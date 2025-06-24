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
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="memory"
)
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
from crudadmin.session.configs import RedisConfig

# Method 1: Using configuration object (recommended)
redis_config = RedisConfig(host="localhost", port=6379, db=0)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)

# Method 2: URL-based configuration
redis_config = RedisConfig(url="redis://localhost:6379/0")
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)

# Method 3: Dictionary configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config={"host": "localhost", "port": 6379, "db": 0}
)
```

### Redis with Authentication

```python
from crudadmin.session.configs import RedisConfig

# URL with password
redis_config = RedisConfig(url="redis://user:password@localhost:6379/1")
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)

# Configuration object with authentication (recommended)
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0,
    username="user",  # Redis 6.0+ ACL support
    password="your-redis-password"
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)

# Dictionary configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config={
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "password": "your-redis-password"
    }
)
```

### Production Redis Configuration

```python
import os
from crudadmin.session.configs import RedisConfig

# Environment-based configuration
redis_config = RedisConfig(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    password=os.getenv("REDIS_PASSWORD"),
    pool_size=20,
    connect_timeout=10
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)
```

### Advanced Redis Parameters

```python
from crudadmin.session.configs import RedisConfig

# Full configuration with all options
redis_config = RedisConfig(
    host="redis-cluster.example.com",
    port=6379,
    db=0,
    password="secure-password",
    username="redis_user",  # Redis 6.0+ ACL support
    
    # Connection pooling
    pool_size=20,
    connect_timeout=10
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config
)
```

### When to Use

✅ **Production environments**  
✅ **High-traffic applications**  
✅ **Multi-instance deployments**  
✅ **Applications requiring session persistence**  
✅ **Microservices architectures**

### Configuration Object Examples

For comprehensive Redis configuration:

```python
from crudadmin import CRUDAdmin
from crudadmin.session.configs import RedisConfig

# Basic configuration
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)

# With authentication (Redis 6.0+ ACL support)
redis_config = RedisConfig(
    host="redis.example.com",
    port=6379,
    db=1,
    username="myapp_user",      # Redis ACL username
    password="secure_password"
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)

# Advanced Redis configuration with connection pooling
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0,
    username="admin_user",
    password="secret123",
    pool_size=50,
    connect_timeout=30
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)
```

### URL-Based Configuration

Redis URLs support the standard format including usernames through RedisConfig:

```python
from crudadmin import CRUDAdmin
from crudadmin.session.configs import RedisConfig

# Basic Redis URL
redis_config = RedisConfig(url="redis://localhost:6379/0")
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)

# With password only (legacy authentication)
redis_config = RedisConfig(url="redis://:password123@localhost:6379/0")
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)

# With username and password (Redis 6.0+ ACL)
redis_config = RedisConfig(
    url="redis://myuser:password123@redis.example.com:6379/1"
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)

# Complex Redis URL with custom port and database
redis_config = RedisConfig(
    url="redis://admin_user:secure_pass@redis-cluster.internal:6380/3"
)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    session_backend="redis",
    redis_config=redis_config
)
```

### Authentication Methods

Redis supports two authentication methods:

1. **Legacy AUTH (Redis < 6.0)**: Uses only password
   ```python
   from crudadmin.session.configs import RedisConfig
   
   # URL format
   redis_config = RedisConfig(url="redis://:password@localhost:6379/0")
   admin = CRUDAdmin(
       session=get_session,
       SECRET_KEY="your-secret-key",
       session_backend="redis",
       redis_config=redis_config
   )
   
   # Configuration object format
   redis_config = RedisConfig(password="password")
   admin = CRUDAdmin(
       session=get_session,
       SECRET_KEY="your-secret-key",
       session_backend="redis",
       redis_config=redis_config
   )
   ```

2. **ACL Authentication (Redis 6.0+)**: Uses username and password
   ```python
   from crudadmin.session.configs import RedisConfig
   
   # URL format
   redis_config = RedisConfig(url="redis://username:password@localhost:6379/0")
   admin = CRUDAdmin(
       session=get_session,
       SECRET_KEY="your-secret-key",
       session_backend="redis",
       redis_config=redis_config
   )
   
   # Configuration object format
   redis_config = RedisConfig(
       username="username",
       password="password"
   )
   admin = CRUDAdmin(
       session=get_session,
       SECRET_KEY="your-secret-key",
       session_backend="redis",
       redis_config=redis_config
   )
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
from crudadmin.session.configs import MemcachedConfig

# Method 1: Server list
memcached_config = MemcachedConfig(servers=["localhost:11211"])
admin = CRUDAdmin(
    session=get_session,
    session_backend="memcached",
    memcached_config=memcached_config
)

# Method 2: Individual parameters
memcached_config = MemcachedConfig(host="localhost", port=11211)
admin = CRUDAdmin(
    session=get_session,
    session_backend="memcached",
    memcached_config=memcached_config
)

# Method 3: Dictionary configuration
admin = CRUDAdmin(
    session=get_session,
    session_backend="memcached",
    memcached_config={"host": "localhost", "port": 11211}
)
```

### Multiple Servers

```python
from crudadmin.session.configs import MemcachedConfig

# Multiple servers (first server used due to aiomcache limitations)
memcached_config = MemcachedConfig(servers=[
    "memcached1.example.com:11211",
    "memcached2.example.com:11211"  # Backup server
])
admin = CRUDAdmin(
    session=get_session,
    session_backend="memcached",
    memcached_config=memcached_config
)
```

### Production Memcached Configuration

```python
import os
from crudadmin.session.configs import MemcachedConfig

# Environment-based configuration
memcached_config = MemcachedConfig(
    host=os.getenv("MEMCACHED_HOST", "localhost"),
    port=int(os.getenv("MEMCACHED_PORT", 11211)),
    pool_size=15
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="memcached",
    memcached_config=memcached_config
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
admin = CRUDAdmin(
    session=get_session,
    session_backend="database"
)
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
from crudadmin.session.configs import RedisConfig

# Redis for performance + Database for audit trail
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0,
    password="redis-password"
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="redis",
    redis_config=redis_config,
    track_sessions_in_db=True  # Enables hybrid mode
)
```

### Memcached + Database Hybrid

```python
from crudadmin.session.configs import MemcachedConfig

# Memcached for performance + Database for audit trail
memcached_config = MemcachedConfig(
    host="localhost",
    port=11211
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    session_backend="memcached",
    memcached_config=memcached_config,
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

## Environment-Based Configuration

### Dynamic Configuration

```python
import os
from crudadmin.session.configs import RedisConfig

# Configure backend based on environment
environment = os.getenv("ENVIRONMENT", "development")

if environment == "production":
    redis_config = RedisConfig(
        host=os.getenv("REDIS_HOST"),
        port=int(os.getenv("REDIS_PORT")),
        password=os.getenv("REDIS_PASSWORD")
    )
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
        session_backend="redis",
        redis_config=redis_config,
        track_sessions_in_db=True
    )
elif environment == "staging":
    redis_config = RedisConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379))
    )
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
        session_backend="redis",
        redis_config=redis_config,
        track_sessions_in_db=True
    )
else:
    # Development uses memory sessions (default)
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=os.environ["ADMIN_SECRET_KEY"]
    )
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
import os
from crudadmin.session.configs import RedisConfig

redis_config = RedisConfig(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"]
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    session_backend="redis",
    redis_config=redis_config,
    track_sessions_in_db=True,
    secure_cookies=True,
    enforce_https=True
)
```

### High Availability Setup

```python
import os
from crudadmin.session.configs import RedisConfig

# Redis cluster with connection pooling
redis_config = RedisConfig(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    pool_size=20,
    connect_timeout=10
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    session_backend="redis",
    redis_config=redis_config,
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

## Configuration Validation

### Built-in Validation

CRUDAdmin configuration objects include comprehensive validation:

```python
from crudadmin.session.configs import RedisConfig, MemcachedConfig

# ✅ URL takes precedence when both URL and individual params are set
redis_config = RedisConfig(
    url="redis://localhost:6379/0",
    host="ignored",  # URL takes precedence
    port=9999        # URL takes precedence
)

# ✅ Server list takes precedence for Memcached
memcached_config = MemcachedConfig(
    servers=["server1:11211"],
    host="ignored",  # servers take precedence
    port=9999        # servers take precedence
)

# ❌ This will raise ValidationError (invalid port)
try:
    redis_config = RedisConfig(port=70000)  # Invalid port range
except ValueError as e:
    print(f"Validation error: {e}")

# ❌ This will raise ValidationError (negative timeout)
try:
    redis_config = RedisConfig(connect_timeout=-5)  # Negative timeout
except ValueError as e:
    print(f"Validation error: {e}")
```



### Error Handling

```python
from crudadmin.session.configs import RedisConfig

try:
    redis_config = RedisConfig(
        host="unreachable-redis.example.com",
        port=6379
    )
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=SECRET_KEY,
        session_backend="redis",
        redis_config=redis_config
    )
except ImportError:
    # Redis dependencies not installed
    print("Redis support not available, falling back to memory")
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=SECRET_KEY,
        session_backend="memory"
    )
except ConnectionError:
    # Redis server unavailable
    print("Redis unavailable, using database sessions")
    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY=SECRET_KEY,
        session_backend="database"
    )
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
from crudadmin.session.configs import RedisConfig

# Redis with optimized connection pooling
redis_config = RedisConfig(
    host="redis.example.com",
    port=6379,
    pool_size=20,  # Increase for high traffic
    connect_timeout=10
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    redis_config=redis_config
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

Then use them in your configuration:

```python
import os
from crudadmin.session.configs import RedisConfig

# Create configuration from environment variables
redis_config = RedisConfig(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    password=os.environ["REDIS_PASSWORD"],
    db=int(os.getenv("REDIS_DB", "0")),
    pool_size=int(os.getenv("REDIS_POOL_SIZE", "10")),
    connect_timeout=int(os.getenv("REDIS_CONNECT_TIMEOUT", "10"))
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    session_backend="redis",
    redis_config=redis_config,
    # Session management settings from environment
    max_sessions_per_user=int(os.getenv("MAX_SESSIONS_PER_USER", "5")),
    session_timeout_minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "30")),
    cleanup_interval_minutes=int(os.getenv("CLEANUP_INTERVAL_MINUTES", "15"))
)
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