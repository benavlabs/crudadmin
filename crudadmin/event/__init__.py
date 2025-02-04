from .decorators import log_admin_action, log_auth_action
from .integration import EventSystemIntegration
from .models import (
    EventStatus,
    EventType,
    create_admin_audit_log,
    create_admin_event_log,
)
from .schemas import (
    AdminAuditLogCreate,
    AdminAuditLogRead,
    AdminEventLogCreate,
    AdminEventLogRead,
)
from .service import EventService

__all__ = [
    "EventType",
    "EventStatus",
    "create_admin_event_log",
    "create_admin_audit_log",
    "AdminEventLogCreate",
    "AdminEventLogRead",
    "AdminAuditLogCreate",
    "AdminAuditLogRead",
    "EventService",
    "EventSystemIntegration",
    "log_admin_action",
    "log_auth_action",
]


def init_event_system(db_config):
    """Initialize the event system with the given database configuration."""
    event_service = EventService(db_config)
    event_integration = EventSystemIntegration(event_service)

    return event_service, event_integration
