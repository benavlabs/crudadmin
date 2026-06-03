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

> \[!IMPORTANT\]  
> **v0.4.0 Breaking Changes**: Session backend configuration has been completely redesigned. The old method-based API (`admin.use_redis_sessions()`, etc.) has been removed in favor of a cleaner constructor-based approach. **Existing code will need updates.** See the [v0.4.0 release notes](https://github.com/benavlabs/crudadmin/releases) for migration guide and examples.

> \[!WARNING\]  
> CRUDAdmin is still experimental. While actively developed and tested, APIs may change between versions. Upgrade with caution in production environments, always carefully reading the changelog.

## Features

- **🔒 Multi-Backend Session Management**: Memory, Redis, Memcached, Database, and Hybrid backends
- **🛡️ Built-in Security**: CSRF protection, rate limiting, IP restrictions, HTTPS enforcement, and secure cookies
- **📝 Event Tracking & Audit Logs**: Comprehensive audit trails for all admin actions with user attribution
- **📊 Auto-generated Interface**: Creates admin UI directly from your SQLAlchemy models with intelligent field detection
- **🔍 Advanced Filtering**: Type-aware field filtering, search, and pagination with bulk operations
- **🌗 Modern UI**: Clean, responsive interface built with HTMX and [FastCRUD](https://github.com/benavlabs/fastcrud)

## Video Preview

<p align="center">To see what CRUDAdmin dashboard actually looks like in practice, watch the video demo on youtube:</p>
<p align="center">
  <a href="https://www.youtube.com/watch?v=THLdUbDQ9yM">
    <img src="docs/assets/youtube-preview.png" alt="Watch CRUDAdmin Dashboard Demo on Youtube" width="75%" height="auto"/>
  </a>
</p>
<br>

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

> \[!WARNING\]
> **Important for SQLite users:** If you're using SQLite databases (which is the default for CRUDAdmin), make sure to add database files to your `.gitignore` to avoid committing sensitive data like admin credentials and session tokens.
>
> ```gitignore
> # SQLite databases - NEVER commit these to version control
> *.db
> *.sqlite
> *.sqlite3
> crudadmin_data/
>
> # Also exclude database journals
> *.db-journal
> *.sqlite3-journal
> ```

## Session Backends

### Development (Default)
```python
admin = CRUDAdmin(session=get_session, SECRET_KEY="key")  # Memory backend (default)
```

### Production with Redis
```python
from crudadmin import CRUDAdmin, RedisConfig

# Using configuration object (recommended)
redis_config = RedisConfig(host="localhost", port=6379, db=0)
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY="key",
    session_backend="redis",
    redis_config=redis_config
)

# Or using a dictionary
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY="key",
    session_backend="redis",
    redis_config={"host": "localhost", "port": 6379, "db": 0}
)

# Or using Redis URL
redis_config = RedisConfig(url="redis://localhost:6379/0")
admin = CRUDAdmin(
    session=get_session, 
    SECRET_KEY="key",
    session_backend="redis",
    redis_config=redis_config
)
```

### Production with Security Features
```python
from crudadmin import CRUDAdmin, RedisConfig

# Configure Redis backend
redis_config = RedisConfig(
    host="localhost",
    port=6379,
    db=0,
    password="your-redis-password"
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    # Session backend configuration
    session_backend="redis",
    redis_config=redis_config,
    # Session management settings
    max_sessions_per_user=3,
    session_timeout_minutes=15,
    cleanup_interval_minutes=5,
    # Security features
    allowed_ips=["10.0.0.1"],
    allowed_networks=["192.168.1.0/24"],
    secure_cookies=True,
    enforce_https=True,
    # Event tracking
    track_events=True
)
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

## Build a full SaaS on FastAPI

Need more than an admin panel? **[FastroAI](https://fastro.ai)** is the complete FastAPI SaaS template from the same team: auth, Stripe payments (subscriptions, credits, discounts), entitlements, transactional email, an Astro frontend, and PydanticAI agents, wired together and production-ready.

<p align="center">
  <a href="https://fastro.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/benavlabs/crudadmin/blob/main/docs/assets/fastroai-card-dark.png?raw=true">
      <img src="https://github.com/benavlabs/crudadmin/blob/main/docs/assets/fastroai-card-light.png?raw=true" alt="FastroAI - the complete FastAPI SaaS template: auth, Stripe payments, entitlements, email, frontend and AI" width="100%">
    </picture>
  </a>
</p>

<p align="center"><b><a href="https://fastro.ai">Ship your SaaS faster with FastroAI →</a></b></p>

<hr>
<a href="https://benav.io">
  <img src="docs/assets/benav_labs_banner.png" alt="Powered by Benav Labs - benav.io"/>
</a>