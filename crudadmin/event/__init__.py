from .models import (
    EventType,
    EventStatus,
    create_admin_event_log,
    create_admin_audit_log,
)
from .schemas import (
    AdminEventLogCreate,
    AdminEventLogRead,
    AdminAuditLogCreate,
    AdminAuditLogRead,
)
from .service import EventService
from .integration import EventSystemIntegration
from .decorators import log_admin_action, log_auth_action

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
