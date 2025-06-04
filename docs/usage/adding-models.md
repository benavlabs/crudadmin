# Adding Models to Your Admin Interface

This guide explains how to register your SQLAlchemy models with CRUDAdmin to create a fully functional admin interface. You'll learn how to configure models, set up schemas, control actions, and handle special field types.

## Prerequisites

Before adding models to your admin interface, ensure you have:

- SQLAlchemy models defined with proper table structure
- Corresponding Pydantic schemas for data validation
- CRUDAdmin instance created and configured (see [Quick Start](../quick-start.md))

---

## Basic Model Registration

### Step 1: Define Your SQLAlchemy Model

First, create your SQLAlchemy model with proper field definitions:

??? example "User Model Example"
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
        updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    ```

### Step 2: Create Pydantic Schemas

Define schemas for create and update operations:

??? example "User Schema Examples"
    ```python
    from pydantic import BaseModel, EmailStr, Field
    from typing import Optional
    from datetime import datetime

    class UserCreate(BaseModel):
        username: str = Field(..., min_length=3, max_length=50)
        email: EmailStr
        role: str = Field(default="user", pattern="^(admin|user|moderator)$")
        is_active: bool = True

        class Config:
            json_schema_extra = {
                "example": {
                    "username": "johndoe",
                    "email": "john@example.com",
                    "role": "user",
                    "is_active": True
                }
            }

    class UserUpdate(BaseModel):
        email: Optional[EmailStr] = None
        role: Optional[str] = Field(None, pattern="^(admin|user|moderator)$")
        is_active: Optional[bool] = None

        class Config:
            json_schema_extra = {
                "example": {
                    "email": "newemail@example.com",
                    "role": "moderator",
                    "is_active": False
                }
            }
    ```

### Step 3: Register with CRUDAdmin

Use the `add_view()` method to register your model:

```python
# Basic model registration
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)
```

---

## Action Control

### Configuring Allowed Actions

Control which operations are available for each model:

```python
# Read-only model (view only)
admin.add_view(
    model=AuditLog,
    create_schema=AuditLogSchema,
    update_schema=AuditLogSchema,
    allowed_actions={"view"}  # Only viewing allowed
)

# No deletion allowed
admin.add_view(
    model=Order,
    create_schema=OrderCreate,
    update_schema=OrderUpdate,
    allowed_actions={"view", "create", "update"}  # No delete
)

# Full access (default)
admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Available Actions

| Action | Description | Generated Routes |
|--------|-------------|------------------|
| `"view"` | Read and list records | `GET /admin/{model}/`, `GET /admin/{model}/{id}` |
| `"create"` | Create new records | `GET /admin/{model}/create`, `POST /admin/{model}/create` |
| `"update"` | Edit existing records | `GET /admin/{model}/update/{id}`, `POST /admin/{model}/update/{id}` |
| `"delete"` | Delete records | `POST /admin/{model}/delete/{id}` |

---

## Advanced Schema Configuration

### Using Different Schemas for Different Operations

```python
class UserCreateAdmin(BaseModel):
    """Schema with more fields for admin creation"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|user|moderator)$")
    is_active: bool = True
    notes: Optional[str] = Field(None, max_length=500)

class UserUpdateAdmin(BaseModel):
    """Schema with admin-specific update fields"""
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern="^(admin|user|moderator)$")
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=500)

class UserUpdateInternal(BaseModel):
    """Internal schema for system updates"""
    last_login: Optional[datetime] = None
    login_count: Optional[int] = None

admin.add_view(
    model=User,
    create_schema=UserCreateAdmin,
    update_schema=UserUpdateAdmin,
    update_internal_schema=UserUpdateInternal,  # For internal operations
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Custom Delete Schema

Define specific fields required for deletion:

```python
class ProductDelete(BaseModel):
    """Require reason for product deletion"""
    reason: str = Field(..., min_length=10, max_length=200)
    archive_inventory: bool = Field(default=True)

admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    delete_schema=ProductDelete,  # Custom deletion form
    allowed_actions={"view", "create", "update", "delete"}
)
```

---

## Password Field Handling

### Setting Up Password Transformation

For models with password fields, use `PasswordTransformer`:

```python
from crudadmin.admin_interface.model_view import PasswordTransformer
import bcrypt

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

class UserCreateWithPassword(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)  # This gets transformed
    role: str = Field(default="user")

class UserUpdateWithPassword(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)  # Optional password update
    role: Optional[str] = None

# Create password transformer
password_transformer = PasswordTransformer(
    password_field="password",           # Field in Pydantic schema
    hashed_field="hashed_password",      # Field in SQLAlchemy model
    hash_function=hash_password,         # Your hashing function
    required_fields=["username", "email"] # Required fields for validation
)

admin.add_view(
    model=User,
    create_schema=UserCreateWithPassword,
    update_schema=UserUpdateWithPassword,
    password_transformer=password_transformer,
    allowed_actions={"view", "create", "update", "delete"}
)
```

---

## Real-World Examples

### E-commerce Models

```python
# Product Management
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    price: Decimal = Field(..., gt=0, decimal_places=2)
    description: Optional[str] = Field(None, max_length=1000)
    category_id: Optional[int] = None
    sku: str = Field(..., regex=r'^[A-Z0-9-]+$')
    in_stock: bool = True

admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    allowed_actions={"view", "create", "update"}  # No deletion for products
)

# Order Management (Read-only for admins)
admin.add_view(
    model=Order,
    create_schema=OrderSchema,
    update_schema=OrderSchema,
    allowed_actions={"view"}  # Orders are read-only in admin
)
```

### Content Management

```python
# Blog Post Management
class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    content: str = Field(..., min_length=50)
    author_id: int
    category: str = Field(..., pattern="^(tech|business|personal)$")
    published: bool = False
    tags: List[str] = Field(default_factory=list, max_items=10)

class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    content: Optional[str] = Field(None, min_length=50)
    category: Optional[str] = Field(None, pattern="^(tech|business|personal)$")
    published: Optional[bool] = None
    tags: Optional[List[str]] = Field(None, max_items=10)

admin.add_view(
    model=BlogPost,
    create_schema=BlogPostCreate,
    update_schema=BlogPostUpdate,
    allowed_actions={"view", "create", "update", "delete"}
)
```

### User Management with Roles

```python
class UserManagementCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(admin|moderator|user)$")
    department: Optional[str] = None
    is_active: bool = True
    
    @validator('password')
    def validate_password(cls, v):
        if not re.search(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]', v):
            raise ValueError('Password must contain letters, numbers, and special characters')
        return v

admin.add_view(
    model=User,
    create_schema=UserManagementCreate,
    update_schema=UserManagementUpdate,
    password_transformer=password_transformer,
    allowed_actions={"view", "create", "update"}  # No user deletion
)
```

---

## Advanced Configuration Options

### Excluding Models from Navigation

```python
# Add model but don't show in main navigation
admin.add_view(
    model=InternalLog,
    create_schema=InternalLogSchema,
    update_schema=InternalLogSchema,
    include_in_models=False,  # Hidden from main navigation
    allowed_actions={"view"}
)
```

### Custom Field Validation

```python
class ProductCreateAdvanced(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    price: Decimal = Field(..., gt=0, le=999999.99, decimal_places=2)
    weight: Optional[float] = Field(None, gt=0, le=1000)
    dimensions: Optional[str] = Field(None, regex=r'^\d+x\d+x\d+$')
    
    @validator('name')
    def validate_name(cls, v):
        if any(char in v for char in ['<', '>', '&']):
            raise ValueError('Product name cannot contain HTML characters')
        return v.title()  # Auto-capitalize
    
    @validator('price')
    def validate_price(cls, v):
        if v > 10000:
            raise ValueError('Price cannot exceed $10,000')
        return v

admin.add_view(
    model=Product,
    create_schema=ProductCreateAdvanced,
    update_schema=ProductUpdateAdvanced,
    allowed_actions={"view", "create", "update", "delete"}
)
```

---

## Common Patterns and Best Practices

### 1. Audit Fields

```python
class BaseSchema(BaseModel):
    """Base schema with common audit fields"""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        # Don't include audit fields in forms (auto-generated)
        fields = {'created_at': {'exclude': True}, 'updated_at': {'exclude': True}}
```

### 2. Enum Fields

```python
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.USER  # Enum becomes dropdown in admin
```

### 3. File Upload Fields

```python
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=100)
    file_path: str  # File handling would be custom
    file_type: str = Field(..., pattern="^(pdf|doc|docx|txt)$")
    size_mb: float = Field(..., gt=0, le=50)
```

---

## Troubleshooting

### Common Issues

**Schema Validation Errors:**
```python
# ❌ Incorrect - Field names don't match model
class UserCreate(BaseModel):
    user_name: str  # Model has 'username'
    
# ✅ Correct - Field names match model
class UserCreate(BaseModel):
    username: str
```

**Missing Required Fields:**
```python
# ❌ Incorrect - Missing required model fields
class UserCreate(BaseModel):
    username: str
    # Missing 'email' which is required in model
    
# ✅ Correct - All required fields included
class UserCreate(BaseModel):
    username: str
    email: EmailStr
```

**Action Configuration:**
```python
# ❌ Incorrect - Typo in action name
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    allowed_actions={"view", "create", "updates"}  # Should be "update"
)
```

### Debugging Tips

1. **Check Model Field Names**: Ensure Pydantic schema fields match SQLAlchemy model columns
2. **Validate Schema Examples**: Use Pydantic's validation to test your schemas
3. **Test Action Permissions**: Verify allowed_actions contain valid strings
4. **Check Password Transformer**: Ensure field names match between schema and model

---

## Next Steps

Once you've successfully added models to your admin interface:

- **[Configure Basic Settings](configuration.md)** to customize your admin interface
- **[Manage Admin Users](admin-users.md)** to set up proper access control
- **[Learn the Interface](interface.md)** to effectively use your new admin panel

For more advanced features like custom field widgets and complex relationships, see the [Advanced Section](../advanced/overview.md). 