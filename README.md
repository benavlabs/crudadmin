# CRUDAdmin

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

## Features

- 🔒 **Advanced Authentication**: Session management, token blacklisting, configurable expiry
- 📊 **CRUD Interface**: Auto-generated UI for SQLAlchemy models
- 📱 **Modern UI**: Dark/light themes, responsive design, HTMX-powered interactivity  
- 🔍 **Smart Search**: Type-aware filtering and sorting
- 📝 **Event Tracking**: Audit logs for all admin actions
- 🛡️ **Security**: IP restrictions, HTTPS enforcement, secure cookies
- 🏥 **Health Monitoring**: System status dashboard
- 🗑️ **Bulk Actions**: Multi-record operations

## Requirements

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0+
- Pydantic 2.0+
- AIOSQLITE/AsyncPG
- bcrypt
- python-jose[cryptography]
- python-multipart

## Installation

```bash
pip install crudadmin
```

## Basic Setup

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from fastapi import FastAPI
from crudadmin import CRUDAdmin
from pydantic import BaseModel, EmailStr

# Define models
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String)
    role = Column(String)

# Define schemas
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    role: str = "user"

class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = None

# Setup
engine = create_async_engine("sqlite+aiosqlite:///app.db")
session = AsyncSession(engine)
app = FastAPI()

# Initialize admin interface
admin = CRUDAdmin(
    session=session,
    SECRET_KEY="your-secret-key",
    initial_admin={
        "username": "admin",
        "password": "secure_password123"
    }
)

# Add models to admin interface
admin.add_view(
    model=User,
    create_schema=UserCreate, 
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update"}
)

# Mount admin app
app.mount("/admin", admin.app)

# Initialize database
@app.on_event("startup")
async def startup():
    await admin.initialize()
```

## Admin Interface Pages

### Dashboard
- Quick overview of all models and record counts
- System health status
- Recent activity (when event tracking enabled)

### Model List Views
- Table view of all records
- Sortable columns (click headers)
- Smart filtering based on field types
- Bulk actions (delete)
- Configurable pagination
- Search across any field

### Model Create/Update Forms
- Auto-generated from Pydantic schemas
- Field validation
- Support for:
  - Text fields
  - Numbers
  - Dates/Times
  - Booleans
  - Enums
  - Foreign keys
  - JSON fields
  
### Event Logs
Available when `track_events=True`:
- All CRUD operations
- Authentication events
- System events
- Record changes
- Session activity
- Filterable by:
  - Event type
  - User
  - Date range
  - Status

### Health Dashboard
- Database connectivity status
- Session management status
- Token service status
- Response latencies
- Component health checks

## Advanced Configuration

### Configuration Parameters

```python
admin = CRUDAdmin(
    # Required parameters
    session=session,                 # AsyncSession instance
    SECRET_KEY="your-secret-key",    # Min 32 bytes, generate using:
        # python -c "import secrets; print(secrets.token_urlsafe(32))"
        # openssl rand -base64 32
        # head -c 32 /dev/urandom | base64

    # Security (all optional)
    allowed_ips=["10.0.0.1", "10.0.0.2"],        # Restrict access to IPs
    allowed_networks=["192.168.1.0/24"],         # Restrict access to networks
    secure_cookies=True,                         # Enable secure cookie flags
    enforce_https=True,                          # Force HTTPS connections
    https_port=443,                              # HTTPS port if enforced
    
    # Authentication (all optional, shown with defaults)
    ACCESS_TOKEN_EXPIRE_MINUTES=30,              # Minutes until access token expires
    REFRESH_TOKEN_EXPIRE_DAYS=1,                 # Days until refresh token expires
    ALGORITHM="HS256",                           # JWT signing algorithm
    
    # Admin Database (optional, pick one if custom location needed)
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin",
    admin_db_path="/custom/path/admin.db",        # SQLite path
    
    # Features (all optional, shown with defaults)
    track_events=False,                          # Enable event/audit logging
    theme="dark-theme",                          # "dark-theme" or "light-theme"
    mount_path="/admin",                         # URL path prefix
    setup_on_initialization=True,                # Auto-initialize on startup
)
```

### Complex Models

```python
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    items = Column(JSON)
    total = Column(Float)
    status = Column(String)
    created_at = Column(DateTime(timezone=True))

class OrderCreate(BaseModel):
    user_id: int
    items: List[dict]
    total: float
    status: str = "pending"
    
class OrderUpdate(BaseModel):
    items: List[dict] | None = None
    status: str | None = None
    
class OrderDelete(BaseModel):
    archive: bool = False
    reason: str | None = None

# Custom update logic
class OrderUpdateInternal(BaseModel):
    updated_at: datetime
    modified_by: str

admin.add_view(
    model=Order,
    create_schema=OrderCreate,
    update_schema=OrderUpdate,
    update_internal_schema=OrderUpdateInternal,
    delete_schema=OrderDelete,
    allowed_actions={"view", "create", "update", "delete"}
)
```

## Security Features

### Authentication
- Session-based with JWT tokens
- Token refresh mechanism
- Token blacklisting
- Configurable expiry times
- Multiple active sessions per user
- Session timeout monitoring

### Access Control
- IP address restrictions
- Network CIDR restrictions
- HTTPS enforcement
- Secure cookie settings
- Per-model action permissions
- Audit logging

### Session Management  
- Session tracking
- Inactivity timeout
- Device/browser tracking
- Concurrent session limits
- Force logout capability

## Event Tracking

When enabled with `track_events=True`:

### Tracked Events
- Model creation
- Model updates
- Model deletion
- Login attempts
- Logout events
- Session events
- System events

### Event Data
- Timestamp
- User
- IP Address
- Event type
- Status
- Details payload
- Related model/record
- Changes made

### Audit Log Features
- Searchable
- Filterable
- Exportable
- Record change tracking
- User activity monitoring

## Customization

### Allowed Actions
Control available operations per model:
- view: Read-only access
- create: Allow record creation
- update: Allow record modification  
- delete: Allow record deletion

```python
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create"}  # Read-only + create
)
```

### Theme Options
- dark-theme (default)
- light-theme

```python
admin = CRUDAdmin(
    # ...
    theme="light-theme"
)
```

### Database Configuration
- SQLite (default)
- PostgreSQL 
- Custom database URLs
- Separate admin database

## Current Limitations

- Basic field types only in forms
- No custom authentication backends
- Limited form customization 
- No file upload support
- No custom admin views (only model-based)
- No custom field widgets
- No relationship widgets
- No inline editing
- No export functionality

## FAQ

**Q: Can I use a custom database for admin data?**  
A: Yes, use `admin_db_url` or `admin_db_path` in CRUDAdmin config

**Q: How do I customize the look & feel?**  
A: Currently limited to dark/light themes. Custom themes coming soon.

**Q: Can I add custom views?**  
A: Not yet supported. Only model-based views available.

**Q: How do I handle file uploads?**  
A: No built-in support yet. Handle in your main app.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests
4. Submit PR

## License

This project is licensed under the MIT License. See LICENSE file.