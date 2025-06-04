# Event System API Reference

The CRUDAdmin event system provides comprehensive audit logging and event tracking for admin operations. This system automatically logs admin actions, authentication events, and security-related activities with full audit trails.

## Core Components

### Event Types and Status

::: crudadmin.event.schemas.EventType
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.schemas.EventStatus
    rendering:
      show_if_no_docstring: true

### Model Creation Functions

::: crudadmin.event.models.create_admin_event_log
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.models.create_admin_audit_log
    rendering:
      show_if_no_docstring: true

## Event Service

The main service class for managing event logging and retrieval.

::: crudadmin.event.service.EventService
    rendering:
      show_if_no_docstring: true

## Event System Integration

High-level integration class for simplified event logging.

::: crudadmin.event.integration.EventSystemIntegration
    rendering:
      show_if_no_docstring: true

## Decorators

Convenient decorators for automatic event logging.

::: crudadmin.event.decorators.log_admin_action
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.decorators.log_auth_action
    rendering:
      show_if_no_docstring: true

## Event Schemas

### Event Log Schemas

::: crudadmin.event.schemas.AdminEventLogBase
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.schemas.AdminEventLogCreate
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.schemas.AdminEventLogRead
    rendering:
      show_if_no_docstring: true

### Audit Log Schemas

::: crudadmin.event.schemas.AdminAuditLogBase
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.schemas.AdminAuditLogCreate
    rendering:
      show_if_no_docstring: true

::: crudadmin.event.schemas.AdminAuditLogRead
    rendering:
      show_if_no_docstring: true

## Usage Examples

### Basic Event Logging

```python
from crudadmin.event import EventService, EventType, EventStatus

# Initialize event service
event_service = EventService(db_config)

# Log a successful login
await event_service.log_event(
    db=db,
    event_type=EventType.LOGIN,
    status=EventStatus.SUCCESS,
    user_id=user.id,
    session_id=session_id,
    request=request,
    details={"login_method": "password"}
)
```

### Automatic Event Logging with Decorators

```python
from crudadmin.event import log_admin_action, EventType

@log_admin_action(EventType.CREATE, model=User)
async def create_user_endpoint(
    request: Request,
    db: AsyncSession,
    admin_db: AsyncSession,
    current_user: User,
    event_integration=None,
    user_data: UserCreate
):
    # Create user logic here
    user = await create_user(db, user_data)
    return user
```

### Model Event Integration

```python
from crudadmin.event import EventSystemIntegration

# Initialize integration
event_integration = EventSystemIntegration(event_service)

# Log model changes
await event_integration.log_model_event(
    db=admin_db,
    event_type=EventType.UPDATE,
    model=Product,
    user_id=current_user.id,
    session_id=session_id,
    request=request,
    resource_id=str(product.id),
    previous_state={"name": "Old Name", "price": 10.00},
    new_state={"name": "New Name", "price": 15.00},
    details={"field_changed": "name, price"}
)
```

### Querying Event History

```python
# Get user activity
activity = await event_service.get_user_activity(
    db=admin_db,
    user_id=user.id,
    start_time=datetime.now() - timedelta(days=7),
    limit=100
)

# Get resource audit history
history = await event_service.get_resource_history(
    db=admin_db,
    resource_type="Product",
    resource_id="123",
    limit=50
)
```

## Event Configuration

### Enabling Event Tracking

```python
from crudadmin import CRUDAdmin

# Enable event tracking
crud_admin = CRUDAdmin(
    track_events=True,
    session_backend="database",  # Required for event storage
    secret_key="your-secret-key"
)
```

### Custom Event Details

Events can include custom details for additional context:

```python
await event_service.log_event(
    db=admin_db,
    event_type=EventType.CREATE,
    status=EventStatus.SUCCESS,
    user_id=user.id,
    session_id=session_id,
    request=request,
    resource_type="Product",
    resource_id="123",
    details={
        "category": "electronics",
        "bulk_operation": True,
        "import_batch_id": "batch_001",
        "validation_warnings": ["price_below_cost"]
    }
)
```

## Event Model Fields

### AdminEventLog Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `timestamp` | datetime | When the event occurred |
| `event_type` | EventType | Type of event (CREATE, UPDATE, DELETE, LOGIN, etc.) |
| `status` | EventStatus | Event status (SUCCESS, FAILURE, WARNING) |
| `user_id` | int | ID of the user who performed the action |
| `session_id` | str | Session ID for the request |
| `ip_address` | str | IP address of the client |
| `user_agent` | str | User agent string from the request |
| `resource_type` | str | Type of resource affected (model name) |
| `resource_id` | str | ID of the specific resource |
| `details` | dict | Additional event-specific details |

### AdminAuditLog Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `event_id` | int | Reference to AdminEventLog |
| `timestamp` | datetime | When the audit record was created |
| `resource_type` | str | Type of resource (model name) |
| `resource_id` | str | ID of the specific resource |
| `action` | str | Action performed (create, update, delete) |
| `previous_state` | dict | State before the change |
| `new_state` | dict | State after the change |
| `changes` | dict | Computed differences between states |
| `audit_metadata` | dict | Additional audit metadata |

## Security Considerations

### Event Integrity

- Events are stored in append-only fashion
- Original event records are never modified
- All changes maintain full audit trails
- Events include request context for security analysis

### Data Privacy

- Sensitive fields can be excluded from audit logs
- Password fields are automatically excluded
- PII can be masked or hashed in event details
- Event retention policies can be implemented

### Performance Impact

- Event logging is asynchronous where possible
- Failed event logging doesn't interrupt main operations
- Database indexes optimize event querying
- Cleanup routines prevent unbounded growth

## Error Handling

The event system includes robust error handling:

```python
try:
    await event_service.log_event(...)
except Exception as e:
    # Event logging failure doesn't interrupt main operation
    logger.error(f"Event logging failed: {e}")
    # Continue with main business logic
```

## Monitoring and Alerting

### High-Priority Events

```python
await event_integration.log_security_event(
    db=admin_db,
    event_type=EventType.FAILED_LOGIN,
    user_id=user.id,
    session_id=session_id,
    request=request,
    details={
        "priority": "high",
        "requires_attention": True,
        "failed_attempts": 5,
        "suspicious_activity": True
    }
)
```

### Event Metrics

Use event data for monitoring:

- Failed login attempt patterns
- Admin activity volume
- Resource modification frequency
- User behavior analysis

The event system provides a complete audit trail for compliance, security monitoring, and operational insights into your CRUDAdmin instance. 