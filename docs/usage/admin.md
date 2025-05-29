BEGIN RAW
# Building Admin Interfaces with CRUDAdmin

CRUDAdmin helps you create powerful admin interfaces for your FastAPI applications with minimal effort. Built on top of FastCRUD and SQLAlchemy, it supports any database that these libraries work with, including PostgreSQL, MySQL, SQLite, Oracle, and Microsoft SQL Server.

## Understanding CRUDAdmin

At its core, CRUDAdmin creates a web-based admin interface for your SQLAlchemy models. It handles all the complexities of:

- User authentication and session management
- Model operations (Create, Read, Update, Delete) through FastCRUD
- Security features like IP restrictions and HTTPS enforcement
- Event logging and audit trails
- Health monitoring

!!! NOTE
    Since CRUDAdmin uses FastCRUD with SQLAlchemy, you can use it with any database that SQLAlchemy supports. Just make sure you have the appropriate database driver installed.

## Getting Started

### Setting Up Your First Admin Interface

The first step is creating a basic admin interface. You'll need a database connection and at least one model to manage. Here's a simple example:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String
import os

# First, set up your database models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)  
    username = Column(String, unique=True)
    email = Column(String)
    role = Column(String)

# Create your database connection
engine = create_async_engine("sqlite+aiosqlite:///app.db")
session = AsyncSession(engine)

# Generate a secure secret key
SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY") or os.urandom(32).hex()

# Create your admin interface
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    initial_admin={
        "username": "admin",
        "password": "secure_pass123"  
    }
)
```

This code sets up a basic admin interface with SQLite storage and creates an initial admin user.

### Mounting **and Initializing** the Admin Interface

Unlike many FastAPI components, **CRUDAdmin requires an initialization step** before your application starts serving requests. This ensures all internal tables (for admin users, sessions, event logs, etc.) are created, and that the initial admin user is set up if needed.

#### 1. Using FastAPI's Lifespan

A recommended approach is using FastAPI's lifespan feature to handle both database table creation and admin initialization:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create database tables for your models if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Initialize the admin interface (creates internal admin tables, initial admin user, etc.)
    await admin.initialize()
    
    # Your other startup logic, if any
    yield
    # Cleanup logic, if any

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Mount the admin interface at "/admin"
app.mount("/admin", admin.app)
```

With this configuration:

1. Your SQLAlchemy models are created (if they don't already exist).  
2. `admin.initialize()` sets up all internal CRUDAdmin tables and ensures an initial admin user is present.  
3. The admin interface is accessible at `/admin` once the app is running.

!!! NOTE
    - If your project uses database migrations (e.g., Alembic), you can rely on those for table creation. However, it's still necessary to call `admin.initialize()` so CRUDAdmin can create its own internal tables and apply any needed logic.  
    - The `initial_admin` user is only created if no admin user currently exists. If you remove `initial_admin` from your code, no default admin user will be created.

#### 2. Manual Initialization (If Needed)

If you prefer a manual initialization approach (for instance, in scripts or tests), you can do something like:

```python
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await admin.initialize()

# Then call startup() before running your FastAPI application
await startup()
```

## Database Configuration

You can use any supported database, but CRUDAdmin uses SQLite by default. You can configure this separately from your main application database:

```python
# Using PostgreSQL for admin data
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin"
)

# Or using custom SQLite
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    admin_db_path="./custom_admin.db"
)
```

The admin database stores:

- User accounts and credentials
- Session information
- Token blacklist for logged-out sessions
- Event logs and audit trails (if enabled)
- System health metrics

## Adding Models to the Admin Interface

For each model you want to manage through the admin interface, you need to define Pydantic schemas that specify how the data should be validated. Let's look at a practical example:

```python
from pydantic import BaseModel, Field, validator
from decimal import Decimal
from datetime import datetime
from typing import Optional

# First, define your SQLAlchemy model
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Decimal, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# Then create schemas for creating and updating products
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    price: Decimal = Field(..., gt=0)
    description: Optional[str] = Field(None, max_length=500)
    
    @validator("price")
    def validate_price(cls, v):
        if v > 1000000:
            raise ValueError("Price cannot exceed 1,000,000")
        return v

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    price: Optional[Decimal] = Field(None, gt=0)
    description: Optional[str] = None

# Add the model to your admin interface
admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    update_internal_schema=None,
    delete_schema=None,
    allowed_actions={"view", "create", "update"}  # Disable deletion if needed
)
```

The schemas define validation rules and field constraints, ensuring that data entered through the admin interface is valid. The `allowed_actions` parameter lets you control which operations are available for each model.

## Security Features

### Authentication and Session Management

CRUDAdmin implements server-side sessions for robust and secure authentication.

!!! NOTE
    Server-side sessions provide excellent security for admin interfaces, allowing for immediate session invalidation and detailed control over active users.

Here's a detailed configuration:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY, # Still needed for signing session cookies
    # Session management
    max_sessions_per_user=5,          # Limit concurrent sessions
    session_timeout_minutes=30,       # Session inactivity timeout
    cleanup_interval_minutes=15,      # How often to remove expired sessions
    # Enable secure cookies and HTTPS for production
    secure_cookies=True,
    enforce_https=True,
)
```

This configuration creates a secure authentication system where:

- **Server-side sessions** provide stateful, secure authentication:
  - Sessions are stored in the admin database.
  - Can be invalidated immediately if needed (e.g., on logout or if a security issue is detected).
  - Limited to 5 concurrent sessions per user (`max_sessions_per_user`).
  - Sessions expire after 30 minutes of inactivity (`session_timeout_minutes`).
  - Expired sessions are cleaned up every 15 minutes (`cleanup_interval_minutes`).

- Additional security features:
  - Secure cookies for HTTPS-only transmission of the session ID.
  - Session tracking and monitoring available through the admin interface.
  - Failed login attempt tracking (if event logging is enabled).

!!! TIP
    Configure shorter session timeouts (`session_timeout_minutes`) for sensitive admin interfaces.

!!! WARNING
    Ensure `session_manager.cleanup_expired_sessions()` is called periodically (handled internally by CRUDAdmin's middleware) to prevent session table bloat.

### IP Restrictions and HTTPS

For production environments, you can restrict access to specific IP addresses and enforce HTTPS:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Restrict access to specific IPs or networks
    allowed_ips=["10.0.0.1", "10.0.0.2"],
    allowed_networks=["192.168.1.0/24"],
    # Force HTTPS
    enforce_https=True,
    https_port=443
)
```

This is particularly useful when your admin interface needs to be accessible only from specific locations, like your office network or VPN.

## Event Tracking and Audit Logs

Event tracking provides detailed information about system usage and changes. Enable it like this:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True  # Enable event tracking
)
```

When enabled, CRUDAdmin automatically logs:

- All login attempts (successful and failed)
- CRUD operations on models (who changed what and when)
- System health status changes
- Security-related events
- Session management events

Each event includes:

- Timestamp with timezone
- User who performed the action
- IP address of the request
- Type of action
- Success/failure status
- Detailed information about changes
- Related resource information

You can view these logs through the built-in event log interface at `/admin/management/events`, which provides:

- Filtering by event type, user, date range, and status
- Detailed view of each event
- Export capabilities for further analysis

## Health Monitoring

CRUDAdmin includes a health monitoring dashboard that helps you keep track of your system's status. Access it at `/admin/management/health` to see:

### System Status Checks

- Database connectivity and response times
- Session management status
- Recent errors or issues

The health monitoring system runs regular checks and provides real-time status updates, making it easier to identify and troubleshoot issues before they become problems.

## Best Practices

### 1. Secret Management

Proper secret key management is crucial for the security of your admin interface. CRUDAdmin uses this key for signing session cookies.

**Key Generation**

```python
# Option 1: Using Python's secrets module (Recommended)
import secrets
SECRET_KEY = secrets.token_urlsafe(32)

# Option 2: Using OpenSSL (from command line)
# $ openssl rand -base64 32

# Option 3: Using /dev/urandom on Unix systems
# $ head -c 32 /dev/urandom | base64
```

**Environment-Based Configuration**

!!! WARNING
    Never commit your `.env` file to version control. Always add it to your `.gitignore` file.

!!! TIP
    Use Starlette's `Secret` type for sensitive values like passwords and API keys. This prevents accidental exposure through string representation.

```python
from starlette.config import Config
from starlette.datastructures import Secret, CommaSeparatedStrings

# Config will be read from environment variables and/or ".env" files
config = Config(".env")

# Load configuration with type casting
DEBUG = config('DEBUG', cast=bool, default=False)
SECRET_KEY = config('SECRET_KEY', cast=Secret)
ALLOWED_IPS = config('ALLOWED_IPS', cast=CommaSeparatedStrings, default='')
ALLOWED_NETWORKS = config('ALLOWED_NETWORKS', cast=CommaSeparatedStrings, default='')

# Development configuration
if not DEBUG:
    admin = CRUDAdmin(
        session=session,
        SECRET_KEY=str(SECRET_KEY),  # Convert Secret to string
        secure_cookies=True,
        enforce_https=True,
        allowed_ips=list(ALLOWED_IPS),
        allowed_networks=list(ALLOWED_NETWORKS)
    )
# Production configuration
else:
    admin = CRUDAdmin(
        session=session,
        SECRET_KEY=str(SECRET_KEY),
        secure_cookies=False  # For local development
    )
```

!!! NOTE
    The `SECRET_KEY` should be at least 32 bytes long for secure cookie signing. Use a cryptographically secure method to generate it.

!!! DANGER
    Running without HTTPS in production is extremely dangerous. Only disable `secure_cookies` and `enforce_https` in development environments.

**Key Storage Best Practices**

- Store keys in environment variables or secure key management systems
- Keep different keys for development, staging, and production
- Rotate keys periodically
- Never commit keys to version control
- Use appropriate file permissions for any files containing keys

### 2. Authentication Settings

Configure authentication to balance security and user experience.

**Token Lifecycle Management**

!!! WARNING
    Keep access token expiration times short. Long-lived access tokens pose a significant security risk if compromised.

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Short-lived access tokens require more frequent authentication
    # but reduce the impact of token theft
    ACCESS_TOKEN_EXPIRE_MINUTES=15,
    
    # Longer refresh tokens mean users don't need to log in as frequently
    REFRESH_TOKEN_EXPIRE_DAYS=7,
    
    # Session limits prevent too many concurrent logins
    session_manager=SessionManager(
        max_sessions_per_user=5,
        session_timeout_minutes=30,
        cleanup_interval_minutes=15
    )
)
```

**Production Security Settings**

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Enable secure cookies
    secure_cookies=True,
    
    # Force HTTPS
    enforce_https=True,
    https_port=443,
    
    # Restrict access to specific IPs
    allowed_ips=["10.0.0.1", "10.0.0.2"],
    allowed_networks=["192.168.1.0/24"]
)
```

### 3. Network Security

Implement multiple layers of security to protect your admin interface.

**IP Restrictions**

!!! TIP
    Use CIDR notation for network ranges to make IP restrictions more manageable. For example, `10.0.0.0/24` covers all IPs from `10.0.0.0` to `10.0.0.255`.

!!! WARNING
    IP restrictions should not be your only security measure. Always use them in combination with proper authentication and HTTPS.

```python
# Restrict access to office network and VPN
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    allowed_ips=[
        "10.0.0.1",     # Office gateway
        "10.0.0.2"      # VPN server
    ],
    allowed_networks=[
        "192.168.1.0/24",   # Office network
        "10.8.0.0/24"       # VPN network
    ]
)
```

**HTTPS Configuration**

- Always enable HTTPS in production
- Use valid SSL certificates (not self-signed)
- Configure proper HTTP to HTTPS redirects
- Set appropriate security headers

**Access Control**

!!! WARNING
    Always use the principle of least privilege when setting `allowed_actions`. Only grant the minimum permissions necessary for each model.

!!! DANGER
    Be especially careful with delete permissions. Consider using soft deletes where possible by adding an `is_deleted` flag to your models.

```python
# Limit model access based on roles
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    # Only allow viewing and updating users
    allowed_actions={"view", "update"}
)

admin.add_view(
    model=AuditLog,
    create_schema=AuditLogSchema,
    update_schema=AuditLogSchema,
    # Read-only access to audit logs
    allowed_actions={"view"}
)
```

### 4. Monitoring and Audit

Set up comprehensive monitoring to detect and respond to issues quickly.

**Event Tracking Setup**

!!! NOTE
    Event tracking has a small performance impact. For high-traffic applications, consider using a separate database for event storage.

!!! TIP
    Set up log rotation or archival policies to manage the size of your event logs over time.

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Enable comprehensive event tracking
    track_events=True,
    
    # Store events in a separate database
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
)
```

**Health Monitoring**

The health dashboard at `/admin/management/health` provides real-time information about:

- Database connectivity and performance
- Session management status
- Authentication service status
- System resources

**Example Health Check Response:**

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
    },
    "token_service": {
        "status": "healthy",
        "last_token_generated": "2025-02-01T12:34:56Z"
    }
}
```

**Event Log Monitoring**

The event log interface at `/admin/management/events` lets you:

1. Filter events by:
    - Event type (login, create, update, delete)
    - Status (success, failure)
    - User
    - Date range

2. View detailed information about each event:
    - Timestamp
    - User who performed the action
    - IP address
    - Action details
    - Success/failure status
    - Related resource information

3. Export events for further analysis or archival

Regularly review these logs for:

- Failed login attempts from unexpected locations
- Unusual patterns of database operations
- System health issues
- Security-related events

---

By following these practices and understanding CRUDAdmin's features, you can create secure, maintainable admin interfaces that make managing your application's data easier and safer.