from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from crudadmin.event.integration import EventSystemIntegration
from crudadmin.event.models import EventStatus, EventType
from crudadmin.event.service import EventService

UTC = timezone.utc


class MockModel:
    """Mock SQLAlchemy model for testing."""

    __name__ = "MockModel"
    __tablename__ = "test_model"


class MockEventLogModel:
    """Mock event log model returned by EventService."""

    def __init__(self, event_id: int = 1):
        self.id = event_id
        self.event_type = EventType.CREATE
        self.status = EventStatus.SUCCESS
        self.user_id = 1
        self.session_id = "test-session"
        self.timestamp = datetime.now(UTC)


@pytest.fixture
def mock_request():
    """Create a mock request for testing."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.url.path = "/api/test"
    request.headers = {"user-agent": "test-agent"}
    request.client.host = "127.0.0.1"
    request.cookies = {"session_id": "test-session-id"}
    return request


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_event_service():
    """Create a mock event service."""
    return AsyncMock(spec=EventService)


@pytest.fixture
def event_integration(mock_event_service):
    """Create an EventSystemIntegration instance."""
    return EventSystemIntegration(mock_event_service)


class TestEventSystemIntegrationInit:
    """Test EventSystemIntegration initialization."""

    def test_initialization(self, mock_event_service):
        """Test EventSystemIntegration initialization."""
        integration = EventSystemIntegration(mock_event_service)
        assert integration.event_service == mock_event_service


class TestLogModelEvent:
    """Test log_model_event method."""

    @pytest.mark.asyncio
    async def test_log_model_event_success_without_audit(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful model event logging without audit log creation."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.LOGIN,  # Not a CRUD event
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id="123",
            details={"action": "login"},
        )

        # Verify event logging was called
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.LOGIN,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_type="MockModel",
            resource_id="123",
            details={"action": "login"},
        )

        # Verify audit log was NOT created (LOGIN is not a CRUD event)
        event_integration.event_service.create_audit_log.assert_not_called()

        # Verify database commit
        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_success_with_audit_create(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful model event logging with audit log creation for CREATE event."""
        mock_event = MockEventLogModel(event_id=1)
        event_integration.event_service.log_event.return_value = mock_event

        previous_state = {"id": 1, "name": "old_name"}
        new_state = {"id": 1, "name": "new_name"}
        details = {"action": "create"}

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.CREATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id="123",
            previous_state=previous_state,
            new_state=new_state,
            details=details,
        )

        # Verify event logging was called
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.CREATE,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_type="MockModel",
            resource_id="123",
            details=details,
        )

        # Verify audit log was created
        event_integration.event_service.create_audit_log.assert_called_once_with(
            db=mock_db,
            event_id=1,
            resource_type="MockModel",
            resource_id="123",
            action="create",
            previous_state=previous_state,
            new_state=new_state,
            metadata=details,
        )

        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_success_with_audit_update(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful model event logging with audit log creation for UPDATE event."""
        mock_event = MockEventLogModel(event_id=2)
        event_integration.event_service.log_event.return_value = mock_event

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.UPDATE,
            model=MockModel,
            user_id=2,
            session_id="test-session-2",
            request=mock_request,
            resource_id="456",
        )

        # Verify audit log was created for UPDATE event
        event_integration.event_service.create_audit_log.assert_called_once_with(
            db=mock_db,
            event_id=2,
            resource_type="MockModel",
            resource_id="456",
            action="update",
            previous_state=None,
            new_state=None,
            metadata=None,
        )

        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_success_with_audit_delete(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful model event logging with audit log creation for DELETE event."""
        mock_event = MockEventLogModel(event_id=3)
        event_integration.event_service.log_event.return_value = mock_event

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.DELETE,
            model=MockModel,
            user_id=3,
            session_id="test-session-3",
            request=mock_request,
            resource_id="789",
        )

        # Verify audit log was created for DELETE event
        event_integration.event_service.create_audit_log.assert_called_once_with(
            db=mock_db,
            event_id=3,
            resource_type="MockModel",
            resource_id="789",
            action="delete",
            previous_state=None,
            new_state=None,
            metadata=None,
        )

        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_no_resource_id_no_audit(
        self, event_integration, mock_db, mock_request
    ):
        """Test model event logging without resource_id - should not create audit log."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.CREATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id=None,  # No resource ID
        )

        # Verify event logging was called with None resource_id
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.CREATE,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_type="MockModel",
            resource_id=None,
            details=None,
        )

        # Verify audit log was NOT created (no resource_id)
        event_integration.event_service.create_audit_log.assert_not_called()

        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_no_event_returned_no_audit(
        self, event_integration, mock_db, mock_request
    ):
        """Test model event logging when no event is returned - should not create audit log."""
        event_integration.event_service.log_event.return_value = None

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.CREATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id="123",
        )

        # Verify audit log was NOT created (no event returned)
        event_integration.event_service.create_audit_log.assert_not_called()

        mock_db.commit.assert_called_once()
        assert result is None

    @pytest.mark.asyncio
    async def test_log_model_event_with_integer_resource_id(
        self, event_integration, mock_db, mock_request
    ):
        """Test model event logging with integer resource_id - should convert to string."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.UPDATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id=123,  # Integer resource ID
        )

        # Verify resource_id was converted to string
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.UPDATE,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_type="MockModel",
            resource_id="123",  # Should be converted to string
            details=None,
        )

        # Verify audit log was created with string resource_id
        event_integration.event_service.create_audit_log.assert_called_once_with(
            db=mock_db,
            event_id=1,
            resource_type="MockModel",
            resource_id="123",  # Should be converted to string
            action="update",
            previous_state=None,
            new_state=None,
            metadata=None,
        )

        mock_db.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_model_event_exception_in_log_event(
        self, event_integration, mock_db, mock_request
    ):
        """Test exception handling in log_event call."""
        event_integration.event_service.log_event.side_effect = Exception(
            "Database error"
        )

        with patch("crudadmin.event.integration.logger") as mock_logger:
            with pytest.raises(Exception, match="Database error"):
                await event_integration.log_model_event(
                    db=mock_db,
                    event_type=EventType.CREATE,
                    model=MockModel,
                    user_id=1,
                    session_id="test-session",
                    request=mock_request,
                )

            # Verify error was logged
            mock_logger.error.assert_called_once_with(
                "Error in event logging: Database error"
            )

            # Verify rollback was called
            mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_model_event_exception_in_audit_log(
        self, event_integration, mock_db, mock_request
    ):
        """Test exception handling in create_audit_log call."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event
        event_integration.event_service.create_audit_log.side_effect = Exception(
            "Audit error"
        )

        with patch("crudadmin.event.integration.logger") as mock_logger:
            with pytest.raises(Exception, match="Audit error"):
                await event_integration.log_model_event(
                    db=mock_db,
                    event_type=EventType.CREATE,
                    model=MockModel,
                    user_id=1,
                    session_id="test-session",
                    request=mock_request,
                    resource_id="123",
                )

            # Verify error was logged
            mock_logger.error.assert_called_once_with(
                "Error in event logging: Audit error"
            )

            # Verify rollback was called
            mock_db.rollback.assert_called_once()


class TestLogAuthEvent:
    """Test log_auth_event method."""

    @pytest.mark.asyncio
    async def test_log_auth_event_success(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful authentication event logging."""
        details = {"username": "testuser", "ip": "127.0.0.1"}

        await event_integration.log_auth_event(
            db=mock_db,
            event_type=EventType.LOGIN,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            success=True,
            details=details,
        )

        # Verify event logging was called with SUCCESS status
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.LOGIN,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=details,
        )

    @pytest.mark.asyncio
    async def test_log_auth_event_failure(
        self, event_integration, mock_db, mock_request
    ):
        """Test authentication event logging for failure."""
        details = {"username": "testuser", "reason": "invalid_password"}

        await event_integration.log_auth_event(
            db=mock_db,
            event_type=EventType.FAILED_LOGIN,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            success=False,
            details=details,
        )

        # Verify event logging was called with FAILURE status
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.FAILED_LOGIN,
            status=EventStatus.FAILURE,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=details,
        )

    @pytest.mark.asyncio
    async def test_log_auth_event_without_details(
        self, event_integration, mock_db, mock_request
    ):
        """Test authentication event logging without details."""
        await event_integration.log_auth_event(
            db=mock_db,
            event_type=EventType.LOGOUT,
            user_id=2,
            session_id="test-session-2",
            request=mock_request,
            success=True,
            details=None,
        )

        # Verify event logging was called with None details
        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.LOGOUT,
            status=EventStatus.SUCCESS,
            user_id=2,
            session_id="test-session-2",
            request=mock_request,
            details=None,
        )

    @pytest.mark.asyncio
    async def test_log_auth_event_exception_handling(
        self, event_integration, mock_db, mock_request
    ):
        """Test exception handling in authentication event logging."""
        event_integration.event_service.log_event.side_effect = Exception(
            "Auth logging error"
        )

        with patch("crudadmin.event.integration.logger") as mock_logger:
            # Should not raise exception, just log it
            await event_integration.log_auth_event(
                db=mock_db,
                event_type=EventType.LOGIN,
                user_id=1,
                session_id="test-session",
                request=mock_request,
                success=True,
            )

            # Verify error was logged with exc_info=True
            mock_logger.error.assert_called_once_with(
                "Error logging auth event: Auth logging error", exc_info=True
            )


class TestLogSecurityEvent:
    """Test log_security_event method."""

    @pytest.mark.asyncio
    async def test_log_security_event_success(
        self, event_integration, mock_db, mock_request
    ):
        """Test successful security event logging."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        details = {
            "threat_type": "brute_force",
            "attempts": 5,
            "blocked_ip": "192.168.1.100",
        }

        result = await event_integration.log_security_event(
            db=mock_db,
            event_type=EventType.FAILED_LOGIN,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=details,
        )

        # Verify event logging was called with WARNING status and enhanced details
        expected_details = {**details, "priority": "high", "requires_attention": True}

        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.FAILED_LOGIN,
            status=EventStatus.WARNING,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=expected_details,
        )

        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_security_event_with_existing_priority(
        self, event_integration, mock_db, mock_request
    ):
        """Test security event logging when details already contain priority."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        details = {
            "threat_type": "sql_injection",
            "priority": "medium",  # Existing priority
            "payload": "'; DROP TABLE users; --",
        }

        result = await event_integration.log_security_event(
            db=mock_db,
            event_type=EventType.CREATE,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=details,
        )

        # Verify priority was overridden to "high"
        expected_details = {**details, "priority": "high", "requires_attention": True}

        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.CREATE,
            status=EventStatus.WARNING,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details=expected_details,
        )

        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_security_event_empty_details(
        self, event_integration, mock_db, mock_request
    ):
        """Test security event logging with empty details dictionary."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        details = {}

        result = await event_integration.log_security_event(
            db=mock_db,
            event_type=EventType.UPDATE,
            user_id=2,
            session_id="test-session-2",
            request=mock_request,
            details=details,
        )

        # Verify security metadata was added to empty details
        expected_details = {"priority": "high", "requires_attention": True}

        event_integration.event_service.log_event.assert_called_once_with(
            db=mock_db,
            event_type=EventType.UPDATE,
            status=EventStatus.WARNING,
            user_id=2,
            session_id="test-session-2",
            request=mock_request,
            details=expected_details,
        )

        assert result == mock_event

    @pytest.mark.asyncio
    async def test_log_security_event_exception_handling(
        self, event_integration, mock_db, mock_request
    ):
        """Test exception handling in security event logging."""
        event_integration.event_service.log_event.side_effect = Exception(
            "Security logging error"
        )

        details = {"threat_type": "xss_attempt"}

        with patch("crudadmin.event.integration.logger") as mock_logger:
            with pytest.raises(Exception, match="Security logging error"):
                await event_integration.log_security_event(
                    db=mock_db,
                    event_type=EventType.CREATE,
                    user_id=1,
                    session_id="test-session",
                    request=mock_request,
                    details=details,
                )

            # Verify error was logged with exc_info=True
            mock_logger.error.assert_called_once_with(
                "Error logging security event: Security logging error", exc_info=True
            )


class TestEventSystemIntegrationEdgeCases:
    """Test edge cases and integration scenarios."""

    @pytest.mark.asyncio
    async def test_log_model_event_with_complex_states(
        self, event_integration, mock_db, mock_request
    ):
        """Test model event logging with complex state objects."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        # Complex state objects with nested data
        previous_state = {
            "id": 1,
            "user": {"name": "John", "roles": ["admin", "user"]},
            "metadata": {"created_by": "system", "version": 1},
        }
        new_state = {
            "id": 1,
            "user": {"name": "John", "roles": ["admin", "user", "moderator"]},
            "metadata": {"created_by": "system", "version": 2},
        }

        result = await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.UPDATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id="complex-123",
            previous_state=previous_state,
            new_state=new_state,
        )

        # Verify audit log was created with complex states
        event_integration.event_service.create_audit_log.assert_called_once_with(
            db=mock_db,
            event_id=1,
            resource_type="MockModel",
            resource_id="complex-123",
            action="update",
            previous_state=previous_state,
            new_state=new_state,
            metadata=None,
        )

        assert result == mock_event

    @pytest.mark.asyncio
    async def test_multiple_event_logging_sequence(
        self, event_integration, mock_db, mock_request
    ):
        """Test logging multiple different types of events in sequence."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        # Log a model event
        await event_integration.log_model_event(
            db=mock_db,
            event_type=EventType.CREATE,
            model=MockModel,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            resource_id="1",
        )

        # Log an auth event
        await event_integration.log_auth_event(
            db=mock_db,
            event_type=EventType.LOGIN,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            success=True,
        )

        # Log a security event
        await event_integration.log_security_event(
            db=mock_db,
            event_type=EventType.FAILED_LOGIN,
            user_id=1,
            session_id="test-session",
            request=mock_request,
            details={"suspicious_activity": True},
        )

        # Verify all event service calls were made
        assert event_integration.event_service.log_event.call_count == 3
        assert event_integration.event_service.create_audit_log.call_count == 1
        assert mock_db.commit.call_count == 1  # Only for model event

    @pytest.mark.asyncio
    async def test_log_model_event_all_event_types_audit_coverage(
        self, event_integration, mock_db, mock_request
    ):
        """Test that audit logs are only created for CREATE, UPDATE, DELETE events."""
        mock_event = MockEventLogModel()
        event_integration.event_service.log_event.return_value = mock_event

        # Test each event type
        crud_events = [EventType.CREATE, EventType.UPDATE, EventType.DELETE]
        non_crud_events = [EventType.LOGIN, EventType.LOGOUT, EventType.FAILED_LOGIN]

        # Test CRUD events - should create audit logs
        for event_type in crud_events:
            event_integration.event_service.create_audit_log.reset_mock()

            await event_integration.log_model_event(
                db=mock_db,
                event_type=event_type,
                model=MockModel,
                user_id=1,
                session_id="test-session",
                request=mock_request,
                resource_id="123",
            )

            # Should create audit log for CRUD events
            event_integration.event_service.create_audit_log.assert_called_once()

        # Test non-CRUD events - should NOT create audit logs
        for event_type in non_crud_events:
            event_integration.event_service.create_audit_log.reset_mock()

            await event_integration.log_model_event(
                db=mock_db,
                event_type=event_type,
                model=MockModel,
                user_id=1,
                session_id="test-session",
                request=mock_request,
                resource_id="123",
            )

            # Should NOT create audit log for non-CRUD events
            event_integration.event_service.create_audit_log.assert_not_called()
