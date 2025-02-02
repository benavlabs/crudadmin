# Securing Your Admin Interface

Security is crucial for any admin interface - after all, this is where your application's most sensitive operations happen. This guide will walk you through securing your CRUDAdmin interface, from basic authentication to production-ready security measures.

## Understanding Authentication in CRUDAdmin

CRUDAdmin uses a dual-layer authentication system that combines the best of two approaches: JWT (JSON Web Tokens) and server-side sessions. Let's understand why this matters and how to set it up properly.

### Authentication in CRUDAdmin

CRUDAdmin uses JWT combined with server-side sessions for authentication, which is perfect for admin interfaces where security is more important than handling large numbers of concurrent users. This approach gives you:

1. Complete control over active sessions
2. Ability to immediately invalidate sessions when needed
3. Built-in protection against common authentication attacks
4. Easy session monitoring through the admin interface

Here's how to set up this dual authentication system:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # JWT Configuration
    ACCESS_TOKEN_EXPIRE_MINUTES=15,   # Short-lived access tokens
    REFRESH_TOKEN_EXPIRE_DAYS=7,      # Longer refresh tokens
    # Session Management
    max_sessions_per_user=5,          # Limit concurrent sessions
    session_timeout_minutes=30,       # Session inactivity timeout
    cleanup_interval_minutes=15,      # Cleanup schedule
)

# Setup FastAPI lifespan for secure initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface and security features
    await admin.initialize()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

Let's break down these settings:

1. **Access Tokens** (15 minutes): These are the primary authentication credentials. We keep them short-lived because if one is stolen, it can only be used for 15 minutes.
2. **Refresh Tokens** (7 days): Instead of making users log in every 15 minutes, we provide a refresh token that can obtain new access tokens. Seven days is a good balance between security and convenience.
3. **Session Limits** (5 per user): This prevents a single user from having too many active sessions. If an attacker tries to create multiple sessions, they'll be limited.

## Protecting Your Admin Interface

### IP Restrictions

In production, you'll want to limit who can even attempt to access your admin interface. IP restrictions are your first line of defense:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    allowed_ips=["10.0.0.1", "10.0.0.2"],        # Specific IPs
    allowed_networks=["192.168.1.0/24"],          # Entire networks
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Initialize admin with IP restrictions
    await admin.initialize()
    yield
```

This configuration means:

- Only requests from `10.0.0.1` or `10.0.0.2` will be allowed
- All IPs in the range `192.168.1.0` to `192.168.1.255` can access the admin
- All other IPs will be blocked before they even reach the login page

Common scenarios for IP restrictions:

- Allow only office IP addresses
- Allow access through your VPN
- Restrict to internal network addresses

### HTTPS Configuration

HTTPS isn't optional for admin interfaces - it's essential. Here's how to enforce it:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    enforce_https=True,
    https_port=443,
    secure_cookies=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin with HTTPS enforcement
    await admin.initialize()
    yield
```

This configuration:

1. Forces all traffic over HTTPS
2. Sets the Secure flag on cookies
3. Redirects HTTP traffic to HTTPS automatically

## Managing Secrets Securely

One of the most common security mistakes is hardcoding secrets in your code. Let's set up proper secret management:

```python
from contextlib import asynccontextmanager
from starlette.config import Config
from starlette.datastructures import Secret, CommaSeparatedStrings

# Load configuration from .env file and environment variables
config = Config(".env")

# Development vs Production settings
DEBUG = config('DEBUG', cast=bool, default=False)
SECRET_KEY = config('SECRET_KEY', cast=Secret)
ALLOWED_IPS = config('ALLOWED_IPS', cast=CommaSeparatedStrings, default='')

admin = CRUDAdmin(
    session=session,
    SECRET_KEY=str(SECRET_KEY),
    # Production settings
    secure_cookies=not DEBUG,
    enforce_https=not DEBUG,
    allowed_ips=list(ALLOWED_IPS) if not DEBUG else None
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Initialize admin with secure configuration
    await admin.initialize()
    yield

app = FastAPI(lifespan=lifespan)
```

Store your `.env` file with this structure:
```plaintext
DEBUG=false
SECRET_KEY=your-secure-key-here
ALLOWED_IPS=10.0.0.1,10.0.0.2
```

[Rest of the documentation remains the same...]

## Implementing Access Control

Not all admin users should have the same permissions. CRUDAdmin lets you implement fine-grained access control:

```python
# Users can only be viewed and updated, not created or deleted
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "update"}
)

# Audit logs are read-only
admin.add_view(
    model=AuditLog,
    create_schema=AuditLogSchema,
    allowed_actions={"view"}
)
```

Instead of deleting records, consider using soft deletes:
```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
```

## Security Checklist for Production

Before deploying to production, ensure you've covered these essential points:

1. **Authentication**
    - [ ] Generate a strong SECRET_KEY
    - [ ] Set appropriate token expiration times
    - [ ] Configure session limits

2. **Network Security**
    - [ ] Enable HTTPS with valid certificates
    - [ ] Configure IP restrictions
    - [ ] Enable secure cookies

3. **Access Control**
    - [ ] Review and limit model permissions
    - [ ] Implement soft deletes where appropriate

4. **Monitoring**
    - [ ] Set up audit logging
    - [ ] Configure error tracking
    - [ ] Enable security alerts

---

Now that your admin interface is secure, let's move on to [Monitoring and Maintenance](monitoring_maintenance.md) to learn about:

- Setting up comprehensive audit trails
- Monitoring system health and performance
- Managing logs and backups
- Handling system maintenance