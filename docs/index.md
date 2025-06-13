<style>
    .md-typeset h1,
    .md-content__button {
        display: none;
    }
</style>

<p align="center">
  <a href="https://github.com/benavlabs/crudadmin">
    <img src="assets/CRUDAdmin.png?raw=true" alt="CRUDAdmin logo" width="45%" height="auto">
  </a>
</p>
<p align="center" markdown=1>
  <i>Modern admin interface for FastAPI with built-in authentication, event tracking, and security features</i>
</p>
<p align="center" markdown=1>
<a href="https://github.com/benavlabs/crudadmin/actions/workflows/tests.yml">
  <img src="https://github.com/benavlabs/crudadmin/actions/workflows/tests.yml/badge.svg" alt="Tests"/>
</a>
<a href="https://pypi.org/project/crudadmin/">
  <img src="https://img.shields.io/pypi/v/crudadmin?color=%2334D058&label=pypi%20package" alt="PyPi Version"/>
</a>
<a href="https://pypi.org/project/crudadmin/">
  <img src="https://img.shields.io/pypi/pyversions/crudadmin.svg?color=%2334D058" alt="Supported Python Versions"/>
</a>
</p>
<hr>
<p align="justify">
<b>CRUDAdmin</b> is a robust admin interface generator for <b>FastAPI</b> applications, offering secure authentication, comprehensive event tracking, and essential monitoring features. Built with <a href="https://github.com/benavlabs/fastcrud">FastCRUD</a> and HTMX, it helps you create production-ready admin panels with minimal configuration.
</p>
<hr>

!!! warning "Experimental Status"
    CRUDAdmin is still experimental. While actively developed and tested, APIs may change between versions. Upgrade with caution in production environments, always carefully reading the changelog.

## Features

- **🔒 Multi-Backend Session Management**: Flexible session storage with Memory, Redis, Memcached, Database, and Hybrid backends
- **🛡️ Built-in Security**: CSRF protection, rate limiting, IP restrictions, HTTPS enforcement, and secure cookie handling
- **🚦 Rate Limiting**: Login attempt protection with IP and username-based tracking
- **📝 Event Tracking & Audit Logs**: Comprehensive audit trails for all admin actions with user agent parsing and attribution
- **📊 Auto-generated Interface**: Creates admin UI directly from your SQLAlchemy models with intelligent field detection
- **🔍 Advanced Filtering**: Type-aware field filtering, search, and pagination with bulk operations
- **🌗 Modern UI**: Clean, responsive interface built with HTMX and [FastCRUD](https://github.com/benavlabs/fastcrud)

## Video Preview

<p align="center">To see what CRUDAdmin dashboard looks like in practice, watch the video demo on youtube:</p>
<p align="center">
  <a href="https://www.youtube.com/watch?v=THLdUbDQ9yM">
    <img src="assets/youtube-preview.png" alt="Watch CRUDAdmin Dashboard Demo on Youtube"/>
  </a>
</p>

## Minimal Example

Here's how simple it is to get a complete admin interface running:

??? note "Define your SQLAlchemy models (click to expand)"
    ```python
    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import DeclarativeBase
    
    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        username = Column(String, unique=True)
        email = Column(String)
        role = Column(String)
    ```

??? note "Define your Pydantic schemas (click to expand)"
    ```python
    from pydantic import BaseModel, EmailStr
    
    class UserCreate(BaseModel):
        username: str
        email: EmailStr
        role: str = "user"

    class UserUpdate(BaseModel):
        email: EmailStr | None = None
        role: str | None = None
    ```

Now, create your admin interface:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from crudadmin import CRUDAdmin

# Database setup
engine = create_async_engine("sqlite+aiosqlite:///app.db")

# Create database session dependency
async def get_session():
    async with AsyncSession(engine) as session:
        yield session

# Create admin interface
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    initial_admin={
        "username": "admin",
        "password": "secure_password123"
    }
)

# Add models to admin
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"}
)

# Setup FastAPI with proper initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface
    await admin.initialize()
    yield

# Create and mount the app
app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

And it's all done! Navigate to `/admin` to access your admin interface with:

- User authentication
- CRUD operations for your models
- Responsive UI with dark/light themes
- Built-in security features

## Requirements

Before installing CRUDAdmin, ensure you have the following prerequisites:

* **Python:** Version 3.9 or newer.
* **FastAPI:** CRUDAdmin is built to work with FastAPI, so having FastAPI in your project is essential.
* **FastCRUD:** CRUDAdmin is built on top of [FastCRUD](https://github.com/benavlabs/fastcrud) for CRUD operations (which requires SQLAlchemy 2.0+ for database operations and Pydantic 2.0+ for data validation and serialization).
* **aiosqlite:** Required for async SQLite operations (automatically installed as a dependency).

## Installing

To install, just run:

```sh
uv add crudadmin
```

Or, if using pip:

```sh
pip install crudadmin
```

### Optional Dependencies

For production use with different session backends:

```sh
# For Redis sessions (recommended for production)
uv add "crudadmin[redis]"

# For Memcached sessions  
uv add "crudadmin[memcached]"

# For PostgreSQL/MySQL admin databases
uv add "crudadmin[postgres]"  # PostgreSQL
uv add "crudadmin[mysql]"     # MySQL
```

You can also combine multiple extras:

```sh
# Redis sessions + PostgreSQL admin database
uv add "crudadmin[redis,postgres]"

# All session and database options
uv add "crudadmin[redis,memcached,postgres,mysql]"
```

### Development Installation

For development with all extras:

```sh
uv add "crudadmin[dev]"
```

## Usage

CRUDAdmin offers flexible configuration options for different deployment scenarios:

### Basic Development Setup

```python
from crudadmin import CRUDAdmin

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key",
    initial_admin={
        "username": "admin", 
        "password": "admin123"
    }
)

# Add your models
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate
)

# Mount to FastAPI
app.mount("/admin", admin.app)
```

### Production Configuration with Security

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    
    # Security features
    allowed_ips=["10.0.0.1"],
    allowed_networks=["192.168.1.0/24"],
    secure_cookies=True,
    enforce_https=True,
    
    # Session management
    max_sessions_per_user=3,
    session_timeout_minutes=15,
    
    # Event tracking
    track_events=True,
    track_sessions_in_db=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin"
    
).use_redis_sessions(
    redis_url="redis://localhost:6379"
)
```

### Advanced Model Configuration

```python
from crudadmin.admin_interface.model_view import PasswordTransformer

# Password handling for user models
password_transformer = PasswordTransformer(
    password_field="password",
    hashed_field="hashed_password", 
    hash_function=hash_password,
    required_fields=["username", "email"]
)

admin.add_view(
    model=User,
    create_schema=UserCreateWithPassword,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"},
    password_transformer=password_transformer
)

# Read-only audit logs
admin.add_view(
    model=AuditLog,
    create_schema=AuditLogSchema,
    update_schema=AuditLogSchema,
    allowed_actions={"view"}  # Read-only
)
```

### Session Backend Configuration

```python
# Redis Sessions (Recommended for Production)
admin.use_redis_sessions(
    redis_url="redis://localhost:6379",
    password="redis-password"
)

# Memcached Sessions
admin.use_memcached_sessions(
    servers=["localhost:11211"]
)

# Hybrid Sessions (Redis + Database)
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    track_sessions_in_db=True
).use_redis_sessions(
    redis_url="redis://localhost:6379"
)
```

## What You Get

Once set up, CRUDAdmin provides:

- **Admin Dashboard**: Overview of your models and system health
- **Model Management**: Auto-generated forms for CRUD operations
- **User Authentication**: Secure login/logout with session management  
- **Event Logs**: Track all admin actions with full audit trails
- **Health Monitoring**: Real-time system status and diagnostics
- **Security Features**: CSRF protection, rate limiting, IP restrictions
- **Responsive UI**: Works on desktop and mobile devices

## Next Steps

- **[Quick Start](quick-start.md)**: Get up and running in 5 minutes
- **[Basic Configuration](usage/configuration.md)**: Detailed configuration options
- **[Advanced Topics](advanced/overview.md)**: Production features and advanced configurations
- **[API Reference](api/overview.md)**: Complete API documentation

## License

[`MIT`](community/LICENSE.md)

