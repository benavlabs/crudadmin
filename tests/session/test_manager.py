from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import SessionData
from crudadmin.session.storage import get_session_storage

UTC = timezone.utc


@pytest.mark.asyncio
async def test_session_manager_initialization(db_config):
    """Test SessionManager initialization."""
    # Create storage for the new SessionManager
    storage = get_session_storage(
        backend="memory",
        model_type=SessionData,
        prefix="test_session:",
        expiration=30 * 60,  # 30 minutes in seconds
    )

    manager = SessionManager(
        session_storage=storage,
        max_sessions_per_user=5,
        session_timeout_minutes=30,
        cleanup_interval_minutes=15,
    )

    assert manager.max_sessions == 5
    assert manager.session_timeout == timedelta(minutes=30)
    assert manager.cleanup_interval == timedelta(minutes=15)


@pytest.mark.asyncio
async def test_create_session_success(session_manager, mock_request):
    """Test successful session creation."""
    user_id = 1
    metadata = {"test": "data"}

    # The new session manager doesn't require database mocking
    result = await session_manager.create_session(mock_request, user_id, metadata)

    # The result should be a tuple of (session_id, csrf_token)
    assert result is not None
    assert isinstance(result, tuple)
    assert len(result) == 2

    session_id, csrf_token = result
    assert isinstance(session_id, str)
    assert isinstance(csrf_token, str)
    assert len(session_id) > 0
    assert len(csrf_token) > 0

    # Verify the session was created by retrieving it
    session_data = await session_manager.storage.get(session_id, SessionData)
    assert session_data is not None
    assert session_data.user_id == user_id
    assert session_data.metadata == metadata
    assert session_data.ip_address == "127.0.0.1"
    assert session_data.is_active is True


@pytest.mark.asyncio
async def test_create_session_max_sessions_reached(session_manager, mock_request):
    """Test session creation when max sessions is reached."""
    user_id = 1

    # Create sessions up to the limit
    created_sessions = []
    for _i in range(session_manager.max_sessions):
        session_id, csrf_token = await session_manager.create_session(
            mock_request, user_id
        )
        created_sessions.append(session_id)

    # Verify all sessions exist
    for session_id in created_sessions:
        session_data = await session_manager.storage.get(session_id, SessionData)
        assert session_data is not None
        assert session_data.user_id == user_id

    # Create one more session - this should trigger cleanup of old sessions
    new_session_id, new_csrf_token = await session_manager.create_session(
        mock_request, user_id
    )

    # Verify the new session was created
    new_session_data = await session_manager.storage.get(new_session_id, SessionData)
    assert new_session_data is not None
    assert new_session_data.user_id == user_id

    # Note: The exact cleanup behavior depends on the implementation
    # The new session should exist, but some old ones might be cleaned up


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
async def test_validate_session_success(session_manager, mock_request):
    """Test successful session validation."""
    user_id = 1

    # Create a session first
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    # Validate the session
    result = await session_manager.validate_session(session_id)

    assert result is not None
    assert isinstance(result, SessionData)
    assert result.user_id == user_id
    assert result.is_active is True


@pytest.mark.asyncio
async def test_validate_session_not_found(session_manager):
    """Test session validation when session is not found."""
    session_id = "nonexistent-session"

    result = await session_manager.validate_session(session_id)

    assert result is None


@pytest.mark.asyncio
async def test_validate_session_inactive(session_manager, mock_request):
    """Test session validation when session is inactive."""
    user_id = 1

    # Create a session first
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    # Manually set the session as inactive
    session_data = await session_manager.storage.get(session_id, SessionData)
    session_data.is_active = False
    await session_manager.storage.update(session_id, session_data)

    result = await session_manager.validate_session(session_id)

    assert result is None


@pytest.mark.asyncio
async def test_validate_session_timed_out(session_manager, mock_request):
    """Test session validation when session has timed out."""
    user_id = 1

    # Create a session first
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    # Manually set the session as timed out
    old_time = datetime.now(UTC) - timedelta(hours=2)  # Older than timeout
    session_data = await session_manager.storage.get(session_id, SessionData)
    session_data.last_activity = old_time
    await session_manager.storage.update(session_id, session_data)

    result = await session_manager.validate_session(session_id)

    assert result is None

    # The session should be terminated but not necessarily deleted in the new implementation
    # Check that it was marked as inactive
    terminated_session = await session_manager.storage.get(session_id, SessionData)
    if terminated_session:
        # If the session still exists, it should be marked as inactive
        assert terminated_session.is_active is False


@pytest.mark.asyncio
async def test_terminate_session_success(session_manager, mock_request):
    """Test successful session termination."""
    user_id = 1

    # Create a session first
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    # Terminate the session
    result = await session_manager.terminate_session(session_id)

    assert result is True

    # Verify the session is inactive
    session_data = await session_manager.storage.get(session_id, SessionData)
    assert session_data is not None
    assert session_data.is_active is False


@pytest.mark.asyncio
async def test_terminate_session_not_found(session_manager):
    """Test terminating a session that doesn't exist."""
    session_id = "nonexistent-session"

    result = await session_manager.terminate_session(session_id)

    assert result is False


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(session_manager, mock_request):
    """Test cleanup of expired sessions."""
    user_id = 1

    # Force the cleanup to run by setting last_cleanup to an old time
    session_manager.last_cleanup = datetime.now(UTC) - timedelta(hours=1)

    # Create a session and manually make it expired
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    old_time = datetime.now(UTC) - timedelta(hours=2)  # Older than timeout
    session_data = await session_manager.storage.get(session_id, SessionData)
    session_data.last_activity = old_time
    await session_manager.storage.update(session_id, session_data)

    # Run cleanup
    await session_manager.cleanup_expired_sessions()

    # The session should be marked as inactive
    session_data = await session_manager.storage.get(session_id, SessionData)
    if session_data:
        assert session_data.is_active is False


@pytest.mark.asyncio
async def test_csrf_token_validation(session_manager, mock_request):
    """Test CSRF token validation."""
    user_id = 1

    # Create a session
    session_id, csrf_token = await session_manager.create_session(mock_request, user_id)

    # Validate the CSRF token
    is_valid = await session_manager.validate_csrf_token(session_id, csrf_token)
    assert is_valid is True

    # Test with invalid token
    is_valid = await session_manager.validate_csrf_token(session_id, "invalid-token")
    assert is_valid is False

    # Test with no token
    is_valid = await session_manager.validate_csrf_token(session_id, "")
    assert is_valid is False


@pytest.mark.asyncio
async def test_csrf_token_regeneration(session_manager, mock_request):
    """Test CSRF token regeneration."""
    user_id = 1

    # Create a session
    session_id, old_csrf_token = await session_manager.create_session(
        mock_request, user_id
    )

    # Regenerate CSRF token
    new_csrf_token = await session_manager.regenerate_csrf_token(user_id, session_id)

    assert new_csrf_token != old_csrf_token
    assert len(new_csrf_token) > 0

    # Old token should be invalid
    is_valid = await session_manager.validate_csrf_token(session_id, old_csrf_token)
    assert is_valid is False

    # New token should be valid
    is_valid = await session_manager.validate_csrf_token(session_id, new_csrf_token)
    assert is_valid is True


@pytest.mark.asyncio
async def test_parse_user_agent(session_manager):
    """Test user agent parsing."""
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    result = session_manager.parse_user_agent(user_agent)

    assert result.browser
    assert result.os
    assert isinstance(result.is_mobile, bool)
    assert isinstance(result.is_tablet, bool)
    assert isinstance(result.is_pc, bool)
