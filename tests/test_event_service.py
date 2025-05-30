import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from crudadmin.event.schemas import (
    AdminAuditLogRead,
    AdminEventLogRead,
    EventStatus,
    EventType,
)
from crudadmin.event.service import CustomJSONEncoder, EventService


class SampleEnum(Enum):
    TEST_VALUE = "test"


@pytest.mark.asyncio
async def test_event_service_initialization(event_service):
    """Test EventService initialization."""
    assert event_service.db_config is not None
    assert event_service.crud_events is not None
    assert event_service.crud_audits is not None
    assert isinstance(event_service.json_encoder, CustomJSONEncoder)


def test_custom_json_encoder():
    """Test CustomJSONEncoder functionality."""
    encoder = CustomJSONEncoder()

    # Test datetime encoding
    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert encoder.default(dt) == dt.isoformat()

    # Test Decimal encoding
    decimal_val = Decimal("123.45")
    assert encoder.default(decimal_val) == "123.45"

    # Test Enum encoding
    enum_val = SampleEnum.TEST_VALUE
    assert encoder.default(enum_val) == "test"

    # Test unknown type (should raise TypeError)
    with pytest.raises(TypeError):
        encoder.default(object())


@pytest.mark.asyncio
async def test_serialize_dict(event_service):
    """Test _serialize_dict method."""
    # Test with None
    result = event_service._serialize_dict(None)
    assert result == {}

    # Test with empty dict
    result = event_service._serialize_dict({})
    assert result == {}

    # Test with complex data
    data = {
        "datetime": datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
        "decimal": Decimal("123.45"),
        "enum": SampleEnum.TEST_VALUE,
        "string": "test",
        "number": 42,
    }

    result = event_service._serialize_dict(data)
    assert isinstance(result, dict)
    assert "datetime" in result
    assert "decimal" in result
    assert "enum" in result


@pytest.mark.asyncio
async def test_log_event_success(event_service, mock_request):
    """Test successful event logging."""
    user_id = 1
    session_id = "test-session-id"
    event_type = EventType.LOGIN
    status = EventStatus.SUCCESS
    resource_type = "user"
    resource_id = "123"
    details = {"action": "login", "timestamp": datetime.now(UTC)}

    # Mock the crud_events.create method
    mock_event_result = {
        "id": 1,
        "event_type": event_type,
        "status": status,
        "user_id": user_id,
        "session_id": session_id,
        "ip_address": "127.0.0.1",
        "user_agent": "test-agent",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "timestamp": datetime.now(UTC),
    }

    with patch.object(
        event_service.crud_events, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_event_result

        result = await event_service.log_event(
            db=AsyncMock(),
            event_type=event_type,
            status=status,
            user_id=user_id,
            session_id=session_id,
            request=mock_request,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )

        assert isinstance(result, AdminEventLogRead)
        assert result.event_type == event_type
        assert result.status == status
        assert result.user_id == user_id
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_log_event_with_model_result(event_service, mock_request):
    """Test event logging when crud returns a model object."""
    user_id = 1
    session_id = "test-session-id"
    event_type = EventType.CREATE
    status = EventStatus.SUCCESS

    class MockEventModel:
        def __init__(self):
            self.id = 1
            self.event_type = event_type
            self.status = status
            self.user_id = user_id
            self.session_id = session_id
            self.ip_address = "127.0.0.1"
            self.user_agent = "test-agent"
            self.resource_type = None
            self.resource_id = None
            self.details = {}
            self.timestamp = datetime.now(UTC)
            self._private_attr = "should_be_ignored"

    mock_model = MockEventModel()

    with patch.object(
        event_service.crud_events, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_model

        result = await event_service.log_event(
            db=AsyncMock(),
            event_type=event_type,
            status=status,
            user_id=user_id,
            session_id=session_id,
            request=mock_request,
        )

        assert isinstance(result, AdminEventLogRead)
        assert result.event_type == event_type
        assert result.user_id == user_id


@pytest.mark.asyncio
async def test_log_event_exception_handling(event_service, mock_request):
    """Test event logging exception handling."""
    with patch.object(
        event_service.crud_events, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await event_service.log_event(
                db=AsyncMock(),
                event_type=EventType.LOGIN,
                status=EventStatus.FAILURE,
                user_id=1,
                session_id="test-session",
                request=mock_request,
            )


@pytest.mark.asyncio
async def test_create_audit_log_success(event_service):
    """Test successful audit log creation."""
    event_id = 1
    resource_type = "user"
    resource_id = "123"
    action = "update"
    previous_state = {"name": "old_name", "email": "old@example.com"}
    new_state = {"name": "new_name", "email": "new@example.com"}
    metadata = {"updated_by": "admin"}

    mock_audit_result = {
        "id": 1,
        "event_id": event_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "previous_state": previous_state,
        "new_state": new_state,
        "changes": {"name": {"old": "old_name", "new": "new_name"}},
        "metadata": metadata,
        "timestamp": datetime.now(UTC),
    }

    with patch.object(
        event_service.crud_audits, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_audit_result

        result = await event_service.create_audit_log(
            db=AsyncMock(),
            event_id=event_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata,
        )

        assert isinstance(result, AdminAuditLogRead)
        assert result.event_id == event_id
        assert result.resource_type == resource_type
        assert result.action == action
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_audit_log_exception_handling(event_service):
    """Test audit log creation exception handling."""
    with patch.object(
        event_service.crud_audits, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await event_service.create_audit_log(
                db=AsyncMock(),
                event_id=1,
                resource_type="user",
                resource_id="123",
                action="update",
            )


def test_compute_changes(event_service):
    """Test _compute_changes method."""
    result = event_service._compute_changes(None, None)
    assert result == {}

    result = event_service._compute_changes({"key": "value"}, None)
    assert result == {}

    result = event_service._compute_changes(None, {"key": "value"})
    assert result == {}

    # Test with actual changes
    previous_state = {
        "name": "old_name",
        "email": "old@example.com",
        "status": "active",
        "unchanged": "same_value",
    }

    new_state = {
        "name": "new_name",
        "email": "new@example.com",
        "status": "active",
        "unchanged": "same_value",
        "new_field": "new_value",
    }

    result = event_service._compute_changes(previous_state, new_state)

    assert "name" in result
    assert result["name"]["old"] == "old_name"
    assert result["name"]["new"] == "new_name"

    assert "email" in result
    assert result["email"]["old"] == "old@example.com"
    assert result["email"]["new"] == "new@example.com"

    assert "new_field" in result
    assert result["new_field"]["old"] is None
    assert result["new_field"]["new"] == "new_value"

    # Unchanged fields should not be in the result
    assert "status" not in result
    assert "unchanged" not in result


@pytest.mark.asyncio
async def test_get_user_activity(event_service):
    """Test getting user activity logs."""
    user_id = 1
    start_time = datetime.now(UTC) - timedelta(days=1)
    end_time = datetime.now(UTC)
    limit = 25
    offset = 10

    mock_result = {
        "data": [
            {"id": 1, "event_type": "LOGIN", "user_id": user_id},
            {"id": 2, "event_type": "CREATE", "user_id": user_id},
        ],
        "total_count": 2,
    }

    with patch.object(
        event_service.crud_events, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = mock_result

        result = await event_service.get_user_activity(
            db=AsyncMock(),
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

        assert result == mock_result
        mock_get_multi.assert_called_once_with(
            ANY,
            offset=offset,
            limit=limit,
            sort_columns=["timestamp"],
            sort_orders=["desc"],
            user_id=user_id,
            timestamp__gte=start_time,
            timestamp__lte=end_time,
        )


@pytest.mark.asyncio
async def test_get_user_activity_without_time_filters(event_service):
    """Test getting user activity without time filters."""
    user_id = 1

    mock_result = {"data": [], "total_count": 0}

    with patch.object(
        event_service.crud_events, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = mock_result

        result = await event_service.get_user_activity(
            db=AsyncMock(),
            user_id=user_id,
        )

        assert result == mock_result
        mock_get_multi.assert_called_once_with(
            ANY,
            offset=0,
            limit=50,
            sort_columns=["timestamp"],
            sort_orders=["desc"],
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_get_resource_history(event_service):
    """Test getting resource audit history."""
    resource_type = "user"
    resource_id = "123"
    limit = 25
    offset = 5

    mock_result = {
        "data": [
            {"id": 1, "action": "create", "resource_type": resource_type},
            {"id": 2, "action": "update", "resource_type": resource_type},
        ],
        "total_count": 2,
    }

    with patch.object(
        event_service.crud_audits, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = mock_result

        result = await event_service.get_resource_history(
            db=AsyncMock(),
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
            offset=offset,
        )

        assert result == mock_result
        mock_get_multi.assert_called_once_with(
            ANY,
            offset=offset,
            limit=limit,
            sort_columns=["timestamp"],
            sort_orders=["desc"],
            resource_type=resource_type,
            resource_id=resource_id,
        )


@pytest.mark.asyncio
async def test_get_security_alerts(event_service):
    """Test getting security alerts."""
    lookback_hours = 12

    mock_result = {
        "data": [
            {"id": 1, "event_type": "LOGIN", "status": "FAILURE"},
            {"id": 2, "event_type": "UNAUTHORIZED_ACCESS", "status": "FAILURE"},
        ],
        "total_count": 2,
    }

    with patch.object(
        event_service.crud_events, "get_multi", new_callable=AsyncMock
    ) as mock_get_multi:
        mock_get_multi.return_value = mock_result

        result = await event_service.get_security_alerts(
            db=AsyncMock(),
            lookback_hours=lookback_hours,
        )

        assert isinstance(result, list)
        mock_get_multi.assert_called_once()

        # Verify the call includes time filter
        call_args = mock_get_multi.call_args
        assert "timestamp__gte" in call_args[1]


@pytest.mark.asyncio
async def test_cleanup_old_logs(event_service):
    """Test cleanup of old logs."""
    retention_days = 30

    with patch.object(
        event_service.crud_events, "delete", new_callable=AsyncMock
    ) as mock_delete_events, patch.object(
        event_service.crud_audits, "delete", new_callable=AsyncMock
    ) as mock_delete_audits:
        await event_service.cleanup_old_logs(
            db=AsyncMock(),
            retention_days=retention_days,
        )

        # Verify both event and audit logs are cleaned up
        mock_delete_events.assert_called_once()
        mock_delete_audits.assert_called_once()

        # Verify the time filter is applied
        events_call_args = mock_delete_events.call_args
        audits_call_args = mock_delete_audits.call_args

        assert "timestamp__lt" in events_call_args[1]
        assert "timestamp__lt" in audits_call_args[1]


@pytest.mark.asyncio
async def test_log_event_no_client_ip(event_service):
    """Test event logging when request has no client."""
    mock_request = Mock()
    mock_request.client = None
    mock_request.headers = {"user-agent": "test-agent"}

    mock_event_result = {
        "id": 1,
        "event_type": EventType.LOGIN,
        "status": EventStatus.SUCCESS,
        "user_id": 1,
        "session_id": "test-session",
        "ip_address": "unknown",
        "user_agent": "test-agent",
        "resource_type": None,
        "resource_id": None,
        "details": {},
        "timestamp": datetime.now(UTC),
    }

    with patch.object(
        event_service.crud_events, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_event_result

        result = await event_service.log_event(
            db=AsyncMock(),
            event_type=EventType.LOGIN,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="test-session",
            request=mock_request,
        )

        assert isinstance(result, AdminEventLogRead)

        # Verify the create was called with "unknown" IP
        call_args = mock_create.call_args
        event_data = call_args[1]["object"]
        assert event_data.ip_address == "unknown"


@pytest.mark.asyncio
async def test_serialize_dict_with_nested_data(event_service):
    """Test _serialize_dict with nested complex data."""
    nested_data = {
        "level1": {
            "level2": {
                "datetime": datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
                "decimal": Decimal("99.99"),
                "enum": SampleEnum.TEST_VALUE,
            },
            "list": [
                datetime(2023, 1, 2, 12, 0, 0, tzinfo=UTC),
                Decimal("123.45"),
                SampleEnum.TEST_VALUE,
            ],
        },
    }

    result = event_service._serialize_dict(nested_data)
    assert isinstance(result, dict)
    assert "level1" in result

    # The result should be JSON-serializable
    json_str = json.dumps(result)
    assert isinstance(json_str, str)


@pytest.mark.asyncio
async def test_event_service_with_missing_models(db_config):
    """Test EventService initialization when event models are not set."""
    # Remove event models from db_config
    db_config.AdminEventLog = None
    db_config.AdminAuditLog = None

    with pytest.raises(AttributeError):
        EventService(db_config)
