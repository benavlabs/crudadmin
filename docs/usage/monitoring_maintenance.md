# Monitoring Your Admin Interface

Every admin interface needs proper monitoring - you need to know who's making changes, when they're making them, and whether your system is healthy. In this guide, we'll walk through setting up monitoring for your CRUDAdmin interface and learn how to effectively use these monitoring tools.

## Setting Up Event Tracking

Let's start with the most important monitoring feature: event tracking. Imagine you need to know who changed a user's role last week, or why certain records were updated. Event tracking gives you this visibility.

### Enabling Event Tracking

First, let's enable event tracking in your admin interface:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True,
    # Store events in a separate database to keep your main DB clean
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create your application's database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface with event tracking
    # This will create necessary event tracking tables
    await admin.initialize()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

Pro tip: Using a separate database for logs helps keep your main application database lean and prevents log entries from impacting your app's performance. The `initialize()` call will create the necessary event tracking tables in your specified admin database.

### What Gets Tracked?

Once initialized with event tracking enabled, CRUDAdmin automatically tracks key events. Let's look at some real examples:

1. When someone logs in:
```python
{
    "timestamp": "2024-02-01T09:15:23+00:00",
    "user": "sarah.admin",
    "ip_address": "10.0.0.1",
    "event_type": "auth.login",
    "status": "success"
}
```

2. When a user record is updated:
```python
{
    "timestamp": "2024-02-01T15:23:45+00:00",
    "user": "john.manager",
    "ip_address": "10.0.0.2",
    "event_type": "record.update",
    "resource": "users",
    "resource_id": 456,
    "changes": {
        "role": {
            "old": "user",
            "new": "admin"
        }
    }
}
```

## Using the Health Dashboard

The health dashboard is your window into the system's current state. You can find it at `/admin/management/health`. Let's understand what each part tells you:

### Reading Health Status

Here's what a typical health check looks like:
```python
{
    "database": {
        "status": "healthy",
        "latency_ms": 5.23,
        "active_connections": 12
    },
    "session_management": {
        "status": "healthy",
        "active_sessions": 8,
        "cleanup_status": "ok"
    }
}
```

Let's break down what to look for:

1. **Database Health**
    - `latency_ms`: Should typically be under 100ms
    - `active_connections`: Watch for unusually high numbers

2. **Session Management**
    - `active_sessions`: Unusual spikes might indicate issues
    - `cleanup_status`: Should always be "ok"

## Working with Event Logs

The event log interface at `/admin/management/events` is where you'll spend most of your monitoring time. Let's walk through some common scenarios:

### Scenario 1: Investigating Changes

Suppose a user reports their account details were changed. Here's how to investigate:

1. Go to `/admin/management/events`
2. Filter by:
   - Resource type: "users"
   - Event type: "record.update"
   - Time period: Last 24 hours

You'll see all user record changes, including who made them and exactly what changed.

### Scenario 2: Security Audit

For a security audit, you might need to review all login attempts:

1. Filter by event type: "auth.login"
2. Look for:
   - Failed login attempts from the same IP
   - Successful logins at unusual hours
   - Login attempts for disabled accounts

## Maintaining Your System

### Regular Cleanup

To keep your system running smoothly, set up regular session cleanup:

```python
@app.on_event("startup")
async def schedule_cleanup():
    # Clean expired sessions
    await admin.session_manager.cleanup_expired_sessions()
```

### Database Connection Management

For better database performance, configure your connection pool:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Adjust these based on your application's needs
    pool_size=20,          # Maximum number of connections
    max_overflow=10,       # Extra connections if needed
    pool_timeout=30        # How long to wait for a connection
)
```

## Daily Monitoring Routine

Here's a practical daily routine for monitoring your admin interface:

1. **Morning Check (Start of Day)**
    - Open the health dashboard
    - Verify all systems show "healthy"
    - Check active session count

2. **Security Review**
    - Review failed login attempts
    - Check for unusual activity patterns
    - Verify no unexpected permission changes

3. **System Maintenance**
    - Confirm session cleanup is running
    - Check database connection stats
    - Review event log storage usage

## Troubleshooting Common Issues

### High Database Latency

If you see high `latency_ms` values:

1. Check your database connection pool settings
2. Look for long-running queries in your event logs
3. Consider if you need to optimize your queries

### Session Management Issues

If `active_sessions` seems too high:

1. Verify your session cleanup is running
2. Check for stuck or abandoned sessions
3. Look for any authentication service issues

---

With these monitoring practices in place, you'll be well-equipped to:

- Track all important changes in your system
- Spot potential issues before they become problems
- Maintain a healthy admin interface
- Respond quickly to security concerns

Remember: Regular monitoring is key to maintaining a stable and secure admin interface. Make checking your health dashboard and event logs part of your daily routine.