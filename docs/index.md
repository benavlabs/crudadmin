<style>
    .md-typeset h1,
    .md-content__button {
        display: none;
    }
</style>

<p align="center">
  <a href="https://igorbenav.github.io/crudadmin/">
    <img src="assets/CRUDAdmin.png" alt="CRUDAdmin logo" width="45%" height="auto">
  </a>
</p>
<p align="center" markdown=1>
  <i>Modern admin interface for FastAPI with built-in authentication, event tracking, and security features</i>
</p>
<p align="center" markdown=1>
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
<hr>

## Features

- **Session-based Authentication**: Secure session management with inactivity timeouts and concurrent session limits
- **Built-in Security**: IP restrictions, HTTPS enforcement, and secure cookie handling
- **Event Tracking**: Comprehensive audit logs for all admin actions with user attribution
- **Health Monitoring**: Real-time system status dashboard with key metrics 
- **Auto-generated Interface**: Creates admin UI directly from your SQLAlchemy models
- **Smart Filtering**: Type-aware field filtering and efficient search
- **Modern UI**: Clean interface with dark/light theme support

## Requirements

Before installing CRUDAdmin, ensure you have:

* **Python**: Version 3.9 or newer
* **FastAPI**: Latest version for the web framework 
* **SQLAlchemy**: Version 2.0+ for database operations
* **Pydantic**: Version 2.0+ for data validation

## Installing

To install, just run:

```sh
pip install crudadmin
```

Or, if using poetry:

```sh
poetry add crudadmin
```

## Usage

Here's a quick example to get you started:

### Define Your Models and Schemas

```python title="models.py"
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

```python title="schemas.py"
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

```python title="main.py"
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

### Enable Security Features

CRUDAdmin offers robust security options out of the box:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    # Security settings
    allowed_ips=["10.0.0.1"],
    allowed_networks=["192.168.1.0/24"],
    secure_cookies=True,
    enforce_https=True,
    # Session settings
    max_sessions_per_user=5,
    session_timeout_minutes=30
)
```

### Enable Event Tracking

Track all admin actions with built-in audit logs:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
)
```

## Current Limitations

The following features are in development:

- No file upload support yet
- No custom admin views (model-based only) 
- No custom field widgets
- No SQLAlchemy relationship support
- No export functionality

## License

This project is licensed under the MIT License - see the [LICENSE](community/LICENSE.md) file for details.