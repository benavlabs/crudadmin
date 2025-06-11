"""
Database session storage backend for storing sessions in the AdminSession table.

This backend provides persistent session storage that integrates with the admin
dashboard for session management and monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.db import DatabaseConfig
from ..schemas import AdminSessionCreate, AdminSessionUpdate
from ..storage import AbstractSessionStorage

UTC = timezone.utc

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class DatabaseSessionStorage(AbstractSessionStorage[T]):
    """Database implementation of session storage using AdminSession table."""

    def __init__(
        self,
        db_config: DatabaseConfig,
        prefix: str = "session:",
        expiration: int = 1800,
    ):
        """Initialize the Database session storage.

        Args:
            db_config: Database configuration instance
            prefix: Prefix for all session keys (kept for compatibility)
            expiration: Default session expiration in seconds (used for cleanup)
        """
        super().__init__(prefix=prefix, expiration=expiration)
        self.db_config = db_config

    async def _get_db(self) -> AsyncSession:
        """Get database session."""
        return self.db_config.get_admin_session()

    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session in the database.

        Args:
            data: Session data (must be a SessionData-compatible model)
            session_id: Optional session ID. If not provided, one will be generated
            expiration: Optional custom expiration in seconds (stored but not enforced)

        Returns:
            The session ID
        """
        if session_id is None:
            session_id = self.generate_session_id()

        db = await self._get_db()

        try:
            if hasattr(data, "model_dump"):
                data_dict = data.model_dump()
            else:
                data_dict = data.__dict__

            session_create = AdminSessionCreate(
                user_id=data_dict.get("user_id") or 0,
                session_id=session_id,
                ip_address=data_dict.get("ip_address", ""),
                user_agent=data_dict.get("user_agent", ""),
                device_info=data_dict.get("device_info", {}),
                session_metadata=data_dict.get("metadata", {}),
                is_active=data_dict.get("is_active", True),
                created_at=data_dict.get("created_at", datetime.now(UTC)),
                last_activity=data_dict.get("last_activity", datetime.now(UTC)),
            )

            await self.db_config.crud_sessions.create(db=db, object=session_create)
            await db.commit()

            logger.debug(f"Created session {session_id} in database")
            return session_id

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating session in database: {e}")
            raise

    async def get(self, session_id: str, model_class: type[T]) -> Optional[T]:
        """Get session data from the database.

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist
        """
        db = await self._get_db()

        try:
            session_record = await self.db_config.crud_sessions.get(
                db=db, session_id=session_id
            )

            if not session_record:
                return None

            session_dict: dict[str, Any]
            if hasattr(session_record, "user_id"):
                assert not isinstance(session_record, dict), (
                    "Expected AdminSessionRead object"
                )
                session_dict = {
                    "user_id": session_record.user_id,
                    "session_id": session_record.session_id,
                    "ip_address": session_record.ip_address,
                    "user_agent": session_record.user_agent,
                    "device_info": session_record.device_info,
                    "created_at": session_record.created_at.replace(tzinfo=UTC)
                    if session_record.created_at.tzinfo is None
                    else session_record.created_at,
                    "last_activity": session_record.last_activity.replace(tzinfo=UTC)
                    if session_record.last_activity.tzinfo is None
                    else session_record.last_activity,
                    "is_active": session_record.is_active,
                    "metadata": session_record.session_metadata,
                }
            elif isinstance(session_record, dict):
                created_at = session_record.get("created_at")
                last_activity = session_record.get("last_activity")

                if (
                    created_at
                    and hasattr(created_at, "tzinfo")
                    and created_at.tzinfo is None
                ):
                    created_at = created_at.replace(tzinfo=UTC)
                if (
                    last_activity
                    and hasattr(last_activity, "tzinfo")
                    and last_activity.tzinfo is None
                ):
                    last_activity = last_activity.replace(tzinfo=UTC)

                session_dict = {
                    "user_id": session_record.get("user_id"),
                    "session_id": session_record.get("session_id"),
                    "ip_address": session_record.get("ip_address", ""),
                    "user_agent": session_record.get("user_agent", ""),
                    "device_info": session_record.get("device_info", {}),
                    "created_at": created_at,
                    "last_activity": last_activity,
                    "is_active": session_record.get("is_active", True),
                    "metadata": session_record.get("session_metadata", {}),
                }
            else:
                return None

            return model_class.model_validate(session_dict)

        except Exception as e:
            logger.error(f"Error getting session from database: {e}")
            return None

    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data in the database.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration (updates last_activity)
            expiration: Optional custom expiration in seconds (ignored for database)

        Returns:
            True if the session was updated, False if it didn't exist
        """
        db = await self._get_db()

        try:
            existing = await self.db_config.crud_sessions.get(
                db=db, session_id=session_id
            )
            if not existing:
                return False

            if hasattr(data, "model_dump"):
                data_dict = data.model_dump()
            else:
                data_dict = data.__dict__

            update_data = AdminSessionUpdate(
                last_activity=data_dict.get("last_activity", datetime.now(UTC))
                if reset_expiration
                else None,
                is_active=data_dict.get("is_active"),
                session_metadata=data_dict.get("metadata"),
            )

            update_dict = {
                k: v for k, v in update_data.model_dump().items() if v is not None
            }

            if update_dict:
                await self.db_config.crud_sessions.update(
                    db=db, object=update_dict, session_id=session_id
                )
                await db.commit()

            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating session in database: {e}")
            return False

    async def delete(self, session_id: str) -> bool:
        """Delete a session from the database.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted, False if it didn't exist
        """
        db = await self._get_db()

        try:
            existing = await self.db_config.crud_sessions.get(
                db=db, session_id=session_id
            )
            if not existing:
                return False

            update_data = AdminSessionUpdate(
                is_active=False,
                last_activity=datetime.now(UTC),
            )

            await self.db_config.crud_sessions.update(
                db=db, object=update_data.model_dump(), session_id=session_id
            )
            await db.commit()

            logger.debug(f"Marked session {session_id} as inactive in database")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting session from database: {e}")
            return False

    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds (ignored for database)

        Returns:
            True if the session was extended, False if it didn't exist
        """
        db = await self._get_db()

        try:
            existing = await self.db_config.crud_sessions.get(
                db=db, session_id=session_id
            )
            if not existing:
                return False

            update_data = AdminSessionUpdate(
                last_activity=datetime.now(UTC),
            )

            await self.db_config.crud_sessions.update(
                db=db, object=update_data.model_dump(), session_id=session_id
            )
            await db.commit()

            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error extending session in database: {e}")
            return False

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists in the database.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise
        """
        db = await self._get_db()

        try:
            session_record = await self.db_config.crud_sessions.get(
                db=db, session_id=session_id
            )
            return session_record is not None

        except Exception as e:
            logger.error(f"Error checking session existence in database: {e}")
            return False

    async def get_user_sessions(self, user_id: int) -> list[str]:
        """Get all active session IDs for a user.

        Args:
            user_id: The user ID

        Returns:
            List of session IDs for the user
        """
        db = await self._get_db()

        try:
            sessions = await self.db_config.crud_sessions.get_multi(
                db=db, user_id=user_id, is_active=True
            )

            session_data: list[Any] = []
            if isinstance(sessions, dict) and "data" in sessions:
                session_data = sessions["data"]  # type: ignore[assignment]
            elif isinstance(sessions, list):
                session_data = sessions  # type: ignore[assignment]
            elif isinstance(sessions, int):
                return []
            elif hasattr(sessions, "__iter__") and not isinstance(
                sessions, (str, bytes)
            ):
                try:
                    session_data = list(sessions)
                except (TypeError, ValueError):
                    logger.warning(
                        f"Could not convert sessions to list: {type(sessions)}"
                    )
                    return []
            else:
                logger.warning(f"Unexpected sessions format: {type(sessions)}")
                return []

            session_ids = []
            for session in session_data:
                if hasattr(session, "session_id"):
                    session_ids.append(session.session_id)
                elif isinstance(session, dict) and "session_id" in session:
                    session_ids.append(session["session_id"])

            return session_ids

        except Exception as e:
            logger.error(f"Error getting user sessions from database: {e}")
            return []

    async def close(self) -> None:
        """Close the database connection (no-op for database storage)."""
        pass
