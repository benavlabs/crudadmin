import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from crudadmin.session.backends.memory import MemorySessionStorage

# Import optional backends with fallbacks
try:
    from crudadmin.session.backends.redis import RedisSessionStorage

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisSessionStorage = None

try:
    from crudadmin.session.backends.memcached import MemcachedSessionStorage

    MEMCACHED_AVAILABLE = True
except ImportError:
    MEMCACHED_AVAILABLE = False
    MemcachedSessionStorage = None


class SessionTestData(BaseModel):
    """Test data model for session testing."""

    user_id: int
    session_id: str
    is_active: bool = True
    metadata: dict = {}


# Memory Backend Tests
class TestMemorySessionStorage:
    """Tests for the Memory session storage backend."""

    @pytest.fixture
    def memory_storage(self):
        """Create a Memory session storage instance."""
        return MemorySessionStorage[SessionTestData](
            prefix="test_session:", expiration=1800
        )

    @pytest.mark.asyncio
    async def test_create_session(self, memory_storage):
        """Test creating a new session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        result = await memory_storage.create(test_data, session_id=session_id)

        assert result == session_id

        # Verify the session was stored
        retrieved = await memory_storage.get(session_id, SessionTestData)
        assert retrieved is not None
        assert retrieved.user_id == test_data.user_id
        assert retrieved.session_id == test_data.session_id

    @pytest.mark.asyncio
    async def test_get_session(self, memory_storage):
        """Test retrieving a session by ID."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        await memory_storage.create(test_data, session_id=session_id)
        result = await memory_storage.get(session_id, SessionTestData)

        assert result is not None
        assert result.user_id == test_data.user_id
        assert result.session_id == test_data.session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, memory_storage):
        """Test retrieving a non-existent session."""
        session_id = "nonexistent-session-id"
        result = await memory_storage.get(session_id, SessionTestData)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_session(self, memory_storage):
        """Test updating an existing session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        await memory_storage.create(test_data, session_id=session_id)

        # Update the data
        test_data.metadata = {"updated": True}
        result = await memory_storage.update(session_id, test_data)
        assert result is True

        # Verify the update
        retrieved = await memory_storage.get(session_id, SessionTestData)
        assert retrieved.metadata == {"updated": True}

    @pytest.mark.asyncio
    async def test_delete_session(self, memory_storage):
        """Test deleting a session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        await memory_storage.create(test_data, session_id=session_id)
        result = await memory_storage.delete(session_id)
        assert result is True

        # Verify the session is gone
        retrieved = await memory_storage.get(session_id, SessionTestData)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_exists_session(self, memory_storage):
        """Test checking if a session exists."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        # Should not exist initially
        assert await memory_storage.exists(session_id) is False

        # Create and check again
        await memory_storage.create(test_data, session_id=session_id)
        assert await memory_storage.exists(session_id) is True

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, memory_storage):
        """Test retrieving all sessions for a user."""
        # Skip if the backend doesn't support get_user_sessions
        if not hasattr(memory_storage, "get_user_sessions"):
            return None

        user_id = 1
        session_ids = ["session1", "session2", "session3"]

        # Create multiple sessions for the user
        for sid in session_ids:
            test_data = SessionTestData(user_id=user_id, session_id=sid)
            await memory_storage.create(test_data, session_id=sid)

        result = await memory_storage.get_user_sessions(user_id)
        assert set(result) == set(session_ids)


# Redis Backend Tests
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestRedisSessionStorage:
    """Tests for the Redis session storage backend."""

    @pytest.fixture
    def mock_pipeline(self):
        """Create a mock Redis pipeline."""
        pipeline = MagicMock()
        pipeline.set = MagicMock(return_value=pipeline)
        pipeline.delete = MagicMock(return_value=pipeline)
        pipeline.sadd = MagicMock(return_value=pipeline)
        pipeline.srem = MagicMock(return_value=pipeline)
        pipeline.expire = MagicMock(return_value=pipeline)
        pipeline.execute = AsyncMock(return_value=[True, True])
        return pipeline

    @pytest.fixture
    def mock_redis(self, mock_pipeline):
        """Create a mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.set = AsyncMock()
        redis_mock.delete = AsyncMock()
        redis_mock.sadd = AsyncMock()
        redis_mock.srem = AsyncMock()
        redis_mock.smembers = AsyncMock()
        redis_mock.expire = AsyncMock()
        redis_mock.exists = AsyncMock()
        redis_mock.ttl = AsyncMock(return_value=1000)
        redis_mock.pipeline = MagicMock(return_value=mock_pipeline)
        return redis_mock

    @pytest.fixture
    def redis_storage(self, mock_redis):
        """Create a Redis session storage instance with a mock Redis client."""
        with patch("crudadmin.session.backends.redis.Redis", return_value=mock_redis):
            storage = RedisSessionStorage[SessionTestData](
                prefix="test_session:", expiration=1800
            )
            storage.client = mock_redis
            return storage

    @pytest.mark.asyncio
    async def test_create_session(self, redis_storage, mock_redis, mock_pipeline):
        """Test creating a new session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        mock_pipeline.execute.return_value = [True, True, True]

        result = await redis_storage.create(test_data, session_id=session_id)

        assert result == session_id
        mock_pipeline.set.assert_called()
        mock_pipeline.sadd.assert_called()
        mock_pipeline.expire.assert_called()
        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session(self, redis_storage, mock_redis):
        """Test retrieving a session by ID."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        mock_redis.get.return_value = test_data.model_dump_json()
        result = await redis_storage.get(session_id, SessionTestData)

        assert result is not None
        assert result.user_id == test_data.user_id
        assert result.session_id == test_data.session_id
        mock_redis.get.assert_called_once_with(f"test_session:{session_id}")

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, redis_storage, mock_redis):
        """Test retrieving a non-existent session."""
        session_id = "nonexistent-session-id"
        mock_redis.get.return_value = None

        result = await redis_storage.get(session_id, SessionTestData)
        assert result is None
        mock_redis.get.assert_called_once_with(f"test_session:{session_id}")

    @pytest.mark.asyncio
    async def test_update_session(self, redis_storage, mock_redis, mock_pipeline):
        """Test updating an existing session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        mock_redis.exists.return_value = True
        mock_pipeline.execute.return_value = [True, True]

        result = await redis_storage.update(session_id, test_data)
        assert result is True

        mock_redis.exists.assert_called_once()
        mock_pipeline.set.assert_called()
        mock_pipeline.expire.assert_called()
        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_session(self, redis_storage, mock_redis, mock_pipeline):
        """Test deleting a session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        mock_redis.get.return_value = test_data.model_dump_json()
        mock_pipeline.execute.return_value = [1, 1]

        result = await redis_storage.delete(session_id)
        assert result is True

        mock_redis.get.assert_called_once()
        mock_pipeline.delete.assert_called()
        mock_pipeline.srem.assert_called()
        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_session(self, redis_storage, mock_redis):
        """Test checking if a session exists."""
        session_id = "test-session-id"
        mock_redis.exists.return_value = True

        result = await redis_storage.exists(session_id)
        assert result is True
        mock_redis.exists.assert_called_once_with(f"test_session:{session_id}")

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, redis_storage, mock_redis):
        """Test retrieving all sessions for a user."""
        user_id = 1
        session_ids = ["session1", "session2", "session3"]
        mock_redis.smembers.return_value = session_ids

        result = await redis_storage.get_user_sessions(user_id)
        assert result == session_ids
        mock_redis.smembers.assert_called_once_with(
            f"{redis_storage.user_sessions_prefix}{user_id}"
        )

    @pytest.mark.asyncio
    async def test_delete_pattern(self, redis_storage, mock_redis):
        """Test deleting keys matching a pattern from Redis."""
        login_keys = [f"login:user:test{i}".encode() for i in range(3)]

        class AsyncIterator:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        mock_redis.scan_iter = MagicMock(return_value=AsyncIterator(login_keys))

        mock_pipeline = MagicMock()
        mock_pipeline.delete = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(return_value=[1, 1, 1])
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

        deleted_count = await redis_storage.delete_pattern("login:*")

        mock_redis.scan_iter.assert_called_once_with(match="login:*")
        mock_redis.pipeline.assert_called_once()
        assert mock_pipeline.delete.call_count == 3
        mock_pipeline.execute.assert_called_once()
        assert deleted_count == 3


# Memcached Backend Tests
@pytest.mark.skipif(not MEMCACHED_AVAILABLE, reason="Memcached not available")
class TestMemcachedSessionStorage:
    """Tests for the Memcached session storage backend."""

    @pytest.fixture
    def mock_memcached(self):
        """Create a mock Memcached client."""
        memcached_mock = AsyncMock()
        memcached_mock.get = AsyncMock()
        memcached_mock.set = AsyncMock()
        memcached_mock.delete = AsyncMock()
        return memcached_mock

    @pytest.fixture
    def memcached_storage(self, mock_memcached):
        """Create a Memcached session storage instance with a mock client."""
        with patch(
            "crudadmin.session.backends.memcached.MemcachedClient",
            return_value=mock_memcached,
        ):
            storage = MemcachedSessionStorage[SessionTestData](
                prefix="test_session:", expiration=1800
            )
            storage.client = mock_memcached
            return storage

    def encode_key(self, key):
        """Helper function to encode a key the same way the storage class does."""
        if len(key) > 240:
            key_hash = hashlib.md5(key.encode()).hexdigest()
            key = f"{key[:200]}:{key_hash}"
        return key.encode("utf-8")

    @pytest.mark.asyncio
    async def test_create_session(self, memcached_storage, mock_memcached):
        """Test creating a new session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        mock_memcached.set.return_value = True
        mock_memcached.get.return_value = None

        result = await memcached_storage.create(test_data, session_id=session_id)

        assert result == session_id
        assert mock_memcached.set.call_count == 2  # Session + user sessions index

        session_key = memcached_storage.get_key(session_id)
        encoded_key = self.encode_key(session_key)
        assert mock_memcached.set.call_args_list[0][0][0] == encoded_key

    @pytest.mark.asyncio
    async def test_get_session(self, memcached_storage, mock_memcached):
        """Test retrieving a session by ID."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        encoded_data = test_data.model_dump_json().encode("utf-8")
        mock_memcached.get.return_value = encoded_data

        result = await memcached_storage.get(session_id, SessionTestData)

        assert result is not None
        assert result.user_id == test_data.user_id
        assert result.session_id == test_data.session_id

        session_key = memcached_storage.get_key(session_id)
        encoded_key = self.encode_key(session_key)
        mock_memcached.get.assert_called_once_with(encoded_key)

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, memcached_storage, mock_memcached):
        """Test retrieving a non-existent session."""
        session_id = "nonexistent-session-id"
        mock_memcached.get.return_value = None

        result = await memcached_storage.get(session_id, SessionTestData)
        assert result is None

        session_key = memcached_storage.get_key(session_id)
        encoded_key = self.encode_key(session_key)
        mock_memcached.get.assert_called_once_with(encoded_key)

    @pytest.mark.asyncio
    async def test_update_session(self, memcached_storage, mock_memcached):
        """Test updating an existing session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        session_key = memcached_storage.get_key(session_id)
        encoded_key = self.encode_key(session_key)

        user_sessions_key = memcached_storage.get_user_sessions_key(1)
        encoded_user_key = self.encode_key(user_sessions_key)

        def mock_get_side_effect(key):
            if key == encoded_key:
                return b"existing_data"
            elif key == encoded_user_key:
                return json.dumps(["session1", session_id]).encode("utf-8")
            return None

        mock_memcached.get.side_effect = mock_get_side_effect
        mock_memcached.set.return_value = True

        result = await memcached_storage.update(session_id, test_data)

        assert result is True
        assert mock_memcached.get.call_count == 2
        assert encoded_key in [
            call_args[0][0] for call_args in mock_memcached.get.call_args_list
        ]
        assert encoded_user_key in [
            call_args[0][0] for call_args in mock_memcached.get.call_args_list
        ]

    @pytest.mark.asyncio
    async def test_delete_session(self, memcached_storage, mock_memcached):
        """Test deleting a session."""
        session_id = "test-session-id"
        test_data = SessionTestData(user_id=1, session_id=session_id)

        encoded_data = test_data.model_dump_json().encode("utf-8")
        mock_memcached.get.return_value = encoded_data

        user_sessions = [session_id, "other-session"]
        encoded_user_sessions = json.dumps(user_sessions).encode("utf-8")

        mock_memcached.get.side_effect = lambda key: (
            encoded_data
            if self.encode_key(memcached_storage.get_key(session_id)) == key
            else encoded_user_sessions
        )

        result = await memcached_storage.delete(session_id)
        assert result is True

        assert mock_memcached.delete.call_count == 1
        session_key = memcached_storage.get_key(session_id)
        encoded_key = self.encode_key(session_key)
        mock_memcached.delete.assert_called_once_with(encoded_key)

    @pytest.mark.asyncio
    async def test_exists_session(self, memcached_storage, mock_memcached):
        """Test checking if a session exists."""
        session_id = "test-session-id"

        mock_memcached.get.return_value = b"some_data"
        result = await memcached_storage.exists(session_id)
        assert result is True

        mock_memcached.get.return_value = None
        result = await memcached_storage.exists(session_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_sessions(self, memcached_storage, mock_memcached):
        """Test retrieving all sessions for a user."""
        user_id = 1
        session_ids = ["session1", "session2", "session3"]

        encoded_data = json.dumps(session_ids).encode("utf-8")
        mock_memcached.get.return_value = encoded_data

        result = await memcached_storage.get_user_sessions(user_id)

        assert result == session_ids

        user_sessions_key = memcached_storage.get_user_sessions_key(user_id)
        encoded_key = self.encode_key(user_sessions_key)
        mock_memcached.get.assert_called_once_with(encoded_key)
