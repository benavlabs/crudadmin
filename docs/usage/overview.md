# CRUDAdmin Usage Overview

This guide provides comprehensive information about using CRUDAdmin to create admin interfaces for your FastAPI applications. Whether you're just getting started or looking to implement advanced features, you'll find everything you need in these sections.

## Core Documentation

### [Getting Started Guide](getting_started.md)

Learn the basics of CRUDAdmin and set up your first admin interface:

- Understanding CRUDAdmin's core concepts
- Setting up your first admin interface
- Configuring database connections
- Adding and managing models
- Basic usage and configuration

### [Security and Authentication](security_authentication.md)

Implement robust security measures for your admin interface:

- Setting up authentication and session management
- Configuring IP restrictions and HTTPS
- Managing secrets securely
- Implementing access control
- Production security best practices

### [Monitoring and Maintenance](monitoring_maintenance.md)

Keep your admin interface running smoothly:

- Setting up event tracking and audit logs
- Using the health monitoring dashboard
- Managing event logs effectively
- Implementing maintenance best practices
- Daily monitoring routines

## Quick Start Example

Here's a minimal example to get your admin interface up and running:

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
import os

# Set up database
Base = declarative_base()
engine = create_async_engine("sqlite+aiosqlite:///app.db")
session = AsyncSession(engine)

# Create admin interface
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=os.environ.get("ADMIN_SECRET_KEY"),
    initial_admin={
        "username": "admin",
        "password": "secure_pass123"
    }
)

# Mount to FastAPI
app = FastAPI()
app.mount("/admin", admin.app)
```

## Common Use Cases

### Basic Admin Interface

Perfect for simple applications needing data management:
```python
# Define your model
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    email = Column(String)

# Add to admin interface
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate
)
```

### Secure Production Setup

Recommended configuration for production environments:
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    enforce_https=True,
    secure_cookies=True,
    allowed_networks=["10.0.0.0/24"],
    track_events=True
)
```

### Monitored Environment

Set up comprehensive monitoring:
```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    track_events=True,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs"
)
```

## Next Steps

1. Start with the [Getting Started Guide](getting_started.md) to create your first admin interface
2. Implement security measures using the [Security and Authentication](security_authentication.md) guide
3. Set up monitoring using the [Monitoring and Maintenance](monitoring_maintenance.md) guide

Each guide provides detailed examples and best practices to help you make the most of CRUDAdmin's features.