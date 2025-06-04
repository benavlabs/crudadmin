from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import CSRFToken, SessionData, UserAgentInfo
from crudadmin.session.storage import get_session_storage


class TestSessionManagerIntegration:
    """Integration tests for the SessionManager with real storage backends."""

    @pytest.fixture
    def session_manager_with_mocks(self, mock_session_storage, mock_csrf_storage):
        """Create a session manager with mock storage."""
        with (
            patch(
                "crudadmin.session.manager.get_session_storage",
                return_value=mock_session_storage,
            ),
        ):
            manager = SessionManager(session_storage=mock_session_storage)
            manager.csrf_storage = mock_csrf_storage
            return manager

    @pytest.fixture
    def mock_session_request(self):
        """Create a mock request for session creation."""
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
            "x-forwarded-for": "192.168.1.1",
        }
        return request

    @pytest.fixture
    def mock_response(self):
        """Create a mock response for cookie handling."""
        response = MagicMock(spec=Response)
        response.set_cookie = MagicMock()
        response.delete_cookie = MagicMock()
        return response

    @pytest.mark.asyncio
    async def test_create_session_complete_flow(
        self,
        session_manager_with_mocks,
        mock_session_storage,
        mock_csrf_storage,
        mock_session_request,
    ):
        """Test the complete session creation flow with CSRF token."""
        user_id = 1
        session_id = "test-session-id"
        csrf_token = "test-csrf-token"

        mock_session_storage.create.return_value = session_id

        with patch.object(
            session_manager_with_mocks, "_generate_csrf_token", return_value=csrf_token
        ) as mock_gen:
            (
                result_session_id,
                result_csrf_token,
            ) = await session_manager_with_mocks.create_session(
                request=mock_session_request,
                user_id=user_id,
            )

            assert result_session_id == session_id
            assert result_csrf_token == csrf_token

            # Verify session creation
            mock_session_storage.create.assert_called_once()
            create_args = mock_session_storage.create.call_args[0][0]
            assert create_args.user_id == user_id
            assert create_args.ip_address == "192.168.1.1"

            # Verify CSRF token generation
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_session_complete_flow(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test the complete session validation flow."""
        session_id = "test-session-id"

        current_time = datetime.now(UTC)
        session_data = SessionData(
            session_id=session_id,
            user_id=1,
            is_active=True,
            ip_address="127.0.0.1",
            user_agent="test_agent",
            device_info={},
            last_activity=current_time - timedelta(minutes=5),
            metadata={},
        )

        mock_session_storage.get.return_value = session_data
        mock_session_storage.update.return_value = True

        result = await session_manager_with_mocks.validate_session(session_id)

        assert result is not None
        assert result.session_id == session_id
        assert result.user_id == 1

        # Verify session was retrieved and updated
        mock_session_storage.get.assert_called_once_with(session_id, SessionData)
        mock_session_storage.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_session_expired_auto_terminate(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test that expired sessions are automatically terminated."""
        session_id = "test-session-id"

        current_time = datetime.now(UTC)
        session_data = SessionData(
            session_id=session_id,
            user_id=1,
            is_active=True,
            ip_address="127.0.0.1",
            user_agent="test_agent",
            device_info={},
            last_activity=current_time - timedelta(minutes=45),  # Expired
            metadata={},
        )

        mock_session_storage.get.return_value = session_data

        result = await session_manager_with_mocks.validate_session(session_id)

        assert result is None

        # Verify session was retrieved and marked as inactive
        assert mock_session_storage.get.call_count >= 1
        assert mock_session_storage.get.call_args_list[0][0][0] == session_id
        assert mock_session_storage.get.call_args_list[0][0][1] == SessionData

        # Verify session was terminated
        assert mock_session_storage.update.call_count == 1
        update_args = mock_session_storage.update.call_args[0]
        assert update_args[0] == session_id
        assert update_args[1].is_active is False
        assert "terminated_at" in update_args[1].metadata

    @pytest.mark.asyncio
    async def test_validate_session_inactive(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test validation of inactive sessions."""
        session_id = "test-session-id"

        current_time = datetime.now(UTC)
        session_data = SessionData(
            session_id=session_id,
            user_id=1,
            is_active=False,  # Inactive
            ip_address="127.0.0.1",
            user_agent="test_agent",
            device_info={},
            last_activity=current_time - timedelta(minutes=5),
            metadata={},
        )

        mock_session_storage.get.return_value = session_data

        result = await session_manager_with_mocks.validate_session(session_id)

        assert result is None

        # Verify session was retrieved but not updated
        mock_session_storage.get.assert_called_once_with(session_id, SessionData)
        mock_session_storage.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_csrf_token_lifecycle(
        self, session_manager_with_mocks, mock_csrf_storage
    ):
        """Test the complete CSRF token lifecycle."""
        session_id = "test-session-id"
        csrf_token = "test-csrf-token"
        user_id = 1

        current_time = datetime.now(UTC)
        token_data = CSRFToken(
            token=csrf_token,
            user_id=user_id,
            session_id=session_id,
            expires_at=current_time + timedelta(minutes=30),
        )

        # Test validation
        mock_csrf_storage.get.return_value = token_data
        result = await session_manager_with_mocks.validate_csrf_token(
            session_id, csrf_token
        )
        assert result is True
        mock_csrf_storage.get.assert_called_once_with(csrf_token, CSRFToken)

        # Test expired token
        mock_csrf_storage.reset_mock()
        expired_token_data = CSRFToken(
            token=csrf_token,
            user_id=user_id,
            session_id=session_id,
            expires_at=current_time - timedelta(minutes=5),  # Expired
        )
        mock_csrf_storage.get.return_value = expired_token_data

        result = await session_manager_with_mocks.validate_csrf_token(
            session_id, csrf_token
        )
        assert result is False

        # Verify expired token was deleted
        mock_csrf_storage.get.assert_called_once_with(csrf_token, CSRFToken)
        mock_csrf_storage.delete.assert_called_once_with(csrf_token)

    @pytest.mark.asyncio
    async def test_csrf_token_session_mismatch(
        self, session_manager_with_mocks, mock_csrf_storage
    ):
        """Test CSRF token validation with mismatched session ID."""
        session_id = "test-session-id"
        wrong_session_id = "wrong-session-id"
        csrf_token = "test-csrf-token"

        current_time = datetime.now(UTC)
        token_data = CSRFToken(
            token=csrf_token,
            user_id=1,
            session_id=wrong_session_id,  # Different session ID
            expires_at=current_time + timedelta(minutes=30),
        )

        mock_csrf_storage.get.return_value = token_data

        result = await session_manager_with_mocks.validate_csrf_token(
            session_id, csrf_token
        )

        assert result is False
        mock_csrf_storage.get.assert_called_once_with(csrf_token, CSRFToken)

    @pytest.mark.asyncio
    async def test_regenerate_csrf_token(
        self, session_manager_with_mocks, mock_csrf_storage
    ):
        """Test CSRF token regeneration."""
        user_id = 1
        session_id = "test-session-id"
        new_csrf_token = "new-csrf-token"

        with patch.object(
            session_manager_with_mocks,
            "_generate_csrf_token",
            return_value=new_csrf_token,
        ) as mock_generate:
            result = await session_manager_with_mocks.regenerate_csrf_token(
                user_id, session_id
            )

            assert result == new_csrf_token
            mock_generate.assert_called_once_with(user_id, session_id)

    @pytest.mark.asyncio
    async def test_terminate_session_complete(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test complete session termination."""
        session_id = "test-session-id"

        session_data = SessionData(
            session_id=session_id,
            user_id=1,
            is_active=True,
            ip_address="127.0.0.1",
            user_agent="test_agent",
            device_info={},
            last_activity=datetime.now(UTC),
            metadata={},
        )

        mock_session_storage.get.return_value = session_data
        mock_session_storage.update.return_value = True

        result = await session_manager_with_mocks.terminate_session(session_id)

        assert result is True

        # Verify session was retrieved and updated
        mock_session_storage.get.assert_called_once_with(session_id, SessionData)
        mock_session_storage.update.assert_called_once()

        # Verify session was marked as inactive
        update_args = mock_session_storage.update.call_args[0]
        assert update_args[0] == session_id
        assert not update_args[1].is_active
        assert "terminated_at" in update_args[1].metadata
        assert "termination_reason" in update_args[1].metadata

    @pytest.mark.asyncio
    async def test_session_cookie_management(
        self, session_manager_with_mocks, mock_session_response
    ):
        """Test complete session cookie management."""
        session_id = "test-session-id"
        csrf_token = "test-csrf-token"

        # Test setting cookies
        session_manager_with_mocks.set_session_cookies(
            response=mock_session_response,
            session_id=session_id,
            csrf_token=csrf_token,
        )

        # Verify both cookies were set
        assert mock_session_response.set_cookie.call_count == 2

        # Verify session cookie settings
        session_cookie_args = mock_session_response.set_cookie.call_args_list[0][1]
        assert session_cookie_args["key"] == "session_id"
        assert session_cookie_args["value"] == session_id
        assert session_cookie_args["httponly"] is True

        # Verify CSRF cookie settings
        csrf_cookie_args = mock_session_response.set_cookie.call_args_list[1][1]
        assert csrf_cookie_args["key"] == "csrf_token"
        assert csrf_cookie_args["value"] == csrf_token
        assert csrf_cookie_args["httponly"] is False

        # Test clearing cookies
        mock_session_response.reset_mock()
        session_manager_with_mocks.clear_session_cookies(response=mock_session_response)

        # Verify both cookies were cleared
        assert mock_session_response.delete_cookie.call_count == 2
        assert (
            mock_session_response.delete_cookie.call_args_list[0][1]["key"]
            == "session_id"
        )
        assert (
            mock_session_response.delete_cookie.call_args_list[1][1]["key"]
            == "csrf_token"
        )

    @pytest.mark.asyncio
    async def test_user_agent_parsing(self, session_manager_with_mocks):
        """Test user agent parsing functionality."""
        # Test desktop Chrome
        ua_string = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        result = session_manager_with_mocks.parse_user_agent(ua_string)

        assert isinstance(result, UserAgentInfo)
        assert result.browser == "Chrome"
        assert "91.0" in result.browser_version
        assert result.os == "Windows"
        assert result.is_pc is True
        assert result.is_mobile is False

        # Test mobile Safari
        mobile_ua_string = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        )

        mobile_result = session_manager_with_mocks.parse_user_agent(mobile_ua_string)

        assert mobile_result.browser == "Mobile Safari"
        assert mobile_result.os == "iOS"
        assert mobile_result.device == "iPhone"
        assert mobile_result.is_mobile is True
        assert mobile_result.is_pc is False

    @pytest.mark.asyncio
    async def test_enforce_session_limit(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test enforcing maximum sessions per user."""
        user_id = 1
        active_sessions = []

        # Create 6 sessions (more than the default limit of 5)
        for i in range(6):
            session_data = SessionData(
                session_id=f"session-{i}",
                user_id=user_id,
                is_active=True,
                ip_address="127.0.0.1",
                user_agent="test-agent",
                device_info={},
                last_activity=datetime.now(UTC) - timedelta(minutes=i),
                metadata={},
            )
            active_sessions.append(session_data)

        # Mock storage to return user sessions
        mock_session_storage.get_user_sessions.return_value = [
            s.session_id for s in active_sessions
        ]
        mock_session_storage.get.side_effect = lambda sid, cls: next(
            (s for s in active_sessions if s.session_id == sid), None
        )

        await session_manager_with_mocks._enforce_session_limit(user_id)

        # Verify that oldest sessions were terminated
        assert mock_session_storage.update.call_count == 2

        terminated_sessions = [
            args[0][0] for args in mock_session_storage.update.call_args_list
        ]
        assert "session-5" in terminated_sessions  # Oldest session
        assert "session-4" in terminated_sessions  # Second oldest session

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(
        self, session_manager_with_mocks, mock_session_storage
    ):
        """Test cleanup of expired sessions."""
        # Force cleanup to run by setting last_cleanup to old time
        session_manager_with_mocks.last_cleanup = datetime.now(UTC) - timedelta(hours=1)

        # Mock storage scan functionality
        mock_session_storage._scan_iter = AsyncMock()
        test_keys = [
            "session:valid-session",
            "session:expired-session-1",
            "session:expired-session-2",
        ]
        mock_session_storage._scan_iter.return_value = test_keys

        current_time = datetime.now(UTC)
        timeout_threshold = current_time - session_manager_with_mocks.session_timeout

        # Mock session data - some expired, some valid
        def mock_get_side_effect(session_id, model_class):
            if session_id == "valid-session":
                return SessionData(
                    session_id=session_id,
                    user_id=1,
                    is_active=True,
                    ip_address="127.0.0.1",
                    user_agent="test-agent",
                    device_info={},
                    last_activity=current_time - timedelta(minutes=5),  # Valid
                    metadata={},
                )
            else:
                return SessionData(
                    session_id=session_id,
                    user_id=1,
                    is_active=True,
                    ip_address="127.0.0.1",
                    user_agent="test-agent",
                    device_info={},
                    last_activity=timeout_threshold - timedelta(minutes=5),  # Expired
                    metadata={},
                )

        mock_session_storage.get.side_effect = mock_get_side_effect

        await session_manager_with_mocks.cleanup_expired_sessions()

        # Verify scan was called
        mock_session_storage._scan_iter.assert_called_once()

        # Verify expired sessions were updated (marked as inactive)
        # Should have 2 updates for the 2 expired sessions
        assert mock_session_storage.update.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limiting_functionality(self, session_manager_with_mocks):
        """Test rate limiting functionality."""
        ip_address = "127.0.0.1"
        username = "testuser"

        # Test without rate limiter (should always allow)
        session_manager_with_mocks.rate_limiter = None

        (
            is_allowed,
            attempts_remaining,
        ) = await session_manager_with_mocks.track_login_attempt(
            ip_address=ip_address, username=username, success=False
        )

        assert is_allowed is True
        assert attempts_remaining is None

        # Test with mock rate limiter
        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.increment = AsyncMock(return_value=3)
        mock_rate_limiter.delete = AsyncMock()
        session_manager_with_mocks.rate_limiter = mock_rate_limiter

        # Test failed attempt
        (
            is_allowed,
            attempts_remaining,
        ) = await session_manager_with_mocks.track_login_attempt(
            ip_address=ip_address, username=username, success=False
        )

        assert is_allowed is True  # 3 attempts < max of 5
        assert attempts_remaining == 2  # 5 - 3 = 2

        # Test successful attempt (should clear rate limits)
        await session_manager_with_mocks.track_login_attempt(
            ip_address=ip_address, username=username, success=True
        )

        # Verify rate limits were cleared
        assert mock_rate_limiter.delete.call_count == 2  # IP and username keys

    @pytest.mark.asyncio
    async def test_session_manager_initialization_with_backends(self):
        """Test SessionManager initialization with different backends."""
        # Test with memory backend
        memory_storage = get_session_storage(
            backend="memory",
            model_type=SessionData,
            prefix="test_session:",
            expiration=30 * 60,
        )

        memory_manager = SessionManager(
            session_storage=memory_storage,
            max_sessions_per_user=5,
            session_timeout_minutes=30,
        )

        assert memory_manager.max_sessions == 5
        assert memory_manager.session_timeout == timedelta(minutes=30)
        assert memory_manager.storage == memory_storage

        # Test with auto-created storage
        auto_manager = SessionManager(
            session_backend="memory",
            max_sessions_per_user=3,
            session_timeout_minutes=15,
        )

        assert auto_manager.max_sessions == 3
        assert auto_manager.session_timeout == timedelta(minutes=15)
        assert auto_manager.storage is not None
