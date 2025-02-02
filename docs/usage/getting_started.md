# Getting Started with CRUDAdmin

Welcome to CRUDAdmin! This guide will walk you through creating your first admin interface for a FastAPI application. We'll start with the basics and gradually add more functionality as you become comfortable with the core concepts.

## What is CRUDAdmin?

CRUDAdmin is a tool that creates web-based admin interfaces for FastAPI applications. If you've used Django's admin interface, you'll find CRUDAdmin familiar - it provides similar functionality but is built specifically for FastAPI and SQLAlchemy with FastCRUD.

Think of CRUDAdmin as your application's control center. It automatically creates a professional admin interface where you can:

- Manage your application's data through a clean web interface
- Handle user authentication and permissions
- Monitor your application's health
- Track changes and maintain audit logs

The best part? You can set this up in minutes rather than building it from scratch.

## Your First Admin Interface

Let's create a simple admin interface for managing users. We'll build this step by step:

### Step 1: Setting Up Your Database Models

First, we need to define what data we want to manage. Let's create a basic User model:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String
import os

# Create the base class for our models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)  
    username = Column(String, unique=True)
    email = Column(String)
    role = Column(String)
```

This model represents a simple user table in our database. Each user has an ID, username, email, and role. The `unique=True` parameter ensures no two users can have the same username.

### Step 2: Creating the Database Connection

Now we need to connect to our database. We'll start with SQLite for simplicity:

```python
# Create the database engine
engine = create_async_engine("sqlite+aiosqlite:///app.db")
session = AsyncSession(engine)
```

We're using SQLite here because it's perfect for development - it doesn't require a separate server, and the database is just a file on your computer. For production, you'll want to switch to something like PostgreSQL (we'll cover that later).

### Step 3: Setting Up CRUDAdmin

Here's where the magic happens. We'll create our admin interface:

```python
# Generate a secure secret key
SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY") or os.urandom(32).hex()

# Create your admin interface
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    initial_admin={
        "username": "admin",
        "password": "secure_pass123"  
    }
)
```

Let's break down what's happening here:

- The `SECRET_KEY` is used for securing sessions and tokens. In production, you'll want to set this through environment variables
- `session` connects CRUDAdmin to your database
- `initial_admin` creates your first admin user - you'll use these credentials to log in

### Step 4: Mounting and Initializing the Admin Interface

Now we need to make our admin interface accessible through our FastAPI application and ensure it's properly initialized. Here's how to do it correctly:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Setup FastAPI lifespan for initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables for your models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface
    await admin.initialize()
    yield

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Mount the admin interface
app.mount("/admin", admin.app)
```

This setup ensures that:

1. Your database tables are created before the application starts
2. The admin interface is properly initialized
3. The admin interface is mounted at the correct URL path

After these steps, your admin interface will be available at `http://your-server/admin`. When you visit this URL, you'll see a login page where you can use the admin credentials we set up earlier.

### Step 5: Understanding the Admin Interface Initialization

Let's take a closer look at what happens during the initialization process and how to configure it for different scenarios.

The `initialize()` method is a crucial step that sets up the necessary database tables and creates your initial admin user. Here's what it does in detail:

What `initialize()` does:

1. Creates necessary admin database tables:
    - AdminUser table for managing admin users
    - AdminTokenBlacklist table for handling revoked tokens
    - AdminSession table for session management
    - If event tracking is enabled, creates AdminEventLog and AdminAuditLog tables

2. Creates the initial admin user if one doesn't exist yet, using the credentials provided in `initial_admin`

3. Sets up any additional configurations needed for the admin interface to function

You can also initialize the admin interface manually if you prefer:

```python
async def startup():
    await admin.initialize()

# Call this before running your application
await startup()
```

### Important Notes:

- Always call `initialize()` before your application starts accepting requests
- The best practice is to use FastAPI's lifespan event as shown above
- Make sure your database is accessible before calling `initialize()`
- The initial admin user is only created if no admin users exist in the database
- If you're using migrations, you may want to create these tables through your migration system instead

### Example with More Configuration:

```python
admin = CRUDAdmin(
    session=session,
    SECRET_KEY=SECRET_KEY,
    theme="dark-theme",  # UI theme
    ALGORITHM="HS256",  # JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES=30,
    REFRESH_TOKEN_EXPIRE_DAYS=7,
    initial_admin={
        "username": "admin",
        "password": "secure_pass123"
    },
    track_events=True,  # Enable audit logging
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create your application tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize admin interface with all features
    await admin.initialize()
    
    # Your other startup code here
    yield
    # Your cleanup code here

app = FastAPI(lifespan=lifespan)
```

### Troubleshooting Initialization:

If you encounter issues during initialization, check:

1. Database connectivity - ensure your database is running and accessible
2. Permissions - verify your database user has rights to create tables
3. Configuration - double-check your CRUDAdmin configuration parameters
4. Existing admin users - if you're having issues with the initial admin creation, check if an admin user already exists

The initialization process is designed to be idempotent, meaning it's safe to call multiple times - it won't create duplicate tables or admin users if they already exist.

## Adding More Functionality

Once you have the basic admin interface running, you'll want to add more models to manage. Let's create a more complex example with a Product model:

### Step 1: Define the Model

First, we'll create a Product model with validation:

```python
from pydantic import BaseModel, Field, validator
from decimal import Decimal
from datetime import datetime
from typing import Optional

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Decimal, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Step 2: Create Validation Schemas

CRUDAdmin uses Pydantic schemas to validate data before it goes into your database. This helps prevent invalid data and provides better error messages:

```python
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    price: Decimal = Field(..., gt=0)
    description: Optional[str] = Field(None, max_length=500)
    
    @validator("price")
    def validate_price(cls, v):
        if v > 1000000:
            raise ValueError("Price cannot exceed 1,000,000")
        return v

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    price: Optional[Decimal] = Field(None, gt=0)
    description: Optional[str] = None
```

These schemas ensure that:

- Product names are between 2 and 100 characters
- Prices are always positive
- Descriptions are optional but can't exceed 500 characters
- No product can cost more than 1,000,000

### Step 3: Add the Model to CRUDAdmin

Finally, we register our model with the admin interface:

```python
admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    allowed_actions={"view", "create", "update"}  # Disable deletion if needed
)
```

The `allowed_actions` parameter lets you control what users can do with products. Here, we're allowing viewing, creating, and updating, but not deletion - a common pattern for important business data.

## What's Next?

Now that you have your admin interface up and running, it's time to make it secure. Head to the [Security and Authentication](security_authentication.md) section to learn about:

- Setting up robust authentication for your admin users
- Protecting your interface with IP restrictions
- Configuring HTTPS for secure communication
- Implementing best practices for production deployment

Remember: while the setup we've covered here is perfect for development, you'll want to add security measures before going to production!