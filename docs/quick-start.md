# Quick Start

Get CRUDAdmin up and running in just a few minutes! This guide will walk you through creating your first admin interface.

## Requirements

Before starting, ensure you have:

* **Python:** Version 3.10 or newer
* **FastAPI:** CRUDAdmin is built to work with FastAPI
* **FastCRUD:** CRUDAdmin is built on top of [FastCRUD](https://github.com/benavlabs/fastcrud) for CRUD operations (which requires SQLAlchemy 2.0+ for database operations and Pydantic 2.0+ for data validation and serialization)
* **aiosqlite:** Required for async SQLite operations (automatically installed as a dependency)

## Installation

Install CRUDAdmin:

```sh
uv add crudadmin
```

Or using pip:

```sh
pip install crudadmin
```

For production with Redis sessions (recommended):

```sh
uv add "crudadmin[redis]"
```

## Minimal Example

Assuming you have your SQLAlchemy model, Pydantic schemas and database connection, just skip to [Using CRUDAdmin](#using-crudadmin)

### Basic Setup

??? note "Define your SQLAlchemy model (click to expand)"
    ```python
    from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
    from sqlalchemy.orm import DeclarativeBase
    
    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        username = Column(String(50), unique=True, nullable=False)
        email = Column(String(100), unique=True, nullable=False)
        role = Column(String(20), default="user")
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=func.now())
    ```

??? note "Define your Pydantic schemas (click to expand)"
    ```python
    from pydantic import BaseModel, EmailStr
    from typing import Optional
    
    class UserCreate(BaseModel):
        username: str
        email: EmailStr
        role: str = "user"
        is_active: bool = True

    class UserUpdate(BaseModel):
        email: Optional[EmailStr] = None
        role: Optional[str] = None
        is_active: Optional[bool] = None
    ```

??? note "Set up your database connection (click to expand)"
    ```python
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    
    DATABASE_URL = "sqlite+aiosqlite:///./admin_demo.db"
    engine = create_async_engine(DATABASE_URL, echo=True)

    async def get_session():
        async with AsyncSession(engine) as session:
            yield session
    ```

### Using CRUDAdmin

Create your admin interface and mount it to your FastAPI application. The example expects `Base`, `User`, `UserCreate`, `UserUpdate`, `engine` and `get_session` from the snippets above in the same file. `admin.initialize()` creates the admin tables and the initial admin; `admin.shutdown()` closes the session store when the app stops.

```python title="main.py"
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from crudadmin import CRUDAdmin

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-secret-key-change-me"),
    initial_admin={
        "username": "admin",
        "password": "admin123",
    },
)

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update", "delete"},
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

`SECRET_KEY` keys the stored session and CSRF identifiers. Keep it stable: changing it signs every admin out.

## 🔒 Security Setup

**Before committing your code**, ensure your `.gitignore` excludes database files:

```gitignore
*.db
*.sqlite
*.sqlite3
crudadmin_data/
*.db-journal
*.sqlite3-journal
```

This prevents accidentally committing:
- Your admin database with credentials
- Application databases with user data
- Session storage files
- SQLite journal files

## Accessing Your Admin Interface

1. **Start your FastAPI server:**
    ```bash
    uvicorn main:app --reload
    ```

2. **Navigate to the admin interface:**
    ```
    http://localhost:8000/admin
    ```

3. **Log in with your admin credentials:**
    - Username: `admin`
    - Password: `admin123`

4. **Start managing your data:**
    - View existing users
    - Create new users  
    - Edit user information
    - Delete users (if enabled)

## What You Get Out of the Box

✅ **Secure Authentication** - Login with lockout after repeated failures, CSRF-protected changes, and a Sessions page to sign devices out  
✅ **Auto-Generated Forms** - Create and edit forms built from your Pydantic schemas  
✅ **Data Tables** - Paginated, sortable tables for viewing your data  
✅ **CRUD Operations** - Full Create, Read, Update, Delete functionality  
✅ **Responsive UI** - Works on desktop and mobile devices  
✅ **Dark/Light Themes** - Toggle between themes  
✅ **Input Validation** - Built-in validation using your Pydantic schemas  

## Next Steps

Now that you have a basic admin interface running, you might want to:

- **[Add more models](usage/adding-models.md)** to your admin interface
- **[Learn the interface](usage/interface.md)** to effectively manage your data
- **[Set up admin users](usage/admin-users.md)** for access control
- **[Explore common patterns](usage/common-patterns.md)** for real-world scenarios
- **[Advanced Topics](advanced/overview.md)** for production features and security

## Production Considerations

!!! warning "Security Notice"
    The example above uses a simple password and secret key for demonstration. In production:
    
    - Use a strong, randomly generated `SECRET_KEY` from the environment, and keep it stable
    - With more than one worker, keep sessions in Redis (`session_backend="redis"`, `uv add "crudadmin[redis]"`) or the admin database (`session_backend="database"`); see [Session Backends](usage/session-backends.md)
    - Behind a reverse proxy, set `trusted_proxy_hops` so lockouts and the IP allowlist see the real client IP
    - Restrict the admin to known networks with `allowed_ips` / `allowed_networks`
    - Serve the admin over HTTPS; session cookies are `Secure` by default

For production deployment and advanced configurations, see the **[Advanced Topics](advanced/overview.md)** section.