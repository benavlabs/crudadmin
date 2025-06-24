import hashlib
import json
import logging
from typing import TYPE_CHECKING, Optional, TypeVar

from pydantic import BaseModel

from ..storage import AbstractSessionStorage

if TYPE_CHECKING:
    import aiomcache

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

try:
    import aiomcache

    MemcachedClient = aiomcache.Client
    MEMCACHED_AVAILABLE = True
except ImportError:
    aiomcache = None  # type: ignore
    MemcachedClient = None  # type: ignore
    MEMCACHED_AVAILABLE = False


class MemcachedSessionStorage(AbstractSessionStorage[T]):
    """Memcached implementation of session storage."""

    def __init__(
        self,
        prefix: str = "session:",
        expiration: int = 1800,
        host: str = "localhost",
        port: int = 11211,
        pool_size: int = 10,
    ):
        """Initialize the Memcached session storage.

        Args:
            prefix: Prefix for all session keys
            expiration: Default session expiration in seconds
            host: Memcached host
            port: Memcached port
            pool_size: Connection pool size
        """
        if not MEMCACHED_AVAILABLE:
            raise ImportError(
                "The aiomcache package is not installed. "
                "Please install it with 'pip install aiomcache' to use MemcachedSessionStorage."
            )

        super().__init__(prefix=prefix, expiration=expiration)

        self.client = aiomcache.Client(host, port, pool_size=pool_size)

        self.user_sessions_prefix = f"{prefix}user:"

    def _encode_key(self, key: str) -> bytes:
        """Encode a key for Memcached.

        Memcached has a 250 byte key limit, so we hash long keys.

        Args:
            key: The key to encode

        Returns:
            The encoded key as bytes
        """
        if len(key) > 240:
            key_hash = hashlib.md5(key.encode()).hexdigest()
            key = f"{key[:200]}:{key_hash}"
        return key.encode("utf-8")

    def get_user_sessions_key(self, user_id: int) -> str:
        """Get the key for a user's sessions.

        Args:
            user_id: The user ID

        Returns:
            The Memcached key for the user's sessions
        """
        return f"{self.user_sessions_prefix}{user_id}"

    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session in Memcached.

        Args:
            data: Session data (must be a Pydantic model)
            session_id: Optional session ID. If not provided, one will be generated
            expiration: Optional custom expiration in seconds

        Returns:
            The session ID
        """
        if session_id is None:
            session_id = self.generate_session_id()

        key = self.get_key(session_id)
        exp = expiration if expiration is not None else self.expiration

        json_data = data.model_dump_json().encode("utf-8")

        try:
            await self.client.set(self._encode_key(key), json_data, exptime=exp)

            if hasattr(data, "user_id"):
                user_id = data.user_id
                user_sessions_key = self.get_user_sessions_key(user_id)

                user_sessions_data = await self.client.get(
                    self._encode_key(user_sessions_key)
                )

                if user_sessions_data:
                    try:
                        user_sessions = json.loads(user_sessions_data.decode("utf-8"))
                        if session_id not in user_sessions:
                            user_sessions.append(session_id)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        user_sessions = [session_id]
                else:
                    user_sessions = [session_id]

                user_sessions_json = json.dumps(user_sessions).encode("utf-8")
                await self.client.set(
                    self._encode_key(user_sessions_key),
                    user_sessions_json,
                    exptime=exp + 3600,
                )

            logger.debug(f"Created session {session_id} with expiration {exp}s")
            return session_id
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise

    async def get(self, session_id: str, model_class: type[T]) -> Optional[T]:
        """Get session data from Memcached.

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist
        """
        key = self.get_key(session_id)

        try:
            data = await self.client.get(self._encode_key(key))
            if data is None:
                return None

            try:
                json_data = json.loads(data.decode("utf-8"))
                return model_class.model_validate(json_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Error parsing session data: {e}")
                return None

        except Exception as e:
            logger.error(f"Error getting session: {e}")
            raise

    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data in Memcached.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was updated, False if it didn't exist
        """
        key = self.get_key(session_id)

        try:
            if not await self.client.get(self._encode_key(key)):
                return False

            json_data = data.model_dump_json().encode("utf-8")
            exp = expiration if expiration is not None else self.expiration

            await self.client.set(self._encode_key(key), json_data, exptime=exp)

            if reset_expiration and hasattr(data, "user_id"):
                user_id = data.user_id
                user_sessions_key = self.get_user_sessions_key(user_id)

                user_sessions_data = await self.client.get(
                    self._encode_key(user_sessions_key)
                )

                if user_sessions_data:
                    try:
                        user_sessions = json.loads(user_sessions_data.decode("utf-8"))
                        user_sessions_json = json.dumps(user_sessions).encode("utf-8")
                        await self.client.set(
                            self._encode_key(user_sessions_key),
                            user_sessions_json,
                            exptime=exp + 3600,
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass

            return True

        except Exception as e:
            logger.error(f"Error updating session: {e}")
            raise

    async def delete(self, session_id: str) -> bool:
        """Delete a session from Memcached.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted, False if it didn't exist
        """
        key = self.get_key(session_id)

        try:
            session_data = await self.client.get(self._encode_key(key))
            if session_data is None:
                return False

            await self.client.delete(self._encode_key(key))

            try:
                json_data = json.loads(session_data.decode("utf-8"))
                if "user_id" in json_data:
                    user_id = json_data["user_id"]
                    user_sessions_key = self.get_user_sessions_key(user_id)

                    user_sessions_data = await self.client.get(
                        self._encode_key(user_sessions_key)
                    )

                    if user_sessions_data:
                        try:
                            user_sessions = json.loads(
                                user_sessions_data.decode("utf-8")
                            )
                            if session_id in user_sessions:
                                user_sessions.remove(session_id)
                                user_sessions_json = json.dumps(user_sessions).encode(
                                    "utf-8"
                                )
                                await self.client.set(
                                    self._encode_key(user_sessions_key),
                                    user_sessions_json,
                                    exptime=3600 * 24,
                                )
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            raise

    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session in Memcached.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was extended, False if it didn't exist

        Note:
            Memcached doesn't allow extending expiration without updating the value.
            We need to get, then set the value again with a new expiration.
        """
        key = self.get_key(session_id)
        exp = expiration if expiration is not None else self.expiration

        try:
            session_data = await self.client.get(self._encode_key(key))
            if session_data is None:
                return False

            await self.client.set(self._encode_key(key), session_data, exptime=exp)

            try:
                json_data = json.loads(session_data.decode("utf-8"))
                if "user_id" in json_data:
                    user_id = json_data["user_id"]
                    user_sessions_key = self.get_user_sessions_key(user_id)

                    user_sessions_data = await self.client.get(
                        self._encode_key(user_sessions_key)
                    )

                    if user_sessions_data:
                        await self.client.set(
                            self._encode_key(user_sessions_key),
                            user_sessions_data,
                            exptime=exp + 3600,
                        )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            return True
        except Exception as e:
            logger.error(f"Error extending session: {e}")
            raise

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists in Memcached.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise
        """
        key = self.get_key(session_id)

        try:
            data = await self.client.get(self._encode_key(key))
            return data is not None
        except Exception as e:
            logger.error(f"Error checking session existence: {e}")
            raise

    async def get_user_sessions(self, user_id: int) -> list[str]:
        """Get all session IDs for a user.

        Args:
            user_id: The user ID

        Returns:
            List of session IDs for the user
        """
        user_sessions_key = self.get_user_sessions_key(user_id)

        try:
            data = await self.client.get(self._encode_key(user_sessions_key))
            if data is None:
                return []

            try:
                user_sessions = json.loads(data.decode("utf-8"))
                if isinstance(user_sessions, list):
                    return [str(session_id) for session_id in user_sessions]
                else:
                    logger.error(f"User sessions data is not a list: {user_sessions}")
                    return []
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Error parsing user sessions data: {e}")
                return []
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            raise

    async def close(self) -> None:
        """Close the Memcached connection."""
        await self.client.close()
