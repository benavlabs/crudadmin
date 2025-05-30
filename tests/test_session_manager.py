from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import AdminSessionUpdate


@pytest.mark.asyncio
async def test_session_manager_initialization(db_config):
    """Test SessionManager initialization."""
    manager = SessionManager(
        db_config=db_config,
        max_sessions_per_user=5,
        session_timeout_minutes=30,
        cleanup_interval_minutes=15,
    )

    assert manager.db_config == db_config
    assert manager.max_sessions == 5
    assert manager.session_timeout == timedelta(minutes=30)
    assert manager.cleanup_interval == timedelta(minutes=15)


@pytest.mark.asyncio
async def test_create_session_success(session_manager, mock_request):
    """Test successful session creation."""
    user_id = 1
    metadata = {"test": "data"}

    # Mock the database operations
    with patch.object(
        session_manager, "get_user_active_sessions", new_callable=AsyncMock
    ) as mock_get_sessions, patch.object(
        session_manager.db_config.crud_sessions, "create", new_callable=AsyncMock
    ) as mock_create:
        # Setup mocks
        mock_get_sessions.return_value = []  # No existing sessions

        # Mock the create method to return a successful result
        mock_create.return_value = {"id": 1, "session_id": "test-session-id"}

        # Mock the get_admin_db async generator
        async def mock_get_admin_db():
            mock_session = AsyncMock()
            yield mock_session

        session_manager.db_config.get_admin_db = mock_get_admin_db

        result = await session_manager.create_session(mock_request, user_id, metadata)

        # The result should be an AdminSessionCreate object
        assert result is not None
        assert hasattr(result, "user_id")
        assert result.user_id == user_id
        assert result.session_metadata == metadata
        assert result.ip_address == "127.0.0.1"
        assert result.is_active is True


@pytest.mark.asyncio
async def test_create_session_max_sessions_reached(session_manager, mock_request):
    """Test session creation when max sessions is reached."""
    user_id = 1

    # Mock existing sessions (more than max allowed)
    existing_sessions = [
        {"session_id": f"session-{i}"} for i in range(session_manager.max_sessions + 1)
    ]

    with patch.object(
        session_manager, "get_user_active_sessions", new_callable=AsyncMock
    ) as mock_get_sessions, patch.object(
        session_manager, "terminate_session", new_callable=AsyncMock
    ) as mock_terminate, patch.object(
        session_manager.db_config.crud_sessions, "create", new_callable=AsyncMock
    ) as mock_create:
        # Setup mocks
        mock_get_sessions.return_value = existing_sessions
        mock_create.return_value = {"id": 1, "session_id": "new-session-id"}

        # Mock the get_admin_db async generator
        async def mock_get_admin_db():
            mock_session = AsyncMock()
            yield mock_session

        session_manager.db_config.get_admin_db = mock_get_admin_db

        result = await session_manager.create_session(mock_request, user_id)

        # Verify old sessions were terminated
        assert mock_terminate.call_count == len(existing_sessions)
        assert result is not None


@pytest.mark.asyncio
async def test_create_session_invalid_request(session_manager):
    """Test session creation with invalid request."""
    user_id = 1

    # Mock request with no client
    mock_request = Mock()
    mock_request.client = None
    mock_request.headers = {"user-agent": "test-agent"}

    with pytest.raises(ValueError, match="Invalid request client"):
        await session_manager.create_session(mock_request, user_id)


@pytest.mark.asyncio
async def test_validate_session_success(session_manager):
    """Test successful session validation."""
    session_id = "test-session-id"
    current_time = datetime.now(UTC)

    session_data = {
        "session_id": session_id,
        "is_active": True,
        "last_activity": current_time.isoformat(),
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi, patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        mock_get_multi.return_value = {"data": [session_data]}

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is True
        mock_update.assert_called_once()  # Activity should be updated


@pytest.mark.asyncio
async def test_validate_session_not_found(session_manager):
    """Test session validation when session is not found."""
    session_id = "nonexistent-session"

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = {"data": []}

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is False


@pytest.mark.asyncio
async def test_validate_session_inactive(session_manager):
    """Test session validation when session is inactive."""
    session_id = "inactive-session"

    session_data = {
        "session_id": session_id,
        "is_active": False,
        "last_activity": datetime.now(UTC).isoformat(),
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = {"data": [session_data]}

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is False


@pytest.mark.asyncio
async def test_validate_session_timed_out(session_manager):
    """Test session validation when session has timed out."""
    session_id = "timed-out-session"
    old_time = datetime.now(UTC) - timedelta(hours=2)  # Older than timeout

    session_data = {
        "session_id": session_id,
        "is_active": True,
        "last_activity": old_time.isoformat(),
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi, patch.object(
        session_manager, "terminate_session", new_callable=AsyncMock
    ) as mock_terminate:
        mock_get_multi.return_value = {"data": [session_data]}

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is False
        mock_terminate.assert_called_once_with(ANY, session_id)


@pytest.mark.asyncio
async def test_validate_session_no_update_activity(session_manager):
    """Test session validation without updating activity."""
    session_id = "test-session-id"
    current_time = datetime.now(UTC)

    session_data = {
        "session_id": session_id,
        "is_active": True,
        "last_activity": current_time.isoformat(),
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi, patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        mock_get_multi.return_value = {"data": [session_data]}

        result = await session_manager.validate_session(
            AsyncMock(), session_id, update_activity=False
        )

        assert result is True
        mock_update.assert_not_called()  # Activity should not be updated


@pytest.mark.asyncio
async def test_update_activity(session_manager):
    """Test updating session activity."""
    session_id = "test-session-id"

    with patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        await session_manager.update_activity(AsyncMock(), session_id)

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[1]["session_id"] == session_id
        assert isinstance(call_args[1]["object"], AdminSessionUpdate)


@pytest.mark.asyncio
async def test_terminate_session(session_manager):
    """Test session termination."""
    session_id = "test-session-id"

    with patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        await session_manager.terminate_session(AsyncMock(), session_id)

        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[1]["session_id"] == session_id

        update_data = call_args[1]["object"]
        assert isinstance(update_data, AdminSessionUpdate)
        assert update_data.is_active is False


@pytest.mark.asyncio
async def test_get_user_active_sessions(session_manager):
    """Test getting user active sessions."""
    user_id = 1

    mock_sessions = [
        {"session_id": "session-1", "user_id": user_id, "is_active": True},
        {"session_id": "session-2", "user_id": user_id, "is_active": True},
    ]

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = {"data": mock_sessions}

        result = await session_manager.get_user_active_sessions(AsyncMock(), user_id)

        assert result == mock_sessions
        mock_get_multi.assert_called_once_with(ANY, user_id=user_id, is_active=True)


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(session_manager):
    """Test cleanup of expired sessions."""
    # Force the cleanup to run by setting last_cleanup to an old time
    session_manager.last_cleanup = datetime.now(UTC) - timedelta(hours=1)

    cutoff_time = datetime.now(UTC) - session_manager.session_timeout

    # Mock expired sessions
    expired_sessions = [
        {
            "session_id": "expired-1",
            "last_activity": cutoff_time - timedelta(minutes=1),
        },
        {
            "session_id": "expired-2",
            "last_activity": cutoff_time - timedelta(minutes=2),
        },
    ]

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi, patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        mock_get_multi.return_value = {"data": expired_sessions}

        await session_manager.cleanup_expired_sessions(AsyncMock())

        # Should have called get_multi to find expired sessions
        mock_get_multi.assert_called_once()
        # Should have called update for each expired session
        assert mock_update.call_count == len(expired_sessions)


@pytest.mark.asyncio
async def test_get_session_metadata(session_manager):
    """Test getting session metadata."""
    session_id = "test-session-id"
    metadata = {"test": "data", "user_info": {"role": "admin"}}

    session_data = {
        "session_id": session_id,
        "user_id": 1,
        "ip_address": "127.0.0.1",
        "device_info": {"browser": "Chrome"},
        "created_at": datetime.now(UTC),
        "last_activity": datetime.now(UTC),
        "is_active": True,
        "metadata": metadata,
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = session_data

        result = await session_manager.get_session_metadata(AsyncMock(), session_id)

        assert result is not None
        assert result["session_id"] == session_id
        assert result["user_id"] == 1
        mock_get.assert_called_once_with(ANY, session_id=session_id)


@pytest.mark.asyncio
async def test_get_session_metadata_not_found(session_manager):
    """Test getting session metadata when session is not found."""
    session_id = "nonexistent-session"

    with patch.object(
        session_manager.db_config.crud_sessions, "get", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        result = await session_manager.get_session_metadata(AsyncMock(), session_id)

        assert result is None
        mock_get.assert_called_once_with(ANY, session_id=session_id)


@pytest.mark.asyncio
async def test_handle_concurrent_login(session_manager):
    """Test handling concurrent login."""
    user_id = 1
    current_session_id = "current-session"

    other_sessions = [
        {"session_id": "session-1", "metadata": {}},
        {"session_id": "session-2", "metadata": {}},
    ]

    with patch.object(
        session_manager, "get_user_active_sessions", new_callable=AsyncMock
    ) as mock_get_sessions, patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ) as mock_update:
        mock_get_sessions.return_value = other_sessions + [
            {"session_id": current_session_id}
        ]

        await session_manager.handle_concurrent_login(
            AsyncMock(), user_id, current_session_id
        )

        # Should update metadata for other sessions (not the current one)
        assert mock_update.call_count == len(other_sessions)

        # Verify the update calls
        for call in mock_update.call_args_list:
            session_id = call[1]["session_id"]
            assert session_id != current_session_id
            assert session_id in ["session-1", "session-2"]


@pytest.mark.asyncio
async def test_make_timezone_aware(session_manager):
    """Test making datetime timezone aware."""
    # Test with naive datetime
    naive_dt = datetime(2023, 1, 1, 12, 0, 0)
    aware_dt = session_manager.make_timezone_aware(naive_dt)
    assert aware_dt.tzinfo == UTC

    # Test with already aware datetime
    already_aware = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = session_manager.make_timezone_aware(already_aware)
    assert result == already_aware


@pytest.mark.asyncio
async def test_validate_session_with_datetime_object(session_manager):
    """Test session validation with datetime object instead of string."""
    session_id = "test-session-id"
    current_time = datetime.now(UTC)

    session_data = {
        "session_id": session_id,
        "is_active": True,
        "last_activity": current_time,  # datetime object instead of string
    }

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi, patch.object(
        session_manager.db_config.crud_sessions, "update", new_callable=AsyncMock
    ):
        mock_get_multi.return_value = {"data": [session_data]}

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is True


@pytest.mark.asyncio
async def test_validate_session_exception_handling(session_manager):
    """Test session validation exception handling."""
    session_id = "test-session-id"

    with patch.object(
        session_manager.db_config.crud_sessions, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.side_effect = Exception("Database error")

        result = await session_manager.validate_session(AsyncMock(), session_id)

        assert result is False


@pytest.mark.asyncio
async def test_create_session_exception_handling(session_manager, mock_request):
    """Test session creation exception handling."""
    user_id = 1

    with patch.object(
        session_manager, "get_user_active_sessions", new_callable=AsyncMock
    ) as mock_get_sessions, patch.object(
        session_manager.db_config.crud_sessions, "create", new_callable=AsyncMock
    ) as mock_create:
        # Setup mocks to trigger an exception
        mock_get_sessions.return_value = []

        # Make the create method raise an exception
        mock_create.side_effect = Exception("Database error")

        # Mock the get_admin_db async generator
        async def mock_get_admin_db():
            mock_session = AsyncMock()
            yield mock_session

        session_manager.db_config.get_admin_db = mock_get_admin_db

        with pytest.raises(Exception, match="Database error"):
            await session_manager.create_session(mock_request, user_id)
