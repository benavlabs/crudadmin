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

- **🔒 Session Management**: Sessions in memory, Redis or the admin database, built on [crudauth](https://github.com/benavlabs/crudauth), with a Sessions page to sign devices out
- **🛡️ Built-in Security**: CSRF protection, login lockout, password confirmation before admin-account changes, IP allowlists, HTTPS enforcement, and secure session cookies (HttpOnly, Secure, SameSite=Strict)
- **👥 Roles**: Superusers manage admin accounts and see the event log; other admins work with your models
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

engine = create_async_engine("sqlite+aiosqlite:///app.db")


async def get_session():
    async with AsyncSession(engine) as session:
        yield session


admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
    initial_admin={
        "username": "admin",
        "password": "secure_password123",
    },
)

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"},
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await admin.initialize()
    yield
    await admin.shutdown()


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

* **Python:** Version 3.10 or newer.
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

`redis` adds the Redis session backend; `postgres` and `mysql` add drivers for keeping the admin database there:

```sh
uv add "crudadmin[redis]"
uv add "crudadmin[postgres]"
uv add "crudadmin[mysql]"
uv add "crudadmin[redis,postgres]"
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
        "password": "admin123",
    },
)

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
)

app.mount("/admin", admin.app)
```

### Production Configuration with Security

```python
from crudadmin import AccessConfig, CRUDAdmin, RedisConfig, SessionConfig

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    sessions=SessionConfig(
        backend="redis",
        redis=RedisConfig(url="redis://localhost:6379"),
        max_per_admin=3,
        timeout_minutes=15,
        secure_cookies=True,
    ),
    access=AccessConfig(
        allowed_ips=["10.0.0.1"],
        allowed_networks=["192.168.1.0/24"],
        trusted_proxy_hops=1,
        enforce_https=True,
    ),
    track_events=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin",
)
```

`trusted_proxy_hops=1` reads the client IP from `X-Forwarded-For` behind one reverse proxy; leave it at `0` when the app is exposed directly. `track_events=True` records logins, failed logins, lockouts and every change in the event log.

### Advanced Model Configuration

```python
from crudadmin.admin_interface.model_view import PasswordTransformer

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
    password_transformer=password_transformer,
)

admin.add_view(
    model=AuditLog,
    create_schema=AuditLogSchema,
    update_schema=AuditLogSchema,
    allowed_actions={"view"},
)
```

### Session Backend Configuration

Sessions, CSRF tokens and login-lockout counters live in one of three backends:

```python
from crudadmin import CRUDAdmin, RedisConfig, SessionConfig

admin = CRUDAdmin(session=get_session, SECRET_KEY=SECRET_KEY)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    sessions=SessionConfig(
        backend="redis",
        redis=RedisConfig(host="localhost", port=6379, password="redis-password"),
    ),
)

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    sessions=SessionConfig(backend="database"),
)
```

The default, `memory`, is per process: fine for development and a single worker. With several workers, use `redis`, or `database` to keep them in the admin database without extra infrastructure. See [Session Backends](usage/session-backends.md).

## What You Get

Once set up, CRUDAdmin provides:

- **Admin Dashboard**: Overview of your models and system health
- **Model Management**: Auto-generated forms for CRUD operations
- **User Authentication**: Login with lockout, CSRF-protected changes, and a Sessions page to sign devices out
- **Event Logs**: Track all admin actions with full audit trails
- **Health Monitoring**: Real-time system status and diagnostics
- **Security Features**: IP allowlists, HTTPS enforcement, secure session cookies
- **Responsive UI**: Works on desktop and mobile devices

## Next Steps

- **[Quick Start](quick-start.md)**: Get up and running in 5 minutes
- **[Basic Configuration](usage/configuration.md)**: Detailed configuration options
- **[Advanced Topics](advanced/overview.md)**: Production features and advanced configurations
- **[API Reference](api/overview.md)**: Complete API documentation

## License

[`MIT`](community/LICENSE.md)

