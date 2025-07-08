from datetime import datetime, timezone
from unittest.mock import Mock

from sqlalchemy.orm import DeclarativeBase

from crudadmin.event.models import create_admin_audit_log, create_admin_event_log
from crudadmin.event.schemas import EventType

UTC = timezone.utc


class MockBase(DeclarativeBase):
    """Mock base class for testing."""

    pass


class TestCreateAdminEventLog:
    """Test cases for create_admin_event_log function."""

    def test_create_admin_event_log_basic_functionality(self):
        """Test basic functionality of create_admin_event_log."""
        base = MockBase
        EventLogModel = create_admin_event_log(base)

        assert EventLogModel.__name__ == "AdminEventLog"
        assert EventLogModel.__tablename__ == "admin_event_log"
        assert issubclass(EventLogModel, base)
        assert hasattr(EventLogModel, "__table_args__")
        assert EventLogModel.__table_args__ == {"extend_existing": True}

    def test_create_admin_event_log_has_all_required_fields(self):
        """Test that AdminEventLog has all required fields with correct types."""
        base = MockBase
        EventLogModel = create_admin_event_log(base)

        # Check field existence and types
        for field in EventLogModel.__table__.columns:
            assert hasattr(EventLogModel, field.key)

    def test_create_admin_event_log_repr_method(self):
        """Test __repr__ method of AdminEventLog."""
        base = MockBase
        EventLogModel = create_admin_event_log(base)

        # Create an instance to test repr
        instance = EventLogModel()
        instance.id = 1
        instance.event_type = EventType.CREATE
        instance.user_id = 123

        repr_str = repr(instance)
        assert "AdminEventLog" in repr_str
        assert "id=1" in repr_str
        assert "event_type=create" in repr_str  # Enum value is stored as string
        assert "user_id=123" in repr_str

    def test_create_admin_event_log_returns_existing_class(self):
        """Test that function returns existing class when already in registry."""
        base = MockBase

        # Create the first instance
        EventLogModel1 = create_admin_event_log(base)

        # Create the second instance - should return the same class
        EventLogModel2 = create_admin_event_log(base)

        assert EventLogModel1 is EventLogModel2
        assert EventLogModel1.__name__ == "AdminEventLog"
        assert EventLogModel2.__name__ == "AdminEventLog"

    def test_create_admin_event_log_with_base_without_registry(self):
        """Test function behavior when base class doesn't have registry."""

        class BaseWithoutRegistry:
            pass

        EventLogModel = create_admin_event_log(BaseWithoutRegistry)

        assert EventLogModel.__name__ == "AdminEventLog"
        assert EventLogModel.__tablename__ == "admin_event_log"
        assert issubclass(EventLogModel, BaseWithoutRegistry)


class TestCreateAdminAuditLog:
    """Test cases for create_admin_audit_log function."""

    def test_create_admin_audit_log_basic_functionality(self):
        """Test basic functionality of create_admin_audit_log."""
        base = MockBase
        AuditLogModel = create_admin_audit_log(base)

        assert AuditLogModel.__name__ == "AdminAuditLog"
        assert AuditLogModel.__tablename__ == "admin_audit_log"
        assert issubclass(AuditLogModel, base)
        assert hasattr(AuditLogModel, "__table_args__")
        assert AuditLogModel.__table_args__ == {"extend_existing": True}

    def test_create_admin_audit_log_has_all_required_fields(self):
        """Test that AdminAuditLog has all required fields."""
        base = MockBase
        AuditLogModel = create_admin_audit_log(base)

        # Check field existence
        for field in AuditLogModel.__table__.columns:
            assert hasattr(AuditLogModel, field.key)

    def test_create_admin_audit_log_repr_method(self):
        """Test __repr__ method of AdminAuditLog."""
        base = MockBase
        AuditLogModel = create_admin_audit_log(base)

        # Create an instance to test repr
        instance = AuditLogModel()
        instance.id = 1
        instance.resource_type = "user"
        instance.resource_id = "123"

        repr_str = repr(instance)
        assert "AdminAuditLog" in repr_str
        assert "id=1" in repr_str
        assert "resource_type=user" in repr_str
        assert "resource_id=123" in repr_str

    def test_create_admin_audit_log_returns_existing_class(self):
        """Test that function returns existing class when already in registry."""
        base = MockBase

        # Create the first instance
        AuditLogModel1 = create_admin_audit_log(base)

        # Create the second instance - should return the same class
        AuditLogModel2 = create_admin_audit_log(base)

        assert AuditLogModel1 is AuditLogModel2
        assert AuditLogModel1.__name__ == "AdminAuditLog"
        assert AuditLogModel2.__name__ == "AdminAuditLog"

    def test_create_admin_audit_log_with_base_without_registry(self):
        """Test function behavior when base class doesn't have registry."""

        class BaseWithoutRegistry:
            pass

        AuditLogModel = create_admin_audit_log(BaseWithoutRegistry)

        assert AuditLogModel.__name__ == "AdminAuditLog"
        assert AuditLogModel.__tablename__ == "admin_audit_log"
        assert issubclass(AuditLogModel, BaseWithoutRegistry)


class TestModelIntegration:
    """Integration tests for both model creation functions."""

    def test_both_models_can_be_created_with_same_base(self):
        """Test that both models can be created with the same base class."""
        base = MockBase

        EventLogModel = create_admin_event_log(base)
        AuditLogModel = create_admin_audit_log(base)

        assert EventLogModel.__name__ == "AdminEventLog"
        assert AuditLogModel.__name__ == "AdminAuditLog"
        assert issubclass(EventLogModel, base)
        assert issubclass(AuditLogModel, base)
        assert EventLogModel is not AuditLogModel

    def test_models_have_different_table_names(self):
        """Test that models have different table names."""
        base = MockBase

        EventLogModel = create_admin_event_log(base)
        AuditLogModel = create_admin_audit_log(base)

        assert EventLogModel.__tablename__ != AuditLogModel.__tablename__
        assert EventLogModel.__tablename__ == "admin_event_log"
        assert AuditLogModel.__tablename__ == "admin_audit_log"

    def test_models_timestamp_default_behavior(self):
        """Test timestamp default behavior for both models."""
        base = MockBase

        EventLogModel = create_admin_event_log(base)
        AuditLogModel = create_admin_audit_log(base)

        # Test that timestamp columns have default values
        event_timestamp = EventLogModel.__table__.columns.get("timestamp")
        audit_timestamp = AuditLogModel.__table__.columns.get("timestamp")

        assert event_timestamp.default is not None
        assert audit_timestamp.default is not None

        # Test that default can be called to generate current UTC time
        # Using a mock context as the lambda expects it
        mock_ctx = Mock()

        event_default_value = event_timestamp.default.arg(mock_ctx)
        audit_default_value = audit_timestamp.default.arg(mock_ctx)

        assert isinstance(event_default_value, datetime)
        assert isinstance(audit_default_value, datetime)
        assert event_default_value.tzinfo == UTC
        assert audit_default_value.tzinfo == UTC
