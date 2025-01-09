# CRUDAdmin

<p align="center">
  <i>Easily extendable FastAPI admin dashboard with built-in authentication and CRUD operations</i>
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
<b>CRUDAdmin</b> is a powerful admin dashboard for FastAPI applications that provides automatic CRUD interfaces, built-in authentication, and a modern UI. It's designed to be easily extendable and customizable while maintaining a clean, responsive interface for managing your application's data.
</p>

## Features

- 🔐 **Built-in Authentication**: Complete authentication system with user management and token-based security
- 🎨 **Modern UI**: Clean, responsive interface with dark/light theme support
- ⚡️ **HTMX Integration**: Enhanced interactivity without complex client-side JavaScript
- 📱 **Mobile-Friendly**: Responsive design that works across all device sizes
- 🔍 **Search & Filter**: Dynamic searching and filtering capabilities for all models
- 📊 **Pagination**: Built-in pagination support with configurable page sizes
- 🛡️ **Type Safety**: Full TypeScript-like safety with Pydantic models
- 🎯 **Auto CRUD**: Automatic CRUD interface generation for your SQLAlchemy models
- 🔧 **Customizable**: Easy to extend and customize to fit your needs

## Requirements

Before installing CRUDAdmin, ensure you have:

- **Python**: Version 3.11 or newer
- **FastAPI**: Version 0.103.1 or newer
- **SQLAlchemy**: Version 2.0.21 or newer
- **Pydantic**: Version 2.4.1 or newer
- **Jinja2**: Version 3.1.2 or newer
- **FastCRUD**: Version 0.12.1 or newer

## Installation

Install using pip:

```bash
pip install crudadmin
```

Or with Poetry:

```bash
poetry add crudadmin
```

## Quick Start

Here's a minimal example to get you started:

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase
from crudadmin import CRUDAdmin

# Database setup
class Base(DeclarativeBase):
    pass

# Create engine and session
engine = create_async_engine("sqlite+aiosqlite:///./test.db")
async_session = AsyncSession(engine)

# Initialize FastAPI
app = FastAPI()

# Initialize CRUDAdmin
admin = CRUDAdmin(
    base=Base,
    engine=engine,
    session=async_session,
    SECRET_KEY="your-secret-key"
)

# Include admin routes
app.include_router(admin.router)
```

## Adding Models

Add your SQLAlchemy models to the admin interface:

```python
from sqlalchemy import Column, Integer, String
from pydantic import BaseModel

# Define your SQLAlchemy model
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String)

# Define Pydantic schemas
class UserCreate(BaseModel):
    name: str
    email: str

class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None

# Add to admin
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    update_internal_schema=None,
    delete_schema=None
)
```

## Authentication

CRUDAdmin comes with built-in authentication. The first admin user can be created programmatically:

```python
@app.on_event("startup")
async def create_first_admin():
    await admin.admin_authentication.create_first_admin(
        name="Admin User",
        username="admin",
        email="admin@example.com",
        password="securepassword123"
    )
```

## Security

CRUDAdmin implements several security features:

- JWT-based authentication
- Password hashing with bcrypt
- Token blacklisting
- CSRF protection
- Role-based access control

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

If you have any questions or feedback, please reach out:

Igor Magalhaes – [@igormagalhaesr](https://twitter.com/igormagalhaesr) – igormagalhaesr@gmail.com