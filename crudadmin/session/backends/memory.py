import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Pattern, TypeVar

from pydantic import BaseModel

from ..storage import AbstractSessionStorage

UTC = timezone.utc

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class MemorySessionStorage(AbstractSessionStorage[T]):
    """In-memory implementation of session storage for testing."""

    def __init__(
        self,
        prefix: str = "session:",
        expiration: int = 1800,
    ):
        """Initialize the in-memory session storage.

        Args:
            prefix: Prefix for all session keys
            expiration: Default session expiration in seconds
        """
        super().__init__(prefix=prefix, expiration=expiration)
        self.data: dict[str, bytes] = {}
        self.expiry: dict[str, datetime] = {}

    async def create(
        self,
        data: T,
        session_id: Optional[str] = None,
        expiration: Optional[int] = None,
    ) -> str:
        """Create a new session in memory.

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

        json_data = data.model_dump_json()

        value_bytes = (
            json_data.encode("utf-8") if isinstance(json_data, str) else json_data
        )

        self.data[key] = value_bytes
        self.expiry[key] = datetime.now(UTC) + timedelta(seconds=exp)

        logger.debug(f"Created session {session_id} with expiration {exp}s")
        return session_id

    async def get(self, session_id: str, model_class: type[T]) -> Optional[T]:
        """Get session data from memory.

        Args:
            session_id: The session ID
            model_class: The Pydantic model class to decode the data into

        Returns:
            The session data or None if session doesn't exist
        """
        key = self.get_key(session_id)

        if self._check_expiry(key):
            return None

        data_bytes = self.data.get(key)
        if data_bytes is None:
            return None

        try:
            data_str = (
                data_bytes.decode("utf-8")
                if isinstance(data_bytes, bytes)
                else data_bytes
            )
            json_data = json.loads(data_str)
            return model_class.model_validate(json_data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing session data: {e}")
            return None

    async def update(
        self,
        session_id: str,
        data: T,
        reset_expiration: bool = True,
        expiration: Optional[int] = None,
    ) -> bool:
        """Update session data in memory.

        Args:
            session_id: The session ID
            data: New session data
            reset_expiration: Whether to reset the expiration
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was updated, False if it didn't exist
        """
        key = self.get_key(session_id)

        if key not in self.data or self._check_expiry(key):
            return False

        json_data = data.model_dump_json()
        value_bytes = (
            json_data.encode("utf-8") if isinstance(json_data, str) else json_data
        )

        self.data[key] = value_bytes

        if reset_expiration:
            exp = expiration if expiration is not None else self.expiration
            self.expiry[key] = datetime.now(UTC) + timedelta(seconds=exp)

        return True

    async def delete(self, session_id: str) -> bool:
        """Delete a session from memory.

        Args:
            session_id: The session ID

        Returns:
            True if the session was deleted, False if it didn't exist
        """
        key = self.get_key(session_id)

        if key in self.data:
            del self.data[key]
            if key in self.expiry:
                del self.expiry[key]
            return True
        return False

    async def extend(self, session_id: str, expiration: Optional[int] = None) -> bool:
        """Extend the expiration of a session in memory.

        Args:
            session_id: The session ID
            expiration: Optional custom expiration in seconds

        Returns:
            True if the session was extended, False if it didn't exist
        """
        key = self.get_key(session_id)
        exp = expiration if expiration is not None else self.expiration

        if key in self.data and not self._check_expiry(key):
            self.expiry[key] = datetime.now(UTC) + timedelta(seconds=exp)
            return True
        return False

    async def exists(self, session_id: str) -> bool:
        """Check if a session exists in memory.

        Args:
            session_id: The session ID

        Returns:
            True if the session exists, False otherwise
        """
        key = self.get_key(session_id)
        return key in self.data and not self._check_expiry(key)

    async def _scan_iter(self, match: Optional[str] = None) -> list[str]:
        """Scan for keys matching a pattern.

        Args:
            match: Pattern to match

        Returns:
            List of matching keys
        """
        if match:
            pattern = match.replace("*", ".*").replace("?", ".")
            pattern = f"^{pattern}$"
            regex: Pattern = re.compile(pattern)

            matching_keys = []
            for key in list(self.data.keys()):
                if self._check_expiry(key):
                    continue

                if regex.match(key):
                    matching_keys.append(key)
            return matching_keys
        else:
            return [
                key for key in list(self.data.keys()) if not self._check_expiry(key)
            ]

    def _check_expiry(self, key: str) -> bool:
        """Check if a key has expired and remove it if so.

        Args:
            key: The key to check

        Returns:
            True if expired (and removed), False otherwise
        """
        if key in self.expiry and datetime.now(UTC) > self.expiry[key]:
            del self.data[key]
            del self.expiry[key]
            return True
        return False

    async def close(self) -> None:
        """Clear all data."""
        self.data.clear()
        self.expiry.clear()

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: The pattern to match keys (e.g., "login:*")

        Returns:
            Number of keys deleted
        """
        matching_keys = await self._scan_iter(match=pattern)

        deleted_count = 0
        for key in matching_keys:
            if key in self.data:
                del self.data[key]
                if key in self.expiry:
                    del self.expiry[key]
                deleted_count += 1

        logger.debug(f"Deleted {deleted_count} keys matching pattern '{pattern}'")
        return deleted_count
