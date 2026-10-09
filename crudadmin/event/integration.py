import logging
from typing import Any, Dict, List, Optional, Tuple, Type

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .models import EventStatus, EventType
from .service import EventService

logger = logging.getLogger(__name__)


class EventSystemIntegration:
    def __init__(self, event_service: EventService):
        self.event_service = event_service

    async def log_model_event(
        self,
        db: AsyncSession,
        event_type: EventType,
        model: Type[DeclarativeBase],
        user_id: int,
        session_id: str,
        request: Request,
        resource_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        succeeded: bool = True,
        deleted_records: Optional[List[Dict[str, Any]]] = None,
        primary_key_name: str = "id",
    ):
        """Record a model change: one event, and its audit rows if the change happened.

        A failed action is recorded as a FAILURE event without audit rows, since
        nothing changed. A delete gets one audit row per deleted record, keyed by
        the model's primary key. The event and its audit rows are written in one
        transaction, rolled back together if any write fails.
        """
        try:
            event = await self.event_service.log_event(
                db=db,
                event_type=event_type,
                status=EventStatus.SUCCESS if succeeded else EventStatus.FAILURE,
                user_id=user_id,
                session_id=session_id,
                request=request,
                resource_type=model.__name__,
                resource_id=str(resource_id) if resource_id else None,
                details=details,
                commit=False,
            )

            if succeeded and event:
                for audited_id, before, after in self._audit_entries(
                    event_type,
                    resource_id,
                    previous_state,
                    new_state,
                    deleted_records,
                    primary_key_name,
                ):
                    await self.event_service.create_audit_log(
                        db=db,
                        event_id=event.id,
                        resource_type=model.__name__,
                        resource_id=audited_id,
                        action=event_type.value,
                        previous_state=before,
                        new_state=after,
                        metadata=details,
                        commit=False,
                    )

            await db.commit()
            return event

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _audit_entries(
        event_type: EventType,
        resource_id: Optional[str],
        previous_state: Optional[Dict[str, Any]],
        new_state: Optional[Dict[str, Any]],
        deleted_records: Optional[List[Dict[str, Any]]],
        primary_key_name: str,
    ) -> List[Tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
        """``(resource_id, previous_state, new_state)`` for each audit row to write."""
        if event_type == EventType.DELETE:
            return [
                (str(record[primary_key_name]), record, None)
                for record in deleted_records or []
                if record.get(primary_key_name) is not None
            ]
        if event_type in (EventType.CREATE, EventType.UPDATE) and resource_id:
            return [(str(resource_id), previous_state, new_state)]
        return []

    async def log_auth_event(
        self,
        db: AsyncSession,
        event_type: EventType,
        user_id: int,
        session_id: str,
        request: Request,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Record an authentication event; a failure is logged, never raised.

        It runs inside login and logout, which must not fail because the event
        log can't be written.
        """
        try:
            status = EventStatus.SUCCESS if success else EventStatus.FAILURE

            await self.event_service.log_event(
                db=db,
                event_type=event_type,
                status=status,
                user_id=user_id,
                session_id=session_id,
                request=request,
                details=details,
            )

        except Exception:
            logger.exception("Could not record the %s event", event_type.value)
            await db.rollback()

    async def log_security_event(
        self,
        db: AsyncSession,
        event_type: EventType,
        user_id: int,
        session_id: str,
        request: Request,
        details: Dict[str, Any],
    ):
        """Log security-related events with high priority."""
        event = await self.event_service.log_event(
            db=db,
            event_type=event_type,
            status=EventStatus.WARNING,
            user_id=user_id,
            session_id=session_id,
            request=request,
            details={**details, "priority": "high", "requires_attention": True},
        )

        return event
