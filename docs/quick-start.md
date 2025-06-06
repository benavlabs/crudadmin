# Quick Start

Get CRUDAdmin up and running in just a few minutes! This guide will walk you through creating your first admin interface.

## Requirements

Before starting, ensure you have:

* **Python:** Version 3.9 or newer
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
    
    # Create database session dependency
    async def get_session():
        async with AsyncSession(engine) as session:
            yield session
    ```

### Using CRUDAdmin

Create your admin interface and mount it to your FastAPI application

```python title="main.py"
from contextlib import asynccontextmanager
from fastapi import FastAPI
import os

from crudadmin import CRUDAdmin
# Import your setup (models, schemas, database)

# Create admin interface
admin = CRUDAdmin(
    session=get_session,  # Your session dependency function
    SECRET_KEY=os.environ.get("SECRET_KEY", "your-secret-key-for-development"),
    initial_admin={
        "username": "admin",
        "password": "admin123"  # Change this in production!
    }
)

# Add your models to the admin interface
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)

# Initialize database and admin
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface
    await admin.initialize()
    yield

# Create FastAPI app
app = FastAPI(lifespan=lifespan)

# Mount admin interface
app.mount("/admin", admin.app)
```

And you're all done! 

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

✅ **Secure Authentication** - Login/logout with session management  
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
    
    - Use strong, randomly generated secret keys
    - Use environment variables for sensitive configuration
    - Consider using Redis for session storage: `uv add "crudadmin[redis]"`
    - Enable HTTPS and secure cookies
    - Set up proper logging and monitoring

For production deployment and advanced configurations, see the **[Advanced Topics](advanced/overview.md)** section.