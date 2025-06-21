# Session Backends

CRUDAdmin provides flexible, scalable session management with multiple backend options. This guide covers how to configure and use different session backends for optimal performance and functionality across development, staging, and production environments.

## Prerequisites

Before configuring session backends, ensure you have:

- CRUDAdmin instance created and configured (see [Basic Configuration](configuration.md))
- Understanding of your deployment environment requirements
- Optional: Redis or Memcached installed for production backends

---

## Backend Overview

CRUDAdmin supports five session backend types, each optimized for different use cases:

| Backend | Performance | Scalability | Persistence | Admin Visibility | Dependencies | Use Case |
|---------|-------------|-------------|-------------|------------------|--------------|----------|
| **Memory** | Excellent | Single node | No | No | None | Development, testing |
| **Redis** | Excellent | Horizontal | Yes* | No | Redis server | Production, high traffic |
| **Memcached** | Excellent | Horizontal | No | No | Memcached server | High performance caching |
| **Database** | Good | Vertical | Yes | Yes | None | Audit requirements |
| **Hybrid** | Excellent | Horizontal | Yes | Yes | Redis/Memcached + DB | Production with audit |

*Redis persistence depends on configuration

---

## Memory Sessions

Perfect for development and testing environments with no external dependencies.

### Basic Usage

```python
from crudadmin import CRUDAdmin

# Memory sessions are the default
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key"
)

# Or explicitly configure
admin.use_memory_sessions()
```

### Characteristics

- **Fast**: No network overhead
- **Simple**: No setup required
- **Ephemeral**: Sessions lost on restart
- **Single node**: Not suitable for load-balanced deployments

### When to Use

✅ **Development environments**  
✅ **Testing and CI/CD**  
✅ **Single-node applications**  
❌ **Production with multiple instances**  
❌ **Applications requiring session persistence**

---

## Redis Sessions

Redis provides high-performance session storage with persistence, clustering support, and advanced features like TTL (Time To Live) and Redis ACL authentication.

### Installation

```bash
# Install Redis support
uv add "crudadmin[redis]"
# or with pip
pip install "crudadmin[redis]"
```

### Basic Configuration

```python
# Method 1: URL-based configuration
admin.use_redis_sessions(redis_url="redis://localhost:6379/0")

# Method 2: Parameter-based configuration (recommended)
admin.use_redis_sessions(
    host="localhost",
    port=6379,
    db=0
)
```

### Redis with Authentication

```python
# URL with password
admin.use_redis_sessions(redis_url="redis://user:password@localhost:6379/1")

# Parameters with password (more reliable)
admin.use_redis_sessions(
    host="localhost",
    port=6379,
    db=0,
    password="your-redis-password"
)
```

### Production Redis Configuration

```python
# Environment-based configuration
admin.use_redis_sessions(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    password=os.getenv("REDIS_PASSWORD"),
    pool_size=20,
    connect_timeout=10
)
```

### Advanced Redis Parameters

```python
# Full configuration with all options
admin.use_redis_sessions(
    host="redis-cluster.example.com",
    port=6379,
    db=0,
    password="secure-password",
    
    # Connection pooling
    pool_size=20,
    connect_timeout=10,
    
    # Socket options
    socket_keepalive=True,
    socket_keepalive_options={},
    
    # Additional Redis client options
    connection_pool_kwargs={"retry_on_timeout": True}
)
```

### When to Use

✅ **Production environments**  
✅ **High-traffic applications**  
✅ **Multi-instance deployments**  
✅ **Applications requiring session persistence**  
✅ **Microservices architectures**

### Parameter-Based Configuration

For individual parameter configuration:

```python
from crudadmin import CRUDAdmin

# Basic configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(
    host="localhost",
    port=6379,
    db=0
)

# With authentication (Redis 6.0+ ACL support)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(
    host="redis.example.com",
    port=6379,
    db=1,
    username="myapp_user",      # Redis ACL username
    password="secure_password"
)

# Additional Redis configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(
    host="localhost",
    port=6379,
    db=0,
    username="admin_user",
    password="secret123",
    socket_timeout=30,
    connection_pool_max_connections=50,
    retry_on_timeout=True
)
```

### URL-Based Configuration

Redis URLs support the standard format including usernames:

```python
from crudadmin import CRUDAdmin

# Basic Redis URL
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(redis_url="redis://localhost:6379/0")

# With password only (legacy authentication)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(redis_url="redis://:password123@localhost:6379/0")

# With username and password (Redis 6.0+ ACL)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(redis_url="redis://myuser:password123@redis.example.com:6379/1")

# Complex Redis URL with custom port and database
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
).use_redis_sessions(redis_url="redis://admin_user:secure_pass@redis-cluster.internal:6380/3")
```

### Authentication Methods

Redis supports two authentication methods:

1. **Legacy AUTH (Redis < 6.0)**: Uses only password
   ```python
   # URL format
   admin.use_redis_sessions(redis_url="redis://:password@localhost:6379/0")
   
   # Parameter format
   admin.use_redis_sessions(password="password")
   ```

2. **ACL Authentication (Redis 6.0+)**: Uses username and password
   ```python
   # URL format
   admin.use_redis_sessions(redis_url="redis://username:password@localhost:6379/0")
   
   # Parameter format
   admin.use_redis_sessions(username="username", password="password")
   ```

---

## Memcached Sessions

High-performance caching solution optimized for speed over persistence.

### Installation

```bash
# Install Memcached support
uv add "crudadmin[memcached]"
# or with pip
pip install "crudadmin[memcached]"
```

### Basic Configuration

```python
# Method 1: Server list
admin.use_memcached_sessions(servers=["localhost:11211"])

# Method 2: Individual parameters
admin.use_memcached_sessions(
    host="localhost",
    port=11211
)
```

### Multiple Servers

```python
# Multiple servers (first server used due to aiomcache limitations)
admin.use_memcached_sessions(servers=[
    "memcached1.example.com:11211",
    "memcached2.example.com:11211"  # Backup server
])
```

### Production Memcached Configuration

```python
# Environment-based configuration
admin.use_memcached_sessions(
    host=os.getenv("MEMCACHED_HOST", "localhost"),
    port=int(os.getenv("MEMCACHED_PORT", 11211)),
    pool_size=15,
    timeout=10
)
```

### When to Use

✅ **High-performance requirements**  
✅ **Applications with simple session needs**  
✅ **Existing Memcached infrastructure**  
❌ **Applications requiring session persistence**  
❌ **Audit requirements**

---

## Database Sessions

Store sessions directly in the database for full admin dashboard visibility and audit trails.

### Basic Configuration

```python
# Database sessions provide full audit trail
admin.use_database_sessions()
```

### Characteristics

- **Persistent**: Sessions survive application restarts
- **Auditable**: Full visibility in admin dashboard
- **Slower**: Database I/O overhead
- **Simple**: No external dependencies

### When to Use

✅ **Audit requirements**  
✅ **Compliance needs**  
✅ **Small to medium applications**  
✅ **Admin session monitoring**  
❌ **High-traffic applications**  
❌ **Performance-critical scenarios**

---

## Hybrid Sessions

Combine the performance of Redis/Memcached with the audit capabilities of database storage.

### Redis + Database Hybrid

```python
# Redis for performance + Database for audit trail
admin.use_redis_sessions(
    host="localhost",
    port=6379,
    db=0,
    password="redis-password",
    track_sessions_in_db=True  # Enables hybrid mode
)
```

### Memcached + Database Hybrid

```python
# Memcached for performance + Database for audit trail
admin.use_memcached_sessions(
    host="localhost",
    port=11211,
    track_sessions_in_db=True  # Enables hybrid mode
)
```

### How Hybrid Mode Works

1. **Active sessions** stored in Redis/Memcached for fast access
2. **Session metadata** stored in database for admin visibility
3. **Session operations** update both stores
4. **Admin dashboard** shows all sessions from database
5. **Performance** maintained through cache-first approach

### When to Use

✅ **Production environments with audit needs**  
✅ **Compliance requirements + performance**  
✅ **Admin session monitoring + scalability**  
✅ **Best of both worlds scenarios**

---

## Dynamic Backend Switching

CRUDAdmin allows switching session backends at runtime while preserving all session manager settings.

### Runtime Configuration

```python
# Start with memory for development
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    max_sessions_per_user=10,
    session_timeout_minutes=60,
    cleanup_interval_minutes=30
)

# Later switch to Redis for production
admin.use_redis_sessions(
    host="redis-prod.example.com",
    port=6379,
    password="production-password"
)

# All session manager settings are preserved:
# - max_sessions_per_user: 10
# - session_timeout_minutes: 60
# - cleanup_interval_minutes: 30
```

### Environment-Based Switching

```python
import os

# Create admin instance
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"]
)

# Configure backend based on environment
environment = os.getenv("ENVIRONMENT", "development")

if environment == "production":
    admin.use_redis_sessions(
        host=os.getenv("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT")),
        password=os.getenv("REDIS_PASSWORD"),
        track_sessions_in_db=True
    )
elif environment == "staging":
    admin.use_redis_sessions(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        track_sessions_in_db=True
    )
else:
    # Development uses memory sessions (default)
    pass
```

---

## Configuration Patterns

### Simple Development Setup

```python
# No external dependencies required
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="dev-key-change-in-production"
)
# Uses memory sessions by default
```

### Production with Redis

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    secure_cookies=True,
    enforce_https=True
)

admin.use_redis_sessions(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    track_sessions_in_db=True
)
```

### High Availability Setup

```python
# Redis cluster with connection pooling
admin.use_redis_sessions(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    pool_size=20,
    connect_timeout=10,
    socket_keepalive=True,
    track_sessions_in_db=True
)
```

### Docker Compose Example

```yaml
version: '3.8'
services:
  web:
    build: .
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=secure-password
      - ENVIRONMENT=production
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass secure-password
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

---

## Parameter Validation and Error Handling

### Conflict Detection

CRUDAdmin includes comprehensive parameter validation:

```python
# ❌ This will raise ValueError
admin.use_redis_sessions(
    redis_url="redis://localhost:6379",
    host="localhost"  # Conflict with URL!
)

# ❌ This will also raise ValueError
admin.use_memcached_sessions(
    servers=["localhost:11211"],
    host="localhost"  # Conflict with servers!
)
```

### Error Handling

```python
try:
    admin.use_redis_sessions(
        host="unreachable-redis.example.com",
        port=6379
    )
except ImportError:
    # Redis dependencies not installed
    print("Redis support not available, falling back to memory")
    admin.use_memory_sessions()
except ConnectionError:
    # Redis server unavailable
    print("Redis unavailable, using database sessions")
    admin.use_database_sessions()
```

### Backward Compatibility

The new parameter system maintains full backward compatibility:

```python
# Old way still works
admin.use_redis_sessions("redis://localhost:6379/0")

# Old way for Memcached still works
admin.use_memcached_sessions(["localhost:11211"])
```

---

## Performance Considerations

### Session Cleanup

```python
# Configure automatic cleanup
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=secret_key,
    cleanup_interval_minutes=15,  # Clean expired sessions every 15 minutes
    session_timeout_minutes=30    # Sessions expire after 30 minutes
)
```

### Connection Pooling

```python
# Redis with optimized connection pooling
admin.use_redis_sessions(
    host="redis.example.com",
    port=6379,
    pool_size=20,  # Increase for high traffic
    connect_timeout=10,
    socket_keepalive=True
)
```

### Session Limits

```python
# Prevent memory exhaustion
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=secret_key,
    max_sessions_per_user=10,      # Limit concurrent sessions
    session_timeout_minutes=30,    # Auto-expire sessions
    cleanup_interval_minutes=15    # Regular cleanup
)
```

---

## Monitoring and Debugging

### Session Metrics

```python
# Monitor active sessions
user_sessions = await admin.session_manager.get_user_sessions(user_id)
print(f"User has {len(user_sessions)} active sessions")

# Check session activity
session_data = await admin.session_manager.validate_session(session_id)
if session_data:
    session_age = datetime.now(UTC) - session_data.last_activity
    print(f"Session last active {session_age} ago")
```

### Debug Logging

```python
import logging

# Enable session debug logging
logging.getLogger('crudadmin.session').setLevel(logging.DEBUG)

# Monitor Redis connections
logging.getLogger('redis').setLevel(logging.INFO)
```

### Health Checks

```python
# Check backend connectivity
try:
    await admin.session_manager.session_storage.exists("health-check")
    print("Session backend healthy")
except Exception as e:
    print(f"Session backend error: {e}")
```

---

## Production Deployment Guide

### Environment Variables

Set up these environment variables for production:

```bash
# Required
ADMIN_SECRET_KEY=your-secret-key-here
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_PASSWORD=secure-redis-password

# Optional
REDIS_DB=0
REDIS_POOL_SIZE=20
REDIS_CONNECT_TIMEOUT=10
ENVIRONMENT=production
```

### Security Checklist

- [ ] Use strong, unique secret keys
- [ ] Configure Redis/Memcached authentication
- [ ] Use TLS/SSL for Redis connections in production
- [ ] Set appropriate session timeouts
- [ ] Enable session cleanup
- [ ] Monitor session backend health
- [ ] Set up session audit logging

### Scaling Considerations

1. **Redis Cluster**: For high availability and horizontal scaling
2. **Connection Pooling**: Optimize pool sizes for your traffic
3. **Session Limits**: Prevent resource exhaustion
4. **Monitoring**: Track session metrics and backend performance
5. **Backup Strategy**: Plan for session backend failures

---

## Next Steps

After configuring your session backend:

1. **[Set up Admin Users](admin-users.md)** for authentication
2. **[Add Models](adding-models.md)** to create your admin interface
3. **[Learn the Interface](interface.md)** for daily operations
4. **[Explore Common Patterns](common-patterns.md)** for advanced scenarios

For production deployments, see [Advanced Topics](../advanced/overview.md) for comprehensive security, monitoring, and scaling strategies. 