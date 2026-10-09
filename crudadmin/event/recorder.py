import logging
from typing import Any

from fastapi import Request
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ..core.db import get_primary_key_name
from .integration import EventSystemIntegration
from .models import EventType

logger = logging.getLogger(__name__)


def changed_fields(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """The fields whose value differs, each as ``{"old": ..., "new": ...}``."""
    if not before or not after:
        return {}
    return {
        key: {"old": before.get(key), "new": after.get(key)}
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key)
    }


def _primary_key_name_or_id(model: type[DeclarativeBase]) -> str:
    try:
        return get_primary_key_name(model)
    except NoInspectionAvailable:
        return "id"


class AdminEvents:
    """Records changes made through the admin in the event log.

    The admin's create, update and delete routes call [record][] once they know
    the outcome, with the records as they were and as they are; a route of your
    own mounted behind the admin's login can do the same. With event tracking
    off, ``record`` does nothing.

    Secrets in the records are redacted before they are stored. A failure to
    write the event is logged and absorbed, since the change it describes is
    already committed.

    Example:
        ```python
        await admin.events.record(
            request,
            admin_db,
            EventType.UPDATE,
            Product,
            record_id=product.id,
            before=before,
            after=after,
        )
        ```
    """

    def __init__(self, integration: EventSystemIntegration | None) -> None:
        self.integration = integration

    @property
    def enabled(self) -> bool:
        return self.integration is not None

    async def record(
        self,
        request: Request,
        admin_db: AsyncSession,
        event_type: EventType,
        model: type[DeclarativeBase],
        *,
        record_id: Any = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        deleted: list[dict[str, Any]] | None = None,
        succeeded: bool = True,
    ) -> None:
        """Record one create, update or delete of ``model`` by the logged-in admin.

        Args:
            request: The admin's request; the admin and the session handle are
                read from it.
            admin_db: A session on the admin database, where events are kept.
            event_type: ``CREATE``, ``UPDATE`` or ``DELETE``.
            model: The model that changed.
            record_id: The changed record's primary key.
            before: The record before an update.
            after: The record after a create or an update.
            deleted: The records a delete removed, as they were.
            succeeded: False records a refused change, without audit rows.
        """
        if self.integration is None:
            return
        admin = getattr(request.state, "user", None) or {}
        try:
            await self.integration.log_model_event(
                db=admin_db,
                event_type=event_type,
                model=model,
                user_id=admin.get("id") or 0,
                session_id=getattr(request.state, "session_handle", None) or "unknown",
                request=request,
                resource_id=None if record_id is None else str(record_id),
                previous_state=before,
                new_state=after,
                details=self._details(
                    request, event_type, model, record_id, before, after, deleted
                ),
                succeeded=succeeded,
                deleted_records=deleted,
                primary_key_name=_primary_key_name_or_id(model),
            )
        except Exception:
            logger.exception(
                "Could not record the %s of %s; the change itself stands",
                event_type.value,
                model.__name__,
            )

    @staticmethod
    def _details(
        request: Request,
        event_type: EventType,
        model: type[DeclarativeBase],
        record_id: Any,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        deleted: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """What the event log page shows: the record's changes, and the request."""
        changes: Any
        if event_type == EventType.UPDATE:
            changes = changed_fields(before, after)
        elif event_type == EventType.DELETE:
            changes = {"deleted_records": deleted or []}
        else:
            changes = after
        return {
            "resource_details": {
                "model": model.__name__,
                "id": None if record_id is None else str(record_id),
                "changes": changes,
            },
            "request_details": {
                "method": request.method,
                "path": request.url.path,
                "user_agent": request.headers.get("user-agent"),
            },
        }
