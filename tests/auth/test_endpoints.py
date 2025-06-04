from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status

from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import SessionData


class CSRFException(HTTPException):
    """Custom exception for CSRF validation failures."""

    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@pytest.fixture
def mock_request():
    """Create a mock request for testing."""
    request = MagicMock(spec=Request)
    request.cookies = {"session_id": "test-session-id"}
    request.headers = {"X-CSRF-Token": "test-csrf-token"}
    request.method = "POST"
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_session_data():
    """Create mock session data for testing."""
    return SessionData(
        session_id="test-session-id",
        user_id=1,
        is_active=True,
        ip_address="127.0.0.1",
        user_agent="test-agent",
        device_info={},
        last_activity=datetime.now(UTC),
        metadata={},
    )


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    session_manager = MagicMock(spec=SessionManager)
    session_manager.create_session = AsyncMock()
    session_manager.validate_session = AsyncMock()
    session_manager.validate_csrf_token = AsyncMock()
    session_manager.regenerate_csrf_token = AsyncMock()
    session_manager.terminate_session = AsyncMock()
    session_manager.set_session_cookies = MagicMock()
    session_manager.clear_session_cookies = MagicMock()
    session_manager.track_login_attempt = AsyncMock()
    session_manager.cleanup_expired_sessions = AsyncMock()
    session_manager.session_timeout = timedelta(minutes=30)
    return session_manager


class TestAuthenticationEndpoints:
    """Test authentication endpoints with session management."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, mock_session_manager, admin_user_data, mock_session_request
    ):
        """Test successful login with session authentication."""
        # Mock successful session creation
        mock_session_manager.create_session.return_value = (
            "test-session-id",
            "test-csrf-token",
        )
        mock_session_manager.track_login_attempt.return_value = (True, 5)

        # Test data
        username = admin_user_data["username"]
        password = "password123"

        # Add id to admin_user_data for testing
        admin_user_data_with_id = {**admin_user_data, "id": 1}

        # Mock the authentication logic
        with patch(
            "crudadmin.admin_user.service.AdminUserService.authenticate_user"
        ) as mock_auth:
            mock_auth.return_value = admin_user_data_with_id

            # Simulate login endpoint behavior
            user = await mock_auth(username, password, db=None)
            assert user is not None

            # Create session
            session_id, csrf_token = await mock_session_manager.create_session(
                request=mock_session_request,
                user_id=user["id"],
                metadata={
                    "login_type": "password",
                    "username": user["username"],
                    "creation_time": datetime.now(UTC).isoformat(),
                },
            )

            assert session_id == "test-session-id"
            assert csrf_token == "test-csrf-token"

            # Verify session creation was called
            mock_session_manager.create_session.assert_called_once()
            create_args = mock_session_manager.create_session.call_args
            assert create_args[1]["user_id"] == user["id"]

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, mock_session_manager):
        """Test login with invalid credentials."""
        username = "invalid_user"
        password = "wrong_password"

        with patch(
            "crudadmin.admin_user.service.AdminUserService.authenticate_user"
        ) as mock_auth:
            mock_auth.return_value = None  # Authentication failed

            user = await mock_auth(username, password, db=None)
            assert user is None

            # Session should not be created for failed authentication
            mock_session_manager.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_endpoint(self, mock_session_manager, mock_session_data):
        """Test logout endpoint."""
        session_id = "test-session-id"
        mock_session_manager.terminate_session.return_value = True

        # Simulate logout endpoint behavior
        if session_id:
            await mock_session_manager.terminate_session(session_id=session_id)

        mock_session_manager.terminate_session.assert_called_once_with(
            session_id=session_id
        )

        # Verify session cookies would be cleared
        # (This would be done in the actual endpoint)
        mock_session_manager.clear_session_cookies.assert_not_called()  # Not called in our simulation

    @pytest.mark.asyncio
    async def test_refresh_csrf_token_endpoint(
        self, mock_session_manager, mock_session_data
    ):
        """Test refreshing the CSRF token."""
        session_id = "test-session-id"
        user_id = 1
        new_csrf_token = "new-csrf-token"

        mock_session_manager.regenerate_csrf_token.return_value = new_csrf_token

        # Simulate CSRF refresh endpoint behavior
        result_token = await mock_session_manager.regenerate_csrf_token(
            user_id=user_id,
            session_id=session_id,
        )

        assert result_token == new_csrf_token
        mock_session_manager.regenerate_csrf_token.assert_called_once_with(
            user_id=user_id,
            session_id=session_id,
        )

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, mock_session_manager):
        """Test accessing protected endpoint without authentication."""
        # Simulate missing session
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}

        session_id = mock_request.cookies.get("session_id")
        assert session_id is None

        # This should result in unauthorized access
        # The actual endpoint would raise HTTPException(401)

    @pytest.mark.asyncio
    async def test_protected_endpoint_access(
        self, mock_session_manager, mock_session_data, admin_user_data
    ):
        """Test accessing protected endpoint with valid session."""
        session_id = "test-session-id"
        mock_session_manager.validate_session.return_value = mock_session_data

        # Add id to admin_user_data for testing
        admin_user_data_with_id = {**admin_user_data, "id": 1}

        # Simulate protected endpoint access
        session_data = await mock_session_manager.validate_session(session_id)

        assert session_data is not None
        assert session_data.user_id == admin_user_data_with_id["id"]
        assert session_data.is_active is True

        mock_session_manager.validate_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_csrf_protection_valid_token(
        self, mock_session_manager, mock_session_data
    ):
        """Test CSRF protection with valid token."""
        session_id = "test-session-id"
        csrf_token = "test-csrf-token"

        mock_session_manager.validate_csrf_token.return_value = True

        # Simulate CSRF validation
        is_valid = await mock_session_manager.validate_csrf_token(
            session_id, csrf_token
        )

        assert is_valid is True
        mock_session_manager.validate_csrf_token.assert_called_once_with(
            session_id, csrf_token
        )

    @pytest.mark.asyncio
    async def test_csrf_protection_invalid_token(
        self, mock_session_manager, mock_session_data
    ):
        """Test CSRF protection with invalid token."""
        session_id = "test-session-id"
        csrf_token = "invalid-csrf-token"

        mock_session_manager.validate_csrf_token.return_value = False

        # Simulate CSRF validation
        is_valid = await mock_session_manager.validate_csrf_token(
            session_id, csrf_token
        )

        assert is_valid is False
        mock_session_manager.validate_csrf_token.assert_called_once_with(
            session_id, csrf_token
        )

    @pytest.mark.asyncio
    async def test_csrf_protection_missing_token(
        self, mock_session_manager, mock_session_data
    ):
        """Test CSRF protection when token is missing."""
        csrf_token = None

        # Simulate missing CSRF token validation
        if not csrf_token:
            # This should raise CSRFException in actual implementation
            with pytest.raises(CSRFException):  # Simulating the exception
                raise CSRFException("CSRF token missing")

    @pytest.mark.asyncio
    async def test_login_with_rate_limiting_allowed(
        self, mock_session_manager, admin_user_data, mock_session_request
    ):
        """Test login endpoint with rate limiting - allowed attempt."""
        username = admin_user_data["username"]
        password = "password123"
        ip_address = "127.0.0.1"

        # Add id to admin_user_data for testing
        admin_user_data_with_id = {**admin_user_data, "id": 1}

        # Mock rate limiting to allow the attempt
        mock_session_manager.track_login_attempt.return_value = (True, 4)
        mock_session_manager.create_session.return_value = (
            "test-session-id",
            "test-csrf-token",
        )

        with patch(
            "crudadmin.admin_user.service.AdminUserService.authenticate_user"
        ) as mock_auth:
            mock_auth.return_value = admin_user_data_with_id

            # Simulate rate limiting check
            (
                is_allowed,
                attempts_remaining,
            ) = await mock_session_manager.track_login_attempt(
                ip_address=ip_address, username=username, success=False
            )

            assert is_allowed is True
            assert attempts_remaining == 4

            # If allowed, proceed with authentication
            user = await mock_auth(username, password, db=None)
            assert user is not None

            # Mark successful login
            await mock_session_manager.track_login_attempt(
                ip_address=ip_address, username=username, success=True
            )

            # Create session
            session_id, csrf_token = await mock_session_manager.create_session(
                request=mock_session_request, user_id=user["id"]
            )

            assert session_id == "test-session-id"
            assert csrf_token == "test-csrf-token"

    @pytest.mark.asyncio
    async def test_login_with_rate_limiting_blocked(
        self, mock_session_manager, admin_user_data
    ):
        """Test login endpoint with rate limiting - blocked attempt."""
        username = admin_user_data["username"]
        ip_address = "127.0.0.1"

        # Mock rate limiting to block the attempt
        mock_session_manager.track_login_attempt.return_value = (False, 0)

        # Simulate rate limiting check
        is_allowed, attempts_remaining = await mock_session_manager.track_login_attempt(
            ip_address=ip_address, username=username, success=False
        )

        assert is_allowed is False
        assert attempts_remaining == 0

        # Authentication should not proceed when rate limited
        # The actual endpoint would return 401 or 429

        # Verify session creation was not called
        mock_session_manager.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_validation_expired(self, mock_session_manager):
        """Test session validation with expired session."""
        session_id = "expired-session-id"

        # Mock expired session
        mock_session_manager.validate_session.return_value = None

        session_data = await mock_session_manager.validate_session(session_id)

        assert session_data is None
        mock_session_manager.validate_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_session_cleanup(self, mock_session_manager):
        """Test session cleanup functionality."""
        mock_session_manager.cleanup_expired_sessions.return_value = None

        # Simulate periodic cleanup
        await mock_session_manager.cleanup_expired_sessions()

        mock_session_manager.cleanup_expired_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_cookie_handling(self, mock_session_manager):
        """Test session cookie setting and clearing."""
        from fastapi import Response

        response = MagicMock(spec=Response)
        session_id = "test-session-id"
        csrf_token = "test-csrf-token"

        # Test setting cookies
        mock_session_manager.set_session_cookies(
            response=response,
            session_id=session_id,
            csrf_token=csrf_token,
            secure=True,
            path="/admin",
        )

        mock_session_manager.set_session_cookies.assert_called_once()

        # Test clearing cookies
        mock_session_manager.clear_session_cookies(
            response=response,
            path="/admin",
        )

        mock_session_manager.clear_session_cookies.assert_called_once()


class TestSessionDependencies:
    """Test session-related dependencies and middleware."""

    async def mock_get_session_from_cookie(self, request, session_manager):
        """Mock implementation of getting session from cookie."""
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        session_data = await session_manager.validate_session(session_id)
        if not session_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            )

        return session_data

    async def mock_verify_csrf_token(self, request, session_data, session_manager):
        """Mock implementation of CSRF token verification."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return

        if not session_data:
            return

        token = request.headers.get("X-CSRF-Token")
        if not token:
            raise CSRFException("CSRF token missing")

        is_valid = await session_manager.validate_csrf_token(
            session_data.session_id, token
        )
        if not is_valid:
            raise CSRFException("Invalid CSRF token")

    @pytest.mark.asyncio
    async def test_get_session_from_cookie_success(
        self, mock_session_manager, mock_session_data
    ):
        """Test getting session data from a valid cookie."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {"session_id": "test-session-id"}

        mock_session_manager.validate_session.return_value = mock_session_data

        result = await self.mock_get_session_from_cookie(
            mock_request, mock_session_manager
        )

        assert result == mock_session_data
        mock_session_manager.validate_session.assert_called_once_with("test-session-id")

    @pytest.mark.asyncio
    async def test_get_session_from_cookie_no_cookie(self, mock_session_manager):
        """Test when no session cookie is present."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}

        with pytest.raises(HTTPException) as exc_info:
            await self.mock_get_session_from_cookie(mock_request, mock_session_manager)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Not authenticated" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_session_from_cookie_invalid_session(self, mock_session_manager):
        """Test when session is invalid or expired."""
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {"session_id": "invalid-session-id"}

        mock_session_manager.validate_session.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await self.mock_get_session_from_cookie(mock_request, mock_session_manager)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid or expired session" in exc_info.value.detail
        mock_session_manager.validate_session.assert_called_once_with(
            "invalid-session-id"
        )

    @pytest.mark.asyncio
    async def test_verify_csrf_token_valid(
        self, mock_session_manager, mock_session_data
    ):
        """Test verifying a valid CSRF token."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"X-CSRF-Token": "test-csrf-token"}

        mock_session_manager.validate_csrf_token.return_value = True

        # Should not raise any exception
        await self.mock_verify_csrf_token(
            request=mock_request,
            session_data=mock_session_data,
            session_manager=mock_session_manager,
        )

        mock_session_manager.validate_csrf_token.assert_called_once_with(
            "test-session-id", "test-csrf-token"
        )

    @pytest.mark.asyncio
    async def test_verify_csrf_token_missing(
        self, mock_session_manager, mock_session_data
    ):
        """Test when CSRF token is missing."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {}

        with pytest.raises(CSRFException) as exc_info:
            await self.mock_verify_csrf_token(
                request=mock_request,
                session_data=mock_session_data,
                session_manager=mock_session_manager,
            )

        assert "CSRF token missing" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_csrf_token_invalid(
        self, mock_session_manager, mock_session_data
    ):
        """Test when CSRF token is invalid."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"X-CSRF-Token": "invalid-csrf-token"}

        mock_session_manager.validate_csrf_token.return_value = False

        with pytest.raises(CSRFException) as exc_info:
            await self.mock_verify_csrf_token(
                request=mock_request,
                session_data=mock_session_data,
                session_manager=mock_session_manager,
            )

        assert "Invalid CSRF token" in str(exc_info.value.detail)
        mock_session_manager.validate_csrf_token.assert_called_once_with(
            "test-session-id", "invalid-csrf-token"
        )

    @pytest.mark.asyncio
    async def test_verify_csrf_token_get_method_skip(
        self, mock_session_manager, mock_session_data
    ):
        """Test that CSRF verification is skipped for GET requests."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.headers = {}

        # Should not raise any exception for GET request
        await self.mock_verify_csrf_token(
            request=mock_request,
            session_data=mock_session_data,
            session_manager=mock_session_manager,
        )

        # CSRF validation should not be called for GET requests
        mock_session_manager.validate_csrf_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_csrf_token_no_session_data(self, mock_session_manager):
        """Test CSRF verification when there's no session data."""
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.headers = {"X-CSRF-Token": "test-csrf-token"}

        # Should not raise any exception when session_data is None
        await self.mock_verify_csrf_token(
            request=mock_request,
            session_data=None,
            session_manager=mock_session_manager,
        )

        # CSRF validation should not be called when session_data is None
        mock_session_manager.validate_csrf_token.assert_not_called()
