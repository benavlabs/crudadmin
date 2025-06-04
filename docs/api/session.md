# Session Management API Reference

The CRUDAdmin session management system provides secure, scalable session handling with multiple backend options and comprehensive security features including CSRF protection, session expiration, and device tracking.

## Core Components

### Session Manager

The main session management class that handles all session operations.

::: crudadmin.session.manager.SessionManager
    rendering:
      show_if_no_docstring: true

### Session Storage Backends

#### Abstract Base Class

::: crudadmin.session.storage.AbstractSessionStorage
    rendering:
      show_if_no_docstring: true

#### Storage Factory

::: crudadmin.session.storage.get_session_storage
    rendering:
      show_if_no_docstring: true

### Session Storage Implementations

#### Memory Storage

::: crudadmin.session.backends.memory.MemorySessionStorage
    rendering:
      show_if_no_docstring: true

#### Redis Storage

::: crudadmin.session.backends.redis.RedisSessionStorage
    rendering:
      show_if_no_docstring: true

#### Memcached Storage

::: crudadmin.session.backends.memcached.MemcachedSessionStorage
    rendering:
      show_if_no_docstring: true

#### Database Storage

::: crudadmin.session.backends.database.DatabaseSessionStorage
    rendering:
      show_if_no_docstring: true

#### Hybrid Storage

::: crudadmin.session.backends.hybrid.HybridSessionStorage
    rendering:
      show_if_no_docstring: true

## Session Schemas

### Core Session Data

::: crudadmin.session.schemas.SessionData
    rendering:
      show_if_no_docstring: true

::: crudadmin.session.schemas.SessionCreate
    rendering:
      show_if_no_docstring: true

### CSRF Protection

::: crudadmin.session.schemas.CSRFToken
    rendering:
      show_if_no_docstring: true

### User Agent Information

::: crudadmin.session.schemas.UserAgentInfo
    rendering:
      show_if_no_docstring: true

### Database Session Models

::: crudadmin.session.schemas.AdminSessionCreate
    rendering:
      show_if_no_docstring: true

::: crudadmin.session.schemas.AdminSessionRead
    rendering:
      show_if_no_docstring: true

::: crudadmin.session.schemas.AdminSessionUpdate
    rendering:
      show_if_no_docstring: true

## Usage Examples

### Basic Session Management

```python
from crudadmin.session.manager import SessionManager
from crudadmin.session.storage import get_session_storage

# Create session manager with memory backend
session_manager = SessionManager(
    session_backend="memory",
    max_sessions_per_user=5,
    session_timeout_minutes=30
)

# Create a new session
session_id, csrf_token = await session_manager.create_session(
    request=request,
    user_id=user.id,
    metadata={"role": "admin", "permissions": ["read", "write"]}
)

# Validate session
session_data = await session_manager.validate_session(session_id)
if session_data:
    print(f"Valid session for user {session_data.user_id}")
```

### Redis Backend Configuration

```python
# Configure with Redis for production
session_manager = SessionManager(
    session_backend="redis",
    redis_host="localhost",
    redis_port=6379,
    redis_db=0,
    redis_password="your-redis-password",
    max_sessions_per_user=10,
    session_timeout_minutes=60
)
```

### Database Backend for Audit Trail

```python
from your_app.database import DatabaseConfig

# Configure with database backend for admin visibility
db_config = DatabaseConfig(...)  # Your database configuration

session_manager = SessionManager(
    session_backend="database",
    db_config=db_config,
    max_sessions_per_user=5,
    session_timeout_minutes=30
)
```

### Hybrid Backend (Best of Both Worlds)

```python
# Hybrid: Redis for performance + Database for audit
session_manager = SessionManager(
    session_backend="hybrid",
    db_config=db_config,
    redis_host="localhost",
    redis_port=6379,
    max_sessions_per_user=10,
    session_timeout_minutes=60
)
```

### CSRF Protection

```python
# Validate CSRF token for state-changing operations
is_valid = await session_manager.validate_csrf_token(
    csrf_token=request.headers.get("X-CSRF-Token"),
    session_id=session_id,
    user_id=current_user.id
)

if not is_valid:
    raise HTTPException(status_code=403, detail="Invalid CSRF token")
```

### Session Cleanup

```python
# Cleanup expired sessions (should be called periodically)
await session_manager.cleanup_expired_sessions()

# Terminate specific session
await session_manager.terminate_session(session_id)

# Terminate all user sessions
await session_manager.terminate_user_sessions(user_id)
```

## Backend Comparison

| Backend | Performance | Scalability | Persistence | Admin Visibility | Use Case |
|---------|-------------|-------------|-------------|------------------|----------|
| **Memory** | Excellent | Single node | No | No | Development, testing |
| **Redis** | Excellent | Horizontal | Yes* | No | Production, high traffic |
| **Memcached** | Excellent | Horizontal | No | No | High performance caching |
| **Database** | Good | Vertical | Yes | Yes | Audit requirements |
| **Hybrid** | Excellent | Horizontal | Yes | Yes | Best of all worlds |

*Redis persistence depends on configuration

## Security Features

### Session Security

```python
# Session manager provides multiple security layers
session_manager = SessionManager(
    # Limit concurrent sessions per user
    max_sessions_per_user=5,
    
    # Automatic session expiration
    session_timeout_minutes=30,
    
    # CSRF protection
    csrf_token_bytes=32,
    
    # Login rate limiting
    login_max_attempts=5,
    login_window_minutes=15
)
```

### Device Tracking

Sessions automatically track device information:

```python
# Device info is automatically parsed and stored
session_data = await session_manager.validate_session(session_id)
device_info = session_data.device_info

print(f"Browser: {device_info['browser']}")
print(f"OS: {device_info['os']}")
print(f"Mobile: {device_info['is_mobile']}")
```

### IP Address Monitoring

```python
# Sessions track IP addresses for security monitoring
session_data = await session_manager.validate_session(session_id)
print(f"Session from IP: {session_data.ip_address}")

# Detect IP changes (potential session hijacking)
if session_data.ip_address != request.client.host:
    # Handle potential security issue
    await session_manager.terminate_session(session_id)
```

## Configuration Options

### Session Manager Settings

```python
session_manager = SessionManager(
    # Storage configuration
    session_backend="redis",
    redis_host="localhost",
    redis_port=6379,
    redis_db=0,
    redis_password=None,
    
    # Session limits
    max_sessions_per_user=5,
    session_timeout_minutes=30,
    
    # Cleanup
    cleanup_interval_minutes=15,
    
    # CSRF
    csrf_token_bytes=32,
    
    # Rate limiting
    login_max_attempts=5,
    login_window_minutes=15
)
```

### Backend-Specific Options

#### Redis Configuration

```python
redis_storage = get_session_storage(
    backend="redis",
    model_type=SessionData,
    host="localhost",
    port=6379,
    db=0,
    password="your-password",
    pool_size=10,
    connect_timeout=10,
    prefix="session:",
    expiration=1800  # 30 minutes
)
```

#### Database Configuration

```python
database_storage = get_session_storage(
    backend="database",
    model_type=SessionData,
    db_config=your_db_config,
    prefix="session:",
    expiration=1800
)
```

## Integration with CRUDAdmin

### Automatic Session Management

```python
from crudadmin import CRUDAdmin

# CRUDAdmin automatically creates and manages sessions
crud_admin = CRUDAdmin(
    # Session backend configuration
    session_backend="redis",
    redis_url="redis://localhost:6379",
    
    # Session settings
    session_timeout=30,  # minutes
    max_sessions_per_user=5,
    
    # Security
    secret_key="your-secret-key",
    csrf_protection=True
)
```

### Custom Session Storage

```python
# Use custom session storage
custom_storage = YourCustomSessionStorage()

crud_admin = CRUDAdmin(
    session_storage=custom_storage,
    secret_key="your-secret-key"
)
```

## Session Data Structure

### SessionData Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | int | ID of the authenticated user |
| `session_id` | str | Unique session identifier |
| `ip_address` | str | IP address when session was created |
| `user_agent` | str | User agent string from browser |
| `device_info` | dict | Parsed device/browser information |
| `created_at` | datetime | When the session was created |
| `last_activity` | datetime | Last time session was validated |
| `is_active` | bool | Whether the session is active |
| `metadata` | dict | Additional session-specific data |

### Device Information

```python
device_info = {
    "browser": "Chrome",
    "browser_version": "120.0.0.0",
    "os": "Windows",
    "device": "PC",
    "is_mobile": False,
    "is_tablet": False,
    "is_pc": True
}
```

## Error Handling

### Session Validation Errors

```python
try:
    session_data = await session_manager.validate_session(session_id)
    if not session_data:
        # Session not found, expired, or inactive
        raise HTTPException(status_code=401, detail="Invalid session")
except Exception as e:
    logger.error(f"Session validation error: {e}")
    raise HTTPException(status_code=500, detail="Session validation failed")
```

### Backend Connection Errors

```python
try:
    await session_manager.create_session(request, user_id)
except ConnectionError:
    # Backend (Redis/Memcached) unavailable
    # Fallback to memory storage or return error
    pass
except Exception as e:
    logger.error(f"Session creation failed: {e}")
    raise
```

## Performance Considerations

### Session Cleanup

```python
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Schedule periodic cleanup
scheduler = AsyncIOScheduler()
scheduler.add_job(
    session_manager.cleanup_expired_sessions,
    'interval',
    minutes=15,
    id='session_cleanup'
)
scheduler.start()
```

### Connection Pooling

```python
# Redis with connection pooling
redis_storage = get_session_storage(
    backend="redis",
    model_type=SessionData,
    host="localhost",
    port=6379,
    pool_size=20,  # Increase pool size for high traffic
    connect_timeout=10
)
```

### Session Limits

```python
# Prevent memory exhaustion
session_manager = SessionManager(
    max_sessions_per_user=10,  # Limit per user
    session_timeout_minutes=30,  # Auto-expire
    cleanup_interval_minutes=15  # Regular cleanup
)
```

## Monitoring and Debugging

### Session Metrics

```python
# Get active session count for user
user_sessions = await session_manager.get_user_sessions(user_id)
print(f"User has {len(user_sessions)} active sessions")

# Monitor session activity
session_data = await session_manager.validate_session(session_id)
if session_data:
    session_age = datetime.now(UTC) - session_data.last_activity
    print(f"Session last active {session_age} ago")
```

### Debug Information

```python
# Enable detailed logging
import logging
logging.getLogger('crudadmin.session').setLevel(logging.DEBUG)

# Session data includes debug information
print(f"Session metadata: {session_data.metadata}")
print(f"Device info: {session_data.device_info}")
```

The session management system provides a robust, secure foundation for authentication in CRUDAdmin with flexibility to scale from development to production environments. 