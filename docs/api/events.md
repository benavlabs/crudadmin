# Event System API Reference

With `track_events=True`, CRUDAdmin records what admins do: logins, logouts, refused logins, lockouts, and every create, update and delete made through the interface. Superusers read the log on the Event Logs page.

## How Events Are Recorded

**Authentication events** come from [crudauth](https://github.com/benavlabs/crudauth) hooks:

| Event | Type | Status |
|---|---|---|
| Successful login | `LOGIN` | `SUCCESS` |
| Logout | `LOGOUT` | `SUCCESS` |
| Wrong password, unknown or inactive admin | `FAILED_LOGIN` | `FAILURE` |
| Login refused by the lockout | `FAILED_LOGIN` | `FAILURE`, with `reason: "lockout"` in the details |

The username tried is stored under `details.username`, which is what `EventService.get_security_alerts` groups failed logins by. A hook that fails is logged and doesn't affect the login.

**Model events** are recorded by the create, update and bulk-delete routes through `admin.events`, once they know the outcome:

- `SUCCESS` once the change is committed; `FAILURE` when it is refused (invalid input, a record that doesn't exist, a constraint the database enforces). A refused change writes no audit rows, since nothing changed.
- A create writes one audit row with the new record; an update, one with the record before and after and the fields that changed. Both are keyed by the model's primary key, whatever its name.
- A delete writes one audit row per deleted record, holding the record as it was.
- The event and its audit rows are written in one transaction. If any write fails, they're rolled back together, logged, and the admin's change itself still stands.

**Stored values**:

- `session_id` holds the session's public handle, never the session id itself.
- Values under credential-like keys (any key containing `password`, `secret`, `token`, `session_id` or `api_key`) are stored as `[redacted]`, in event details, audit snapshots, change sets and audit metadata alike. A changed password still shows up as a change.
- Request details are stored in the event's `details` and in the audit row's `audit_metadata`.
- Before 0.7, event details and audit metadata weren't redacted. The Event Logs page redacts the details of those older events when it shows them; the rows themselves are unchanged.

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

The service that writes and queries events and audit rows.

::: crudadmin.event.service.EventService
    rendering:
      show_if_no_docstring: true

## Event System Integration

Writes an event together with its audit rows.

::: crudadmin.event.integration.EventSystemIntegration
    rendering:
      show_if_no_docstring: true

## Recording Changes

::: crudadmin.event.recorder.AdminEvents
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

### Enabling Event Tracking

```python
from crudadmin import CRUDAdmin

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    track_events=True,
)
```

The event tables are created in the admin database by `admin.initialize()`, whichever session backend you use. `admin.event_service` and `admin.event_integration` give access to the service and the integration.

### Logging an Event Yourself

```python
from crudadmin.event import EventStatus, EventType

await admin.event_service.log_event(
    db=admin_db,
    event_type=EventType.CREATE,
    status=EventStatus.SUCCESS,
    user_id=user.id,
    session_id=session_handle,
    request=request,
    resource_type="Product",
    resource_id="123",
    details={"import_batch_id": "batch_001"},
)
```

`log_event` commits unless you pass `commit=False`; `create_audit_log` takes the same flag, so an event and its audit rows can share a transaction.

### Logging a Model Change with Its Audit Row

```python
await admin.event_integration.log_model_event(
    db=admin_db,
    event_type=EventType.UPDATE,
    model=Product,
    user_id=current_user.id,
    session_id=session_handle,
    request=request,
    resource_id=str(product.id),
    previous_state={"name": "Old Name", "price": 10.00},
    new_state={"name": "New Name", "price": 15.00},
)
```

For a delete, pass the deleted records and the primary key's name instead of `resource_id`: `deleted_records=[...]`, `primary_key_name="sku"`. Pass `succeeded=False` to record a failed action without audit rows.

### Recording Changes from Your Own Routes

A route of your own can record the changes it makes the way the admin's routes do. `admin.events.record` reads the admin and the session from the request, which the admin's login dependency sets:

```python
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from crudadmin.event import EventType


@router.post(
    "/products/{sku}/restock",
    dependencies=[Depends(admin.admin_authentication.get_current_user())],
)
async def restock(
    sku: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin_db: AsyncSession = Depends(admin.db_config.get_admin_db),
):
    before = await product_as_dict(db, sku)
    await add_stock(db, sku, 10)
    await db.commit()
    await admin.events.record(
        request,
        admin_db,
        EventType.UPDATE,
        Product,
        record_id=sku,
        before=before,
        after=await product_as_dict(db, sku),
    )
```

Pass `after=` for a create, `before=` and `after=` for an update, and `deleted=[...]` with the removed records for a delete; `succeeded=False` records a refused change. With `track_events=False`, `record` does nothing.

### Querying Event History

```python
activity = await admin.event_service.get_user_activity(
    db=admin_db,
    user_id=user.id,
    start_time=datetime.now(timezone.utc) - timedelta(days=7),
    limit=100,
)

history = await admin.event_service.get_resource_history(
    db=admin_db,
    resource_type="Product",
    resource_id="123",
    limit=50,
)

alerts = await admin.event_service.get_security_alerts(db=admin_db, lookback_hours=24)
```

## Event Model Fields

### AdminEventLog Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `timestamp` | datetime | When the event occurred |
| `event_type` | EventType | `create`, `update`, `delete`, `login`, `logout` or `failed_login` |
| `status` | EventStatus | `success`, `failure` or `warning` |
| `user_id` | int | The admin who acted; `0` when a refused login named no account |
| `session_id` | str | The session's public handle |
| `ip_address` | str | Client IP address |
| `user_agent` | str | User agent string from the request |
| `resource_type` | str | Model name, for model events |
| `resource_id` | str | Primary key of the record, for creates and updates |
| `details` | dict | Event-specific details |

### AdminAuditLog Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `event_id` | int | The `AdminEventLog` row this belongs to |
| `timestamp` | datetime | When the audit row was written |
| `resource_type` | str | Model name |
| `resource_id` | str | Primary key of the record |
| `action` | str | `create`, `update` or `delete` |
| `previous_state` | dict | The record before the change (redacted) |
| `new_state` | dict | The record after the change (redacted) |
| `changes` | dict | Fields that changed, with old and new values (redacted) |
| `audit_metadata` | dict | Request details |

## Retention

`EventService.cleanup_old_logs(db, retention_days=90)` deletes older events. Schedule it if the log shouldn't grow without bound.
