# Basic Configuration

This guide covers the essential configuration steps for setting up your CRUDAdmin instance. You'll learn how to create the admin interface with the most common settings to get up and running quickly.

## Prerequisites

Before configuring CRUDAdmin, ensure you have:

- A working FastAPI application
- SQLAlchemy models defined (see [Quick Start](../quick-start.md))
- CRUDAdmin installed (`uv add crudadmin`)
- Basic understanding of FastAPI application structure

---

## Creating Your CRUDAdmin Instance

### Minimal Setup

The simplest CRUDAdmin setup requires only two parameters:

```python
from crudadmin import CRUDAdmin
from sqlalchemy.ext.asyncio import AsyncSession

# Minimal CRUDAdmin instance
admin = CRUDAdmin(
    session=get_session,  # Your session dependency function
    SECRET_KEY="your-secret-key-here"
)
```

### Common Configuration

Here are the most commonly customized settings for getting started:

```python
import os
from crudadmin import CRUDAdmin
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Database setup
DATABASE_URL = "sqlite+aiosqlite:///./app.db"
engine = create_async_engine(DATABASE_URL, echo=True)

# Create database session dependency
async def get_session():
    async with AsyncSession(engine) as session:
        yield session

# Create admin with common settings
admin = CRUDAdmin(
    # Required parameters (no defaults)
    session=get_session,
    SECRET_KEY=os.environ.get("ADMIN_SECRET_KEY", "dev-key-change-in-production"),
    
    # Basic interface settings
    mount_path="/admin",  # Default: "/admin"
    theme="dark-theme",   # Default: "dark-theme" (or "light-theme")
    
    # Database configuration
    admin_db_path=None,   # Default: None (creates ./crudadmin_data/admin.db)
    
    # Initial admin user
    initial_admin={       # Default: None - no auto-creation
        "username": "admin",
        "password": "secure_password_123"
    },
)
```

**Understanding Defaults:**

- **Required parameters**: `session` and `SECRET_KEY` have no defaults and must be provided
- **Optional parameters**: All other parameters have sensible defaults and can be omitted
- **Most minimal setup**: `CRUDAdmin(session=get_session, SECRET_KEY="your-key")` uses all defaults

!!! warning "Security Best Practices"
    **Database Security:** When using SQLite, always add `*.db`, `*.sqlite`, and `crudadmin_data/` to your `.gitignore` to prevent committing sensitive data.

    **Production Security:** For production environments, always follow these best practices:
    
    - Use strong, randomly generated secret keys.
    - Use environment variables for all sensitive configuration.
    - Use a robust session backend like Redis: `uv add "crudadmin[redis]"` (see [Session Backends](session-backends.md))
    - Enable HTTPS and secure cookies to protect data in transit.
    - Set up proper logging and monitoring to detect security events.

---

## Parameter Details

### `session` (Callable, required)
Your SQLAlchemy async session factory or callable that returns sessions:

```python
# Session dependency function (recommended)
async def get_session():
    async with AsyncSession(engine) as session:
        yield session

admin = CRUDAdmin(session=get_session, SECRET_KEY=secret_key)
```

#### `SECRET_KEY` (str)
Critical for session security and cookie signing. **Never use default values in production!**

```python
# ✅ Use environment variables
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"]
)

# ✅ Generate secure keys
# python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Common Optional Parameters

#### `mount_path` (str, default: "/admin")
URL path where the admin interface will be accessible. **If you want a different path than "/admin", you must explicitly pass the `mount_path` parameter to CRUDAdmin.**

```python
# Default: accessible at /admin (no mount_path parameter needed)
admin = CRUDAdmin(session=get_session, SECRET_KEY=key)

# Custom path: accessible at /dashboard (must specify mount_path)
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY=key,
    mount_path="/dashboard"  # Required for non-default paths
)
```

**Important**: Remember to also update your FastAPI mount call to match:

```python
# If using custom mount_path="/dashboard"
app.mount("/dashboard", admin.app)  # Must match the mount_path

# Or dynamically
app.mount(admin.mount_path, admin.app)  # Uses the configured path
```

#### `theme` (str, default: "dark-theme")
Choose between light and dark themes:

```python
# Dark theme (default)
admin = CRUDAdmin(session=get_session, SECRET_KEY=key, theme="dark-theme")

# Light theme
admin = CRUDAdmin(session=get_session, SECRET_KEY=key, theme="light-theme")
```

#### `admin_db_path` (str, default: None)
Custom location for the admin database (used for admin users, sessions, etc.):

```python
# Default: creates ./crudadmin_data/admin.db
admin = CRUDAdmin(session=get_session, SECRET_KEY=key)

# Custom path
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY=key,
    admin_db_path="./admin/admin_database.db"
)
```

#### `initial_admin` (dict, default: None)
Automatically create an admin user when the system initializes:

```python
# No initial admin (default - create manually later)
admin = CRUDAdmin(session=get_session, SECRET_KEY=key)

# Create initial admin automatically
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    initial_admin={
        "username": "admin",
        "password": "secure_password_123"
    }
)
```

---

## FastAPI Integration

### Basic Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin
    await admin.initialize()
    yield

app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

### Custom Mount Path

```python
# If you configured a custom mount_path
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    mount_path="/dashboard"
)

# Mount at the same path
app.mount("/dashboard", admin.app)
```

---

## Development vs Production

### Development Setup

```python
# Simple development configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="dev-key-change-in-production",  # Simple key for development
    initial_admin={                             # Convenient auto-admin
        "username": "admin",
        "password": "admin123"
    }
)
```

### Production Considerations

```python
# Basic production configuration
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],  # Required environment variable
    initial_admin=None,                         # Create admin users manually
    secure_cookies=True,                        # Default: True (good for production)
    enforce_https=True,                         # Redirect HTTP to HTTPS
)
```

For comprehensive production configuration, see the **[Advanced Topics](../advanced/overview.md)** section.

---

## Next Steps

After configuring your CRUDAdmin instance:

1. **[Add Models](adding-models.md)** to create your admin interface
2. **[Set up Admin Users](admin-users.md)** for access control  
3. **[Learn the Interface](interface.md)** to manage your data effectively

For production deployments and advanced configurations, explore the **[Advanced Topics](../advanced/overview.md)** section for scalable session handling, comprehensive security, and audit logging.
