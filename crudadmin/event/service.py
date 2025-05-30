import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from fastapi import Request
from fastcrud import FastCRUD
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    AdminAuditLogCreate,
    AdminAuditLogRead,
    AdminEventLogCreate,
    AdminEventLogRead,
    EventStatus,
    EventType,
)

logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


class EventService:
    def __init__(self, db_config):
        self.db_config = db_config
        self.crud_events = FastCRUD(db_config.AdminEventLog)
        self.crud_audits = FastCRUD(db_config.AdminAuditLog)
        self.json_encoder = CustomJSONEncoder()

    def _serialize_dict(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not data:
            return {}
        return cast(Dict[str, Any], json.loads(self.json_encoder.encode(data)))

    async def log_event(
        self,
        db: AsyncSession,
        event_type: EventType,
        status: EventStatus,
        user_id: int,
        session_id: str,
        request: Request,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AdminEventLogRead:
        try:
            ip_address = request.client.host if request.client else "unknown"

            event_data = AdminEventLogCreate(
                event_type=event_type,
                status=status,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=request.headers.get("user-agent", ""),
                resource_type=resource_type,
                resource_id=resource_id,
                details=self._serialize_dict(details),
            )

            result = await self.crud_events.create(db=db, object=event_data)

            if hasattr(result, "__dict__"):
                result_dict = {
                    k: v for k, v in result.__dict__.items() if not k.startswith("_")
                }
            else:
                result_dict = cast(Dict[str, Any], dict(result))

            event_read = AdminEventLogRead(**result_dict)

            await db.commit()
            return event_read

        except Exception as e:
            logger.error(f"Error logging event: {str(e)}", exc_info=True)
            raise

    async def create_audit_log(
        self,
        db: AsyncSession,
        event_id: int,
        resource_type: str,
        resource_id: str,
        action: str,
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AdminAuditLogRead:
        try:
            audit_data = AdminAuditLogCreate(
                event_id=event_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                previous_state=self._serialize_dict(previous_state),
                new_state=self._serialize_dict(new_state),
                changes=self._serialize_dict(
                    self._compute_changes(previous_state, new_state)
                ),
                metadata=self._serialize_dict(metadata),
            )

            result = await self.crud_audits.create(db=db, object=audit_data)

            if hasattr(result, "__dict__"):
                result_dict = {
                    k: v for k, v in result.__dict__.items() if not k.startswith("_")
                }
            else:
                result_dict = cast(Dict[str, Any], dict(result))

            return AdminAuditLogRead(**result_dict)

        except Exception as e:
            logger.error(f"Error creating audit log: {str(e)}", exc_info=True)
            raise

    def _compute_changes(
        self,
        previous_state: Optional[Dict[str, Any]],
        new_state: Optional[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Compute changes between previous and new states."""
        changes: Dict[str, Dict[str, Any]] = {}

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
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get user activity logs."""
        filters: Dict[str, Any] = {"user_id": user_id}

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

        return cast(Dict[str, Any], result)

    async def get_resource_history(
        self,
        db: AsyncSession,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
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

        return cast(Dict[str, Any], result)

    async def get_security_alerts(
        self, db: AsyncSession, lookback_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get security alerts based on event patterns."""
        alerts: List[Dict[str, Any]] = []
        lookback_time = datetime.now(UTC) - timedelta(hours=lookback_hours)

        failed_logins = await self.crud_events.get_multi(
            db,
            event_type=EventType.FAILED_LOGIN,
            status=EventStatus.FAILURE,
            timestamp__gte=lookback_time,
        )

        failed_login_patterns: Dict[tuple, int] = {}

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
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

            await self.crud_events.delete(
                db, allow_multiple=True, timestamp__lt=cutoff_date
            )

            await self.crud_audits.delete(
                db, allow_multiple=True, timestamp__lt=cutoff_date
            )

        except Exception as e:
            logger.error(f"Error cleaning up old logs: {str(e)}", exc_info=True)
            raise
