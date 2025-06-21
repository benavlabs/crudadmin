import json
import logging
from typing import Optional, TypeVar

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:
    raise ImportError(
        "The redis package is not installed. Please install it with 'pip install redis'"
    ) from None

from pydantic import BaseModel

from ..storage import AbstractSessionStorage

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class RedisSessionStorage(AbstractSessionStorage[T]):
    """Redis implementation of session storage."""

    def __init__(
        self,
        prefix: str = "session:",
        expiration: int = 1800,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        username: Optional[str] = None,
        password: Optional[str] = None,
        pool_size: int = 10,
        connect_timeout: int = 10,
    ):
        """Initialize the Redis session storage.

        Args:
            prefix: Prefix for all session keys
            expiration: Default session expiration in seconds
            host: Redis host
            port: Redis port
            db: Redis database number
            username: Redis username (for ACL authentication, Redis 6.0+)
            password: Redis password
            pool_size: Redis connection pool size
            connect_timeout: Redis connection timeout
        """
        super().__init__(prefix=prefix, expiration=expiration)

        self.client = Redis(
            host=host,
            port=port,
            db=db,
            username=username,
            password=password,
            socket_timeout=connect_timeout,
            socket_connect_timeout=connect_timeout,
            socket_keepalive=True,
            decode_responses=False,
            max_connections=pool_size,
        )

        self.user_sessions_prefix = f"{prefix}user:"

    def get_user_sessions_key(self, user_id: int) -> str:
        """Get the key for a user's sessions set.

        Args:
            user_id: The user ID

        Returns:
            The Redis key for the user's sessions set
        """
        return f"{self.user_sessions_prefix}{user_id}"

    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session in Redis.

        Args:
            data: Session data (must be a Pydantic model)
            session_id: Optional session ID. If not provided, one will be generated
            expiration: Optional custom expiration in seconds

        Returns:
            The session ID

        Raises:
            RedisError: If there is an error with Redis
        """
        if session_id is None:
            session_id = self.generate_session_id()

        key = self.get_key(session_id)
        exp = expiration if expiration is not None else self.expiration

        json_data = data.model_dump_json()

        try:
            pipeline = self.client.pipeline()
            pipeline.set(key, json_data, ex=exp)

            if hasattr(data, "user_id"):
                user_id = data.user_id
                user_sessions_key = self.get_user_sessions_key(user_id)

                pipeline.sadd(user_sessions_key, session_id)

                pipeline.expire(user_sessions_key, exp + 3600)

            await pipeline.execute()
            logger.debug(f"Created session {session_id} with expiration {exp}s")
            return session_id
        except RedisError as e:
            logger.error(f"Error creating session: {e}")
            raise

    async def get(self, session_id: str, model_class: type[T]) -> Optional[T]:
        """Get session data from Redis.

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist

        Raises:
            RedisError: If there is an error with Redis
            ValueError: If the data cannot be parsed
        """
        key = self.get_key(session_id)

        try:
            data = await self.client.get(key)
            if data is None:
                return None

            try:
                json_data = json.loads(data)
                return model_class.model_validate(json_data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Error parsing session data: {e}")
                return None

        except RedisError as e:
            logger.error(f"Error getting session: {e}")
            raise

    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data in Redis.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was updated, False if it didn't exist

        Raises:
            RedisError: If there is an error with Redis
        """
        key = self.get_key(session_id)

        try:
            if not await self.client.exists(key):
                return False

            json_data = data.model_dump_json()
            pipeline = self.client.pipeline()

            if reset_expiration:
                exp = expiration if expiration is not None else self.expiration
                pipeline.set(key, json_data, ex=exp)

                if hasattr(data, "user_id"):
                    user_id = data.user_id
                    user_sessions_key = self.get_user_sessions_key(user_id)
                    pipeline.expire(user_sessions_key, exp + 3600)
            else:
                ttl = await self.client.ttl(key)
                if ttl > 0:
                    pipeline.set(key, json_data, ex=ttl)
                else:
                    exp = expiration if expiration is not None else self.expiration
                    pipeline.set(key, json_data, ex=exp)

                    if hasattr(data, "user_id"):
                        user_id = data.user_id
                        user_sessions_key = self.get_user_sessions_key(user_id)
                        pipeline.expire(user_sessions_key, exp + 3600)

            await pipeline.execute()
            return True

        except RedisError as e:
            logger.error(f"Error updating session: {e}")
            raise

    async def delete(self, session_id: str) -> bool:
        """Delete a session from Redis.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted, False if it didn't exist

        Raises:
            RedisError: If there is an error with Redis
        """
        key = self.get_key(session_id)

        try:
            data = await self.client.get(key)
            if data is None:
                return False

            pipeline = self.client.pipeline()

            pipeline.delete(key)

            try:
                json_data = json.loads(data)
                if "user_id" in json_data:
                    user_id = json_data["user_id"]
                    user_sessions_key = self.get_user_sessions_key(user_id)
                    pipeline.srem(user_sessions_key, session_id)
            except (json.JSONDecodeError, ValueError):
                pass

            result = await pipeline.execute()
            return bool(result[0] > 0)
        except RedisError as e:
            logger.error(f"Error deleting session: {e}")
            raise

    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session in Redis.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was extended, False if it didn't exist

        Raises:
            RedisError: If there is an error with Redis
        """
        key = self.get_key(session_id)
        exp = expiration if expiration is not None else self.expiration

        try:
            data = await self.client.get(key)
            if data is None:
                return False

            pipeline = self.client.pipeline()

            pipeline.expire(key, exp)

            try:
                json_data = json.loads(data)
                if "user_id" in json_data:
                    user_id = json_data["user_id"]
                    user_sessions_key = self.get_user_sessions_key(user_id)
                    pipeline.expire(user_sessions_key, exp + 3600)
            except (json.JSONDecodeError, ValueError):
                pass

            results = await pipeline.execute()
            return bool(results[0])

        except RedisError as e:
            logger.error(f"Error extending session: {e}")
            raise

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists in Redis.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise

        Raises:
            RedisError: If there is an error with Redis
        """
        key = self.get_key(session_id)

        try:
            exists_result = await self.client.exists(key)
            return bool(exists_result)
        except RedisError as e:
            logger.error(f"Error checking session existence: {e}")
            raise

    async def get_user_sessions(self, user_id: int) -> list[str]:
        """Get all session IDs for a user.

        Args:
            user_id: The user ID

        Returns:
            List of session IDs for the user

        Raises:
            RedisError: If there is an error with Redis
        """
        user_sessions_key = self.get_user_sessions_key(user_id)

        try:
            members = await self.client.smembers(user_sessions_key)
            return [m.decode("utf-8") if isinstance(m, bytes) else m for m in members]
        except RedisError as e:
            logger.error(f"Error getting user sessions: {e}")
            raise

    async def close(self) -> None:
        """Close the Redis connection."""
        import warnings

        if hasattr(self.client, "aclose"):
            await self.client.aclose()
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=DeprecationWarning,
                    message=".*Call to deprecated close.*",
                )
                await self.client.close()

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all Redis keys matching a pattern.

        This method is useful for bulk cleanup operations like clearing
        expired rate limiting keys or other grouped data.

        Args:
            pattern: The pattern to match keys (e.g., "login:*")

        Returns:
            Number of keys deleted

        Raises:
            RedisError: If there is an error with Redis
        """
        try:
            matched_keys = []
            async for key in self.client.scan_iter(match=pattern):
                matched_keys.append(key)

            if not matched_keys:
                return 0

            pipeline = self.client.pipeline()
            for key in matched_keys:
                pipeline.delete(key)

            results = await pipeline.execute()
            deleted_count = sum(1 for result in results if result > 0)

            logger.debug(f"Deleted {deleted_count} keys matching pattern '{pattern}'")
            return deleted_count

        except RedisError as e:
            logger.error(f"Error deleting keys with pattern '{pattern}': {e}")
            raise
