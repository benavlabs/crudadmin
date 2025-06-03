# CRUDAdmin

<p align="center">
  <a href="https://igorbenav.github.io/crudadmin/">
    <img src="docs/assets/CRUDAdmin.png" alt="CRUDAdmin logo" width="45%" height="auto">
  </a>
</p>

<p align="center">
  <i>Modern admin interface for FastAPI with built-in authentication, event tracking, and security features</i>
</p>

<p align="center">
<a href="https://pypi.org/project/crudadmin">
  <img src="https://img.shields.io/pypi/v/crudadmin?color=%2334D058&label=pypi%20package" alt="Package version"/>
</a>
<a href="https://pypi.org/project/crudadmin">
  <img src="https://img.shields.io/pypi/pyversions/crudadmin.svg?color=%2334D058" alt="Supported Python versions"/>
</a>
</p>

<hr>
<p align="justify">
<b>CRUDAdmin</b> is a robust admin interface generator for <b>FastAPI</b> applications, offering secure authentication, comprehensive event tracking, and essential monitoring features. Built on top of FastCRUD and SQLAlchemy, it helps you create production-ready admin panels with minimal configuration.
</p>

<p><b>Documentation</b>: <a href="https://igorbenav.github.io/crudadmin/">https://igorbenav.github.io/crudadmin/</a></p>

> [!WARNING]  
> CRUDAdmin is still experimental.

<hr>

## Features

- 🔒 **Multi-Backend Session Management**: Flexible session storage with Memory, Redis, Memcached, Database, and Hybrid backends
- 🛡️ **Enhanced Security**: CSRF protection, rate limiting, IP restrictions, HTTPS enforcement, and secure cookie handling
- 📝 **Event Tracking & Audit Logs**: Comprehensive audit trails for all admin actions with user attribution
- 🏥 **Health Monitoring**: Real-time system status dashboard with key metrics and database health checks
- 📊 **Auto-generated Interface**: Creates admin UI directly from your SQLAlchemy models with intelligent field detection
- 🔍 **Advanced Filtering**: Type-aware field filtering, search, and pagination with bulk operations
- 🌗 **Modern UI**: Clean, responsive interface with dark/light theme support
- ⚡ **Performance Optimized**: Efficient session handling, query optimization, and background cleanup
- 🚦 **Rate Limiting**: Login attempt protection with IP and username-based tracking
- 👤 **Device Fingerprinting**: Enhanced user agent parsing and session tracking

## Requirements

Before installing CRUDAdmin, ensure you have:

- **FastAPI**: Latest version for the web framework
- **SQLAlchemy**: Version 2.0+ for database operations
- **Pydantic**: Version 2.0+ for data validation

## Installing

```sh
pip install crudadmin
```

Or using poetry:

```sh
poetry add crudadmin
```

For production use with Redis sessions (recommended):
```sh
pip install crudadmin redis
```

## Usage

CRUDAdmin offers a straightforward way to create admin interfaces. Here's how to get started:

### Define Your Models and Schemas

**models.py**
```python
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String)
    role = Column(String)
```

**schemas.py**
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

### Set Up the Admin Interface

**main.py**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from crudadmin import CRUDAdmin
import os

# Database setup
engine = create_async_engine("sqlite+aiosqlite:///app.db")
session = AsyncSession(engine)

# Create admin interface
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=os.environ.get("ADMIN_SECRET_KEY"),
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

### Session Management Backends

**Memory Backend (Default - for development/testing):**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Uses memory backend by default
)
```

**Redis Backend (Recommended for production):**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
).use_redis_sessions(
    redis_url="redis://localhost:6379",
    password="your-redis-password"
)
```

**Memcached Backend:**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
).use_memcached_sessions(
    servers=["localhost:11211"]
)
```

**Hybrid Backend (Redis + Database persistence):**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_sessions_in_db=True,
).use_redis_sessions(
    redis_url="redis://localhost:6379"
)
```

### Enable Event Tracking & Audit Logs

**Basic Event Tracking:**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await admin.initialize()  # Creates event tracking tables
    yield
```

**Advanced Event Tracking with Session Persistence:**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True,
    track_sessions_in_db=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
).use_redis_sessions(
    redis_url="redis://localhost:6379"
)
```

### Configure Security Features

**Production Security Setup:**
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # IP Security
    allowed_ips=["10.0.0.1"],
    allowed_networks=["192.168.1.0/24"],
    # Cookie Security
    secure_cookies=True,
    enforce_https=True,
    # Session Management
    max_sessions_per_user=3,
    session_timeout_minutes=15,
    # Rate Limiting
    cleanup_interval_minutes=10,
    # Event Tracking
    track_events=True,
    track_sessions_in_db=True
).use_redis_sessions(
    redis_url="redis://localhost:6379"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await admin.initialize()  # Initializes all security features
    yield
```

## Session Management Migration (v0.2.0)

CRUDAdmin now features a completely redesigned session management system with multiple backend support:

### What's New

- **Multi-Backend Support**: Memory, Redis, Memcached, Database, and Hybrid storage options
- **CSRF Protection**: Built-in CSRF token generation and validation
- **Rate Limiting**: Login attempt tracking with IP and username-based limits
- **Device Fingerprinting**: Enhanced user agent parsing and device info tracking
- **Performance Improvements**: Session operations no longer require database queries (except Database backend)
- **Production Ready**: Redis and Memcached backends for horizontal scaling

### Backend Comparison

| Backend | Use Case | Performance | Persistence | Scalability |
|---------|----------|-------------|-------------|-------------|
| **Memory** | Development/Testing | Fastest | No | Single Instance |
| **Redis** | Production (Recommended) | Very Fast | Optional | High |
| **Memcached** | High-Traffic Production | Very Fast | No | High |
| **Database** | Simple Deployments | Good | Yes | Medium |
| **Hybrid** | Enterprise/Audit Requirements | Fast | Yes | High |

## Current Limitations (Roadmap Items)

- No file upload support yet
- No custom admin views (model-based only)
- No custom field widgets
- No SQLAlchemy relationship support
- No export functionality (CSV, Excel, PDF)
- No role-based permissions system

## Similar Projects

- **[Django Admin](https://docs.djangoproject.com/en/stable/ref/contrib/admin/)**: The inspiration for this project
- **[Flask-Admin](https://flask-admin.readthedocs.io/)**: Similar project for Flask
- **[Sqladmin](https://github.com/aminalaee/sqladmin)**: Another FastAPI admin interface

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

Igor Benav – [@igorbenav](https://x.com/igorbenav) – igormagalhaesr@gmail.com
[github.com/igorbenav](https://github.com/igorbenav/)