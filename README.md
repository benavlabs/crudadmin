# CRUDAdmin

<p align="center">
  <a href="https://benavlabs.github.io/crudadmin/">
    <img src="docs/assets/CRUDAdmin.png" alt="CRUDAdmin logo" width="45%" height="auto">
  </a>
</p>

<p align="center">
  <i>Modern admin interface for FastAPI with built-in authentication, event tracking, and security features</i>
</p>

<p align="center">
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

---

**CRUDAdmin** is a robust admin interface generator for **FastAPI** applications, offering secure authentication, comprehensive event tracking, and essential monitoring features. Built with [FastCRUD](https://github.com/benavlabs/fastcrud) and HTMX, it helps you create production-ready admin panels with minimal configuration.

**Documentation**: [https://benavlabs.github.io/crudadmin/](https://benavlabs.github.io/crudadmin/)

> [!WARNING]  
> CRUDAdmin is still experimental. While actively developed and tested, APIs may change between versions. Upgrade with caution in production environments, always carefuly reading the changelog.

## Features

- **🔒 Multi-Backend Session Management**: Memory, Redis, Memcached, Database, and Hybrid backends
- **🛡️ Built-in Security**: CSRF protection, rate limiting, IP restrictions, HTTPS enforcement, and secure cookies
- **📝 Event Tracking & Audit Logs**: Comprehensive audit trails for all admin actions with user attribution
- **📊 Auto-generated Interface**: Creates admin UI directly from your SQLAlchemy models with intelligent field detection
- **🔍 Advanced Filtering**: Type-aware field filtering, search, and pagination with bulk operations
- **🌗 Modern UI**: Clean, responsive interface built with HTMX and [FastCRUD](https://github.com/benavlabs/fastcrud)

## Quick Start

### Installation

```sh
uv add crudadmin
```

For production with Redis sessions:
```sh
uv add "crudadmin[redis]"
```

Or using pip and memcached:
```sh
pip install "crudadmin[memcached]"
```

### Basic Setup

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from crudadmin import CRUDAdmin

from .user import (
    User,
    UserCreate,
    UserUpdate,
)

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

Navigate to `/admin` to access your admin interface with:

- User authentication
- CRUD operations for your models
- Responsive UI with dark/light themes
- Built-in security features

## Session Backends

### Development (Default)
```python
admin = CRUDAdmin(session=get_session, SECRET_KEY="key")  # Memory backend
```

### Production with Redis
```python
admin = CRUDAdmin(session=get_session, SECRET_KEY="key").use_redis_sessions(
    redis_url="redis://localhost:6379"
)
```

### Production with Security Features
```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    # Security features
    allowed_ips=["10.0.0.1"],
    allowed_networks=["192.168.1.0/24"],
    secure_cookies=True,
    enforce_https=True,
    # Session management
    max_sessions_per_user=3,
    session_timeout_minutes=15,
    # Event tracking
    track_events=True
).use_redis_sessions(redis_url="redis://localhost:6379")
```

## Backend Options

| Backend | Use Case | Performance | Persistence | Scalability |
|---------|----------|-------------|-------------|-------------|
| **Memory** | Development/Testing | Fastest | No | Single Instance |
| **Redis** | Production (Recommended) | Very Fast | Optional | High |
| **Memcached** | High-Traffic Production | Very Fast | No | High |
| **Database** | Simple Deployments | Good | Yes | Medium |
| **Hybrid** | Enterprise/Audit Requirements | Fast | Yes | High |

## What You Get

- **Secure Authentication** - Login/logout with session management  
- **Auto-Generated Forms** - Create and edit forms built from your Pydantic schemas  
- **Data Tables** - Paginated, sortable tables for viewing your data  
- **CRUD Operations** - Full Create, Read, Update, Delete functionality  
- **Responsive UI** - Works on desktop and mobile devices  
- **Dark/Light Themes** - Toggle between themes  
- **Input Validation** - Built-in validation using your Pydantic schemas  
- **Event Tracking** - Monitor all admin actions with audit trails  
- **Health Monitoring** - Real-time system status and diagnostics  

## Documentation

- **[Quick Start](https://benavlabs.github.io/crudadmin/quick-start/)**: Get up and running in 5 minutes
- **[Usage Guide](https://benavlabs.github.io/crudadmin/usage/overview/)**: Complete usage documentation
- **[API Reference](https://benavlabs.github.io/crudadmin/api/overview/)**: Full API documentation
- **[Advanced Topics](https://benavlabs.github.io/crudadmin/advanced/overview/)**: Production features and configurations

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<hr>
<a href="https://benav.io">
  <img src="docs/assets/benav_labs_banner.png" alt="Powered by Benav Labs - benav.io"/>
</a>