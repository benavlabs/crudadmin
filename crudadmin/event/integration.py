import logging
from typing import Any, Dict, Optional, Type

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
    ):
        try:
            event = await self.event_service.log_event(
                db=db,
                event_type=event_type,
                status=EventStatus.SUCCESS,
                user_id=user_id,
                session_id=session_id,
                request=request,
                resource_type=model.__name__,
                resource_id=str(resource_id) if resource_id else None,
                details=details,
            )

            if (
                event
                and event_type in [EventType.CREATE, EventType.UPDATE, EventType.DELETE]
                and resource_id
            ):
                await self.event_service.create_audit_log(
                    db=db,
                    event_id=event.id,
                    resource_type=model.__name__,
                    resource_id=str(resource_id),
                    action=event_type.value,
                    previous_state=previous_state,
                    new_state=new_state,
                    metadata=details,
                )

            await db.commit()
            return event

        except Exception as e:
            logger.error(f"Error in event logging: {str(e)}")
            await db.rollback()
            raise

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
        """Log authentication-related events."""
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

        except Exception as e:
            logger.error(f"Error logging auth event: {str(e)}", exc_info=True)

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
        try:
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

        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}", exc_info=True)
            raise
