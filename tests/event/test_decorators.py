from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from crudadmin.event.decorators import (
    compare_states,
    convert_user_to_dict,
    get_model_changes,
    log_admin_action,
    log_auth_action,
)
from crudadmin.event.models import EventType

UTC = timezone.utc


class MockUser:
    """Mock user class for testing convert_user_to_dict."""

    def __init__(self, user_id: int, username: str, email: str = None):
        self.id = user_id
        self.username = username
        self.email = email
        self._private_attr = "should_be_ignored"


class MockPydanticUser:
    """Mock Pydantic-like user class with dict() method."""

    def __init__(self, user_id: int, username: str, email: str = None):
        self.id = user_id
        self.username = username
        self.email = email

    def dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
        }


class MockModel:
    """Mock SQLAlchemy model for testing."""

    __name__ = "MockModel"
    __tablename__ = "test_model"


@pytest.fixture
def mock_request():
    """Create a mock request for testing."""
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.url.path = "/api/test"
    request.headers = {"user-agent": "test-agent"}
    request.client.host = "127.0.0.1"
    request.cookies = {"session_id": "test-session-id"}
    request.json = AsyncMock(return_value={"ids": [1, 2, 3]})
    request.state = MagicMock()
    return request


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_admin_db():
    """Create a mock admin database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_event_integration():
    """Create a mock event integration."""
    integration = MagicMock()
    integration.log_model_event = AsyncMock()
    integration.log_auth_event = AsyncMock()
    return integration


class TestGetModelChanges:
    """Test get_model_changes function."""

    def test_get_model_changes_empty_dict(self):
        """Test get_model_changes with empty dictionary."""
        result = get_model_changes({})
        assert result == {}

    def test_get_model_changes_with_datetime(self):
        """Test get_model_changes with datetime values."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        model_dict = {
            "id": 1,
            "name": "test",
            "created_at": dt,
        }

        result = get_model_changes(model_dict)

        assert result["id"] == 1
        assert result["name"] == "test"
        assert result["created_at"] == dt.isoformat()

    def test_get_model_changes_without_datetime(self):
        """Test get_model_changes with non-datetime values."""
        model_dict = {
            "id": 1,
            "name": "test",
            "price": 99.99,
            "active": True,
        }

        result = get_model_changes(model_dict)

        assert result == model_dict

    def test_get_model_changes_mixed_types(self):
        """Test get_model_changes with mixed data types."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        model_dict = {
            "id": 1,
            "name": "test",
            "created_at": dt,
            "price": 99.99,
            "active": True,
            "metadata": {"key": "value"},
        }

        result = get_model_changes(model_dict)

        assert result["id"] == 1
        assert result["name"] == "test"
        assert result["created_at"] == dt.isoformat()
        assert result["price"] == 99.99
        assert result["active"] is True
        assert result["metadata"] == {"key": "value"}


class TestCompareStates:
    """Test compare_states function."""

    def test_compare_states_both_none(self):
        """Test compare_states with both states None."""
        result = compare_states(None, None)
        assert result == {}

    def test_compare_states_old_none(self):
        """Test compare_states with old state None."""
        new_state = {"id": 1, "name": "test"}
        result = compare_states(None, new_state)
        assert result == {}

    def test_compare_states_new_none(self):
        """Test compare_states with new state None."""
        old_state = {"id": 1, "name": "test"}
        result = compare_states(old_state, None)
        assert result == {}

    def test_compare_states_no_changes(self):
        """Test compare_states with identical states."""
        old_state = {"id": 1, "name": "test", "active": True}
        new_state = {"id": 1, "name": "test", "active": True}

        result = compare_states(old_state, new_state)
        assert result == {}

    def test_compare_states_with_changes(self):
        """Test compare_states with different states."""
        old_state = {"id": 1, "name": "old_name", "active": True}
        new_state = {"id": 1, "name": "new_name", "active": False}

        result = compare_states(old_state, new_state)

        assert "name" in result
        assert result["name"]["old"] == "old_name"
        assert result["name"]["new"] == "new_name"
        assert "active" in result
        assert result["active"]["old"] is True
        assert result["active"]["new"] is False

    def test_compare_states_added_fields(self):
        """Test compare_states with added fields in new state."""
        old_state = {"id": 1, "name": "test"}
        new_state = {"id": 1, "name": "test", "email": "test@example.com"}

        result = compare_states(old_state, new_state)

        assert "email" in result
        assert result["email"]["old"] is None
        assert result["email"]["new"] == "test@example.com"

    def test_compare_states_removed_fields(self):
        """Test compare_states with removed fields from old state."""
        old_state = {"id": 1, "name": "test", "email": "test@example.com"}
        new_state = {"id": 1, "name": "test"}

        result = compare_states(old_state, new_state)

        assert "email" in result
        assert result["email"]["old"] == "test@example.com"
        assert result["email"]["new"] is None


class TestConvertUserToDict:
    """Test convert_user_to_dict function."""

    def test_convert_user_to_dict_with_dict(self):
        """Test convert_user_to_dict with dictionary input."""
        user_dict = {"id": 1, "username": "testuser", "email": "test@example.com"}
        result = convert_user_to_dict(user_dict)
        assert result == user_dict

    def test_convert_user_to_dict_with_pydantic_like_object(self):
        """Test convert_user_to_dict with Pydantic-like object."""
        user = MockPydanticUser(1, "testuser", "test@example.com")
        result = convert_user_to_dict(user)

        expected = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
        }
        assert result == expected

    def test_convert_user_to_dict_with_object_having_dict_attr(self):
        """Test convert_user_to_dict with object having __dict__ attribute."""
        user = MockUser(1, "testuser", "test@example.com")
        result = convert_user_to_dict(user)

        assert result["id"] == 1
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert "_private_attr" not in result

    def test_convert_user_to_dict_with_minimal_object(self):
        """Test convert_user_to_dict with object having minimal attributes."""
        user = MagicMock()
        user.id = 1
        user.username = "testuser"
        del user.dict  # Remove dict method if exists
        del user.__dict__  # Remove __dict__ attribute if exists

        result = convert_user_to_dict(user)

        assert result["id"] == 1
        assert result["username"] == "testuser"

    def test_convert_user_to_dict_with_object_no_attributes(self):
        """Test convert_user_to_dict with object having no expected attributes."""

        class NoDictUser:
            __slots__ = ()

        user = NoDictUser()

        result = convert_user_to_dict(user)

        assert result["id"] is None
        assert result["username"] is None


class TestLogAdminActionDecorator:
    """Test log_admin_action decorator."""

    @pytest.mark.asyncio
    async def test_log_admin_action_create_event(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator with CREATE event."""
        user = {"id": 1, "username": "testuser"}

        @log_admin_action(EventType.CREATE, MockModel)
        async def test_function(request, db, admin_db, current_user, **kwargs):
            return {"id": 123, "name": "created_item"}

        # Mock the CRUD result on request.state
        mock_request.state.crud_result = MagicMock()
        mock_request.state.crud_result.__dict__ = {
            "id": 123,
            "name": "created_item",
            "_private": "ignored",
        }

        result = await test_function(
            request=mock_request,
            db=mock_db,
            admin_db=mock_admin_db,
            current_user=user,
            event_integration=mock_event_integration,
        )

        assert result == {"id": 123, "name": "created_item"}
        mock_event_integration.log_model_event.assert_called_once()
        mock_admin_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_admin_action_update_event(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator with UPDATE event."""
        user = {"id": 1, "username": "testuser"}

        @log_admin_action(EventType.UPDATE, MockModel)
        async def test_function(request, db, admin_db, current_user, id, **kwargs):
            return {"id": id, "name": "updated_item"}

        # Mock FastCRUD operations
        with patch("crudadmin.event.decorators.FastCRUD") as mock_crud_class:
            mock_crud = AsyncMock()
            mock_crud_class.return_value = mock_crud

            # Mock previous state
            mock_crud.get.side_effect = [
                {"id": 123, "name": "old_item"},  # Previous state
                {"id": 123, "name": "updated_item"},  # New state
            ]

            result = await test_function(
                request=mock_request,
                db=mock_db,
                admin_db=mock_admin_db,
                current_user=user,
                event_integration=mock_event_integration,
                id=123,
            )

            assert result == {"id": 123, "name": "updated_item"}
            mock_event_integration.log_model_event.assert_called_once()
            mock_admin_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_admin_action_delete_event(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator with DELETE event."""
        user = {"id": 1, "username": "testuser"}

        @log_admin_action(EventType.DELETE, MockModel)
        async def test_function(request, db, admin_db, current_user, **kwargs):
            return {"message": "deleted"}

        # Mock deleted records on request.state
        mock_request.state.deleted_records = [
            {"id": 1, "name": "item1"},
            {"id": 2, "name": "item2"},
        ]

        # Mock bulk delete URL
        mock_request.url.path = "/api/test/bulk-delete"

        with patch("crudadmin.event.decorators.FastCRUD") as mock_crud_class:
            mock_crud = AsyncMock()
            mock_crud_class.return_value = mock_crud
            mock_crud.get.return_value = {"id": 123, "name": "item_to_delete"}

            result = await test_function(
                request=mock_request,
                db=mock_db,
                admin_db=mock_admin_db,
                current_user=user,
                event_integration=mock_event_integration,
                id=123,
            )

            assert result == {"message": "deleted"}
            mock_event_integration.log_model_event.assert_called_once()

            # Verify delete-specific details were logged
            call_args = mock_event_integration.log_model_event.call_args[1]
            assert "deleted_records" in call_args["new_state"]
            assert "deletion_details" in call_args["new_state"]

    @pytest.mark.asyncio
    async def test_log_admin_action_no_event_integration(
        self, mock_request, mock_db, mock_admin_db
    ):
        """Test log_admin_action decorator without event integration."""
        user = {"id": 1, "username": "testuser"}

        @log_admin_action(EventType.CREATE, MockModel)
        async def test_function(request, db, admin_db, current_user, **kwargs):
            return {"id": 123, "name": "created_item"}

        result = await test_function(
            request=mock_request,
            db=mock_db,
            admin_db=mock_admin_db,
            current_user=user,
            event_integration=None,
        )

        assert result == {"id": 123, "name": "created_item"}
        # No event should be logged
        mock_admin_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_admin_action_no_current_user(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator without current user."""

        @log_admin_action(EventType.CREATE, MockModel)
        async def test_function(request, db, admin_db, current_user, **kwargs):
            return {"id": 123, "name": "created_item"}

        result = await test_function(
            request=mock_request,
            db=mock_db,
            admin_db=mock_admin_db,
            current_user=None,
            event_integration=mock_event_integration,
        )

        assert result == {"id": 123, "name": "created_item"}
        # No event should be logged without user
        mock_event_integration.log_model_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_admin_action_exception_in_logging(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator when logging raises exception."""
        user = {"id": 1, "username": "testuser"}
        mock_event_integration.log_model_event.side_effect = Exception("Logging failed")

        @log_admin_action(EventType.CREATE, MockModel)
        async def test_function(request, db, admin_db, current_user, **kwargs):
            return {"id": 123, "name": "created_item"}

        mock_request.state.crud_result = MagicMock()
        mock_request.state.crud_result.__dict__ = {"id": 123, "name": "created_item"}

        # Should not raise exception, but should still return result
        result = await test_function(
            request=mock_request,
            db=mock_db,
            admin_db=mock_admin_db,
            current_user=user,
            event_integration=mock_event_integration,
        )

        assert result == {"id": 123, "name": "created_item"}

    @pytest.mark.asyncio
    async def test_log_admin_action_model_none_error(
        self, mock_request, mock_db, mock_admin_db, mock_event_integration
    ):
        """Test log_admin_action decorator with None model raises error for UPDATE/DELETE."""
        user = {"id": 1, "username": "testuser"}

        @log_admin_action(EventType.UPDATE, None)
        async def test_function(request, db, admin_db, current_user, id, **kwargs):
            return {"id": id, "name": "updated_item"}

        with pytest.raises(ValueError, match="Model must not be None"):
            await test_function(
                request=mock_request,
                db=mock_db,
                admin_db=mock_admin_db,
                current_user=user,
                event_integration=mock_event_integration,
                id=123,
            )


class TestLogAuthActionDecorator:
    """Test log_auth_action decorator."""

    @pytest.mark.asyncio
    async def test_log_auth_action_login_success(
        self, mock_request, mock_db, mock_event_integration
    ):
        """Test log_auth_action decorator with successful LOGIN."""

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, form_data=None, **kwargs):
            request.state.user = {"id": 1, "username": "testuser"}
            # Mock response with session cookie
            response = MagicMock()
            response.headers = {}
            response.raw_headers = [
                (b"set-cookie", b"session_id=test-session-123; Path=/; HttpOnly")
            ]
            return response

        form_data = MagicMock()
        form_data.username = "testuser"

        await test_login(
            request=mock_request,
            db=mock_db,
            event_integration=mock_event_integration,
            form_data=form_data,
        )

        mock_event_integration.log_auth_event.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify auth event details
        call_args = mock_event_integration.log_auth_event.call_args[1]
        assert call_args["event_type"] == EventType.LOGIN
        assert call_args["user_id"] == 1
        assert call_args["success"] is True

    @pytest.mark.asyncio
    async def test_log_auth_action_login_failure(
        self, mock_request, mock_db, mock_event_integration
    ):
        """Test log_auth_action decorator with failed LOGIN."""

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, form_data=None, **kwargs):
            # No user set on request.state indicates failure
            return {"error": "Invalid credentials"}

        # Explicitly set user to None to simulate failed login
        mock_request.state.user = None

        form_data = MagicMock()
        form_data.username = "testuser"

        await test_login(
            request=mock_request,
            db=mock_db,
            event_integration=mock_event_integration,
            form_data=form_data,
        )

        mock_event_integration.log_auth_event.assert_called_once()

        # Verify auth event details for failure
        call_args = mock_event_integration.log_auth_event.call_args[1]
        assert call_args["event_type"] == EventType.LOGIN
        assert call_args["user_id"] == 0  # Default for failed login
        assert call_args["success"] is False

    @pytest.mark.asyncio
    async def test_log_auth_action_logout(
        self, mock_request, mock_db, mock_event_integration
    ):
        """Test log_auth_action decorator with LOGOUT."""

        @log_auth_action(EventType.LOGOUT)
        async def test_logout(request, db, **kwargs):
            request.state.user = {"id": 1, "username": "testuser"}
            return {"message": "Logged out successfully"}

        await test_logout(
            request=mock_request,
            db=mock_db,
            event_integration=mock_event_integration,
        )

        mock_event_integration.log_auth_event.assert_called_once()

        # Verify logout event details
        call_args = mock_event_integration.log_auth_event.call_args[1]
        assert call_args["event_type"] == EventType.LOGOUT
        assert call_args["user_id"] == 1
        assert call_args["success"] is True
        assert call_args["session_id"] == "test-session-id"

    @pytest.mark.asyncio
    async def test_log_auth_action_no_event_integration(self, mock_request, mock_db):
        """Test log_auth_action decorator without event integration."""

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, **kwargs):
            return {"message": "Login successful"}

        result = await test_login(
            request=mock_request,
            db=mock_db,
            event_integration=None,
        )

        assert result == {"message": "Login successful"}
        # No event should be logged
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_auth_action_exception_in_logging(
        self, mock_request, mock_db, mock_event_integration
    ):
        """Test log_auth_action decorator when logging raises exception."""
        mock_event_integration.log_auth_event.side_effect = Exception("Logging failed")

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, **kwargs):
            request.state.user = {"id": 1, "username": "testuser"}
            return {"message": "Login successful"}

        # Should raise the exception from logging
        with pytest.raises(Exception, match="Logging failed"):
            await test_login(
                request=mock_request,
                db=mock_db,
                event_integration=mock_event_integration,
            )

    @pytest.mark.asyncio
    async def test_log_auth_action_session_extraction_from_cookie(
        self, mock_request, mock_db, mock_event_integration
    ):
        """Test log_auth_action decorator extracting session from response headers."""

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, **kwargs):
            request.state.user = {"id": 1, "username": "testuser"}
            response = MagicMock()
            response.raw_headers = [
                (b"content-type", b"application/json"),
                (b"set-cookie", b"session_id=extracted-session-456; Path=/; HttpOnly"),
                (b"other-header", b"other-value"),
            ]
            return response

        await test_login(
            request=mock_request,
            db=mock_db,
            event_integration=mock_event_integration,
        )

        mock_event_integration.log_auth_event.assert_called_once()

        # Verify the extracted session ID
        call_args = mock_event_integration.log_auth_event.call_args[1]
        assert call_args["session_id"] == "extracted-session-456"

    @pytest.mark.asyncio
    async def test_log_auth_action_no_client_ip(self, mock_db, mock_event_integration):
        """Test log_auth_action decorator when request has no client info."""
        # Create request without client
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/auth/login"
        request.headers = {"user-agent": "test-agent"}
        request.cookies = {"session_id": "test-session-id"}
        request.client = None  # No client info
        request.state = MagicMock()

        @log_auth_action(EventType.LOGIN)
        async def test_login(request, db, **kwargs):
            request.state.user = {"id": 1, "username": "testuser"}
            return {"message": "Login successful"}

        await test_login(
            request=request,
            db=mock_db,
            event_integration=mock_event_integration,
        )

        mock_event_integration.log_auth_event.assert_called_once()

        # Verify IP address is set to "unknown"
        call_args = mock_event_integration.log_auth_event.call_args[1]
        assert call_args["details"]["request_details"]["ip_address"] == "unknown"
