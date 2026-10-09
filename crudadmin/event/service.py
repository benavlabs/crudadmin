import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, cast
from uuid import UUID

from fastapi import Request
from fastcrud import FastCRUD
from sqlalchemy.ext.asyncio import AsyncSession

from .models import USER_AGENT_LENGTH
from .schemas import (
    AdminAuditLogCreate,
    AdminAuditLogRead,
    AdminEventLogCreate,
    AdminEventLogRead,
    EventStatus,
    EventType,
)

UTC = timezone.utc

logger = logging.getLogger(__name__)


REDACTED = "[redacted]"
SENSITIVE_KEY_PARTS = ("password", "secret", "token", "session_id", "api_key")


def _is_sensitive(key: Any) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_secrets(value: Any, sensitive: bool = False) -> Any:
    """Replace values stored under credential-like keys with a placeholder.

    Applies at any depth, so ``{"hashed_password": {"old": ..., "new": ...}}`` in
    a change set keeps its shape and shows that the field changed, without the
    values. Every event's details and every audit row pass through it before
    they are stored.
    """
    if isinstance(value, dict):
        return {
            k: redact_secrets(v, sensitive or _is_sensitive(k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(v, sensitive) for v in value]
    if sensitive and value is not None:
        return REDACTED
    return value


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


class EventService:
    def __init__(self, db_config):
        self.db_config = db_config
        self.crud_events: FastCRUD[Any, Any, Any, Any, Any, Any] = FastCRUD(
            db_config.AdminEventLog
        )
        self.crud_audits: FastCRUD[Any, Any, Any, Any, Any, Any] = FastCRUD(
            db_config.AdminAuditLog
        )
        self.json_encoder = CustomJSONEncoder()

    def _serialize_dict(self, data: dict | None) -> dict:
        if not data:
            return {}
        return cast(dict, json.loads(self.json_encoder.encode(data)))

    async def log_event(
        self,
        db: AsyncSession,
        event_type: EventType,
        status: EventStatus,
        user_id: int,
        session_id: str,
        request: Request,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        commit: bool = True,
    ) -> AdminEventLogRead:
        ip_address = request.client.host if request.client else "unknown"

        event_data = AdminEventLogCreate(
            event_type=event_type,
            status=status,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent", "")[:USER_AGENT_LENGTH],
            resource_type=resource_type,
            resource_id=resource_id,
            details=self._serialize_dict(redact_secrets(details)),
        )

        result = await self.crud_events.create(
            db=db,
            object=event_data,
            schema_to_select=AdminEventLogRead,
            return_as_model=False,
            commit=commit,
        )
        return AdminEventLogRead(**cast(dict, result))

    async def create_audit_log(
        self,
        db: AsyncSession,
        event_id: int,
        resource_type: str,
        resource_id: str,
        action: str,
        previous_state: dict | None = None,
        new_state: dict | None = None,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> AdminAuditLogRead:
        audit_data = AdminAuditLogCreate(
            event_id=event_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            previous_state=self._serialize_dict(redact_secrets(previous_state)),
            new_state=self._serialize_dict(redact_secrets(new_state)),
            changes=self._serialize_dict(
                redact_secrets(self._compute_changes(previous_state, new_state))
            ),
            audit_metadata=self._serialize_dict(redact_secrets(metadata)),
        )

        result = await self.crud_audits.create(
            db=db,
            object=audit_data,
            schema_to_select=AdminAuditLogRead,
            return_as_model=False,
            commit=commit,
        )

        return AdminAuditLogRead(**cast(dict, result))

    def _compute_changes(
        self,
        previous_state: dict | None,
        new_state: dict | None,
    ) -> dict:
        """Compute changes between previous and new states."""
        changes: dict = {}

        if not previous_state or not new_state:
            return changes

        all_keys = set(previous_state.keys()) | set(new_state.keys())

        for key in all_keys:
            old_value = previous_state.get(key)
            new_value = new_state.get(key)

            if old_value != new_value:
                changes[key] = {"old": old_value, "new": new_value}

        return changes

    async def get_user_activity(
        self,
        db: AsyncSession,
        user_id: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get user activity logs."""
        filters: dict = {"user_id": user_id}

        if start_time:
            filters["timestamp__gte"] = start_time
        if end_time:
            filters["timestamp__lte"] = end_time

        result = await self.crud_events.get_multi(
            db,
            offset=offset,
            limit=limit,
            sort_columns=["timestamp"],
            sort_orders=["desc"],
            **filters,
        )

        return cast(dict, result)

    async def get_resource_history(
        self,
        db: AsyncSession,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get audit history for a specific resource."""
        result = await self.crud_audits.get_multi(
            db,
            offset=offset,
            limit=limit,
            sort_columns=["timestamp"],
            sort_orders=["desc"],
            resource_type=resource_type,
            resource_id=resource_id,
        )

        return cast(dict[str, Any], result)

    async def get_security_alerts(
        self, db: AsyncSession, lookback_hours: int = 24
    ) -> list[dict[str, Any]]:
        """Get security alerts based on event patterns."""
        alerts: list[dict[str, Any]] = []
        lookback_time = datetime.now(UTC) - timedelta(hours=lookback_hours)

        failed_logins = await self.crud_events.get_multi(
            db,
            event_type=EventType.FAILED_LOGIN,
            status=EventStatus.FAILURE,
            timestamp__gte=lookback_time,
        )

        failed_login_patterns: dict[tuple, int] = {}

        for login in failed_logins.get("data", []):
            key = (
                login.get("ip_address", "unknown"),
                login.get("details", {}).get("username", "unknown"),
            )
            failed_login_patterns[key] = failed_login_patterns.get(key, 0) + 1

        for (ip, username), count in failed_login_patterns.items():
            if count >= 5:
                alerts.append(
                    {
                        "type": "multiple_failed_logins",
                        "severity": "high",
                        "details": {
                            "ip_address": ip,
                            "username": username,
                            "attempts": count,
                        },
                    }
                )

        return alerts

    async def cleanup_old_logs(
        self, db: AsyncSession, retention_days: int = 90
    ) -> None:
        """Clean up old logs based on retention policy."""
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        await self.crud_events.delete(
            db, allow_multiple=True, timestamp__lt=cutoff_date
        )

        await self.crud_audits.delete(
            db, allow_multiple=True, timestamp__lt=cutoff_date
        )
