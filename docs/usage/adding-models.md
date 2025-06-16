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

# With optional select_schema for read operations
admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    select_schema=UserSelect,  # Optional: controls which fields appear in list/update views
    allowed_actions={"view", "create", "update", "delete"}
)
```

### `add_view()` Parameters Overview

The `add_view()` method accepts several parameters to configure your model's admin interface:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | SQLAlchemy Model | ✅ | The database model to manage |
| `create_schema` | Pydantic Schema | ✅ | Schema for creating new records |
| `update_schema` | Pydantic Schema | ✅ | Schema for updating existing records |
| `select_schema` | Pydantic Schema | ❌ | Schema for read operations - excludes problematic fields |
| `update_internal_schema` | Pydantic Schema | ❌ | Internal schema for system updates |
| `delete_schema` | Pydantic Schema | ❌ | Schema for deletion operations |
| `allowed_actions` | Set[str] | ❌ | Controls available operations ("view", "create", "update", "delete") |
| `include_in_models` | bool | ❌ | Whether to show in admin navigation (default: True) |
| `password_transformer` | PasswordTransformer | ❌ | For handling password fields |

!!! tip "Key Benefits of select_schema"
    Use `select_schema` when your model has:
    
    - **TSVector fields** that cause `NotImplementedError`
    - **Large binary/text fields** that slow down list views
    - **Sensitive fields** you want to hide from admin users
    - **Complex computed fields** that break display formatting

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

## Handling Problematic Fields

### Using `select_schema` to Exclude Fields from Read Operations

Some database field types can cause issues in admin panels. The most common example is PostgreSQL's `TSVector` type used for full-text search, which can trigger `NotImplementedError` when trying to display records.

The `select_schema` parameter allows you to exclude problematic fields from all read operations while keeping them available for create/update operations.

??? info "When to Use select_schema"
    Use `select_schema` when you encounter:
    
    - **TSVector fields** causing `NotImplementedError` in admin views
    - **Large binary fields** that slow down list views  
    - **Computed fields** that don't need to be displayed
    - **Sensitive fields** that should be hidden from admin users
    - **Complex JSON fields** that break admin display formatting

### Basic Example: Excluding TSVector Fields

```python
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy_utils import TSVectorType
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# SQLAlchemy model with TSVector for full-text search
class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # This field causes NotImplementedError in admin views
    search_vector = Column(TSVectorType('title', 'content'))

# Schemas for create/update (no search_vector)
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)

class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None

# Schema for read operations (excludes problematic field)
class DocumentSelect(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime
    # search_vector field intentionally excluded!

# Register with admin
admin.add_view(
    model=Document,
    create_schema=DocumentCreate,
    update_schema=DocumentUpdate,
    select_schema=DocumentSelect,  # ✅ TSVector excluded from reads
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Advanced Example: Multiple Problematic Fields

```python
from sqlalchemy import Column, Integer, String, Text, LargeBinary, JSON
from sqlalchemy_utils import TSVectorType
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Problematic fields
    search_vector = Column(TSVectorType('title', 'content'))  # TSVector
    thumbnail_data = Column(LargeBinary)  # Large binary data
    metadata = Column(JSON)  # Complex JSON that breaks display
    internal_notes = Column(Text)  # Sensitive admin-only field

# Create/Update schemas include only safe fields
class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    author_id: int = Field(..., gt=0)

class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)  
    content: Optional[str] = None

# Select schema excludes all problematic fields
class ArticleSelect(BaseModel):
    id: int
    title: str
    content: str
    author_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Excluded: search_vector, thumbnail_data, metadata, internal_notes

admin.add_view(
    model=Article,
    create_schema=ArticleCreate,
    update_schema=ArticleUpdate,
    select_schema=ArticleSelect,  # Multiple problematic fields excluded
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Content-Heavy Models

```python
class BlogPost(Base):
    __tablename__ = "blog_posts"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    slug = Column(String(200), unique=True)
    excerpt = Column(Text)  # Short description for admin list
    content = Column(Text)  # Full content - too long for list view
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    
    # Large fields that slow down list views
    full_content = Column(Text)  # Very long article content
    raw_html = Column(Text)  # HTML version
    search_data = Column(TSVectorType('title', 'excerpt', 'content'))

# Lightweight schema for admin list views
class BlogPostSelect(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: str  # Show excerpt instead of full content
    published: bool
    created_at: datetime
    # Excluded: content, full_content, raw_html, search_data

class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=200)
    excerpt: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    published: bool = False

admin.add_view(
    model=BlogPost,
    create_schema=BlogPostCreate,
    update_schema=BlogPostCreate,
    select_schema=BlogPostSelect,  # Fast loading for admin lists
    allowed_actions={"view", "create", "update", "delete"}
)
```

### Security-Sensitive Fields

```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True)
    email = Column(String(100), unique=True)
    role = Column(String(20), default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    # Sensitive fields to hide from admin views
    hashed_password = Column(String(128))  # Password hash
    reset_token = Column(String(128))  # Password reset token
    login_attempts = Column(Integer, default=0)  # Security tracking
    last_login_ip = Column(String(45))  # IP address

# Admin-safe schema excludes sensitive security fields
class UserAdminSelect(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    # Excluded: hashed_password, reset_token, login_attempts, last_login_ip

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    role: str = Field(default="user", pattern="^(admin|user|moderator)$")
    is_active: bool = True
    password: str = Field(..., min_length=8)  # Will be hashed automatically

admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    select_schema=UserAdminSelect,  # Sensitive fields hidden
    password_transformer=password_transformer,
    allowed_actions={"view", "create", "update"}
)
```

### Key Benefits

??? success "Advantages of using select_schema"
    **Performance:**
    - Faster list views by excluding large fields
    - Reduced database query size and network transfer
    
    **Reliability:**
    - Prevents `NotImplementedError` from problematic field types
    - Avoids display issues with complex data structures
    
    **Security:**
    - Hides sensitive fields from admin interface
    - Maintains field access for create/update operations
    
    **User Experience:**
    - Cleaner admin interface with relevant fields only
    - Better responsive design without wide data columns

### Best Practices

!!! tip "select_schema Guidelines"
    1. **Always include primary key** (`id`) in select schemas
    2. **Include display-friendly fields** like names, titles, dates
    3. **Exclude large binary data** that slows down queries
    4. **Hide sensitive security fields** like password hashes
    5. **Test admin views** after adding select_schema to ensure proper display
    6. **Keep create/update schemas separate** to maintain full field access

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
- **[Handle Problematic Fields](#handling-problematic-fields)** to solve TSVector and performance issues

For more advanced features like custom field widgets and complex relationships, see the [Advanced Section](../advanced/overview.md). 