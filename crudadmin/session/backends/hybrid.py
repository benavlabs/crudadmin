"""
Hybrid session storage backend combining Redis and Database storage.

This backend provides the best of both worlds:
- Redis: Fast active session management with automatic expiration
- Database: Persistent audit trail visible in admin dashboard

The Redis storage handles all active session operations while the database
maintains a persistent record for monitoring and analytics.
"""

import logging
from typing import Optional, TypeVar, cast

from pydantic import BaseModel

from ..storage import AbstractSessionStorage

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class HybridSessionStorage(AbstractSessionStorage[T]):
    """Hybrid storage: Redis for active sessions + Database for audit trail."""

    def __init__(
        self,
        redis_storage: AbstractSessionStorage[T],
        database_storage: AbstractSessionStorage[T],
        prefix: str = "session:",
        expiration: int = 1800,
    ):
        """Initialize the Hybrid session storage.

        Args:
            redis_storage: Redis storage instance for active sessions
            database_storage: Database storage instance for audit trail
            prefix: Prefix for all session keys (inherited from redis_storage)
            expiration: Default session expiration in seconds
        """
        super().__init__(prefix=prefix, expiration=expiration)
        self.redis_storage = redis_storage
        self.database_storage = database_storage

    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session in both Redis and Database.

        Args:
            data: Session data (must be a Pydantic model)
            session_id: Optional session ID. If not provided, one will be generated
            expiration: Optional custom expiration in seconds

        Returns:
            The session ID
        """
        session_id = await self.redis_storage.create(data, session_id, expiration)

        try:
            await self.database_storage.create(data, session_id, None)
            logger.debug(f"Session {session_id} stored in both Redis and Database")
        except Exception as e:
            logger.warning(f"Failed to store session audit trail in database: {e}")

        return session_id

    async def get(self, session_id: str, model_class: type[T]) -> Optional[T]:
        """Get session data from Redis (active sessions only).

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist or expired
        """
        return await self.redis_storage.get(session_id, model_class)

    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data in both Redis and Database.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was updated in Redis, False if it didn't exist
        """
        result = await self.redis_storage.update(
            session_id, data, reset_expiration, expiration
        )

        try:
            await self.database_storage.update(session_id, data, reset_expiration, None)
            logger.debug(f"Session {session_id} updated in both Redis and Database")
        except Exception as e:
            logger.warning(f"Failed to update session audit trail in database: {e}")

        return result

    async def delete(self, session_id: str) -> bool:
        """Delete session from Redis and mark as inactive in Database.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted from Redis, False if it didn't exist
        """
        result = await self.redis_storage.delete(session_id)

        try:
            session_data = None

            if hasattr(self.database_storage, "get_raw"):
                session_data = await self.database_storage.get_raw(session_id)
            else:
                try:
                    session_data = await self.database_storage.get(
                        session_id, cast("type[T]", BaseModel)
                    )
                except TypeError:
                    await self.database_storage.delete(session_id)
                    logger.debug(
                        f"Session {session_id} deleted from Redis and hard-deleted from Database"
                    )
                    return result

            if session_data:
                if hasattr(session_data, "is_active"):
                    session_data.is_active = False
                elif isinstance(session_data, dict):
                    session_data["is_active"] = False

                await self.database_storage.update(
                    session_id, session_data, False, None
                )
                logger.debug(
                    f"Session {session_id} deleted from Redis and marked inactive in Database"
                )
            else:
                await self.database_storage.delete(session_id)
                logger.debug(
                    f"Session {session_id} deleted from both Redis and Database"
                )
        except Exception as e:
            logger.warning(f"Failed to update session audit trail on delete: {e}")

        return result

    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session in Redis.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was extended in Redis, False if it didn't exist
        """
        result = await self.redis_storage.extend(session_id, expiration)

        try:
            await self.database_storage.extend(session_id, None)
            logger.debug(
                f"Session {session_id} extended in Redis and last_activity updated in Database"
            )
        except Exception as e:
            logger.warning(f"Failed to update last_activity in database: {e}")

        return result

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists in Redis (active sessions only).

        Args:
            session_id: The session ID

        Returns:
            True if the session exists in Redis, False otherwise
        """
        return await self.redis_storage.exists(session_id)

    async def get_user_sessions(self, user_id: int) -> list[str]:
        """Get all active session IDs for a user from Redis.

        Args:
            user_id: The user ID

        Returns:
            List of active session IDs for the user
        """
        try:
            if hasattr(self.redis_storage, "get_user_sessions"):
                result = await self.redis_storage.get_user_sessions(user_id)
                return result if isinstance(result, list) else []
            else:
                return []
        except Exception as e:
            logger.warning(f"Failed to get user sessions from Redis: {e}")
            try:
                if hasattr(self.database_storage, "get_user_sessions"):
                    result = await self.database_storage.get_user_sessions(user_id)
                    return result if isinstance(result, list) else []
                else:
                    return []
            except Exception as db_e:
                logger.error(
                    f"Failed to get user sessions from Database fallback: {db_e}"
                )
                return []

    async def close(self) -> None:
        """Close both storage connections."""
        await self.redis_storage.close()
        await self.database_storage.close()
