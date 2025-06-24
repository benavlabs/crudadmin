# Common Patterns

This guide demonstrates common real-world patterns and scenarios you'll encounter when building admin interfaces with CRUDAdmin. Each pattern includes complete examples with models, schemas, and configuration.

## Prerequisites

- Basic understanding of [Adding Models](adding-models.md)
- Familiarity with [Admin Interface](interface.md) operations
- Knowledge of SQLAlchemy relationships and Pydantic schemas

---

## Multi-Model Relationships

### Blog System Pattern

A common pattern is managing content with related models (users, posts, comments, tags).

??? note "Complete Blog System Models"
    ```python
    # models.py
    from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Table
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship
    from datetime import datetime

    Base = declarative_base()

    # Many-to-many association table
    post_tags = Table('post_tags', Base.metadata,
        Column('post_id', Integer, ForeignKey('posts.id')),
        Column('tag_id', Integer, ForeignKey('tags.id'))
    )

    class User(Base):
        __tablename__ = "users"
        
        id = Column(Integer, primary_key=True, index=True)
        username = Column(String(50), unique=True, index=True)
        email = Column(String(100), unique=True, index=True)
        full_name = Column(String(100))
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Relationships
        posts = relationship("Post", back_populates="author")
        comments = relationship("Comment", back_populates="author")

    class Category(Base):
        __tablename__ = "categories"
        
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(50), unique=True)
        description = Column(Text)
        
        # Relationships
        posts = relationship("Post", back_populates="category")

    class Tag(Base):
        __tablename__ = "tags"
        
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(30), unique=True)
        color = Column(String(7))  # Hex color code
        
        # Relationships
        posts = relationship("Post", secondary=post_tags, back_populates="tags")

    class Post(Base):
        __tablename__ = "posts"
        
        id = Column(Integer, primary_key=True, index=True)
        title = Column(String(200))
        content = Column(Text)
        excerpt = Column(String(500))
        author_id = Column(Integer, ForeignKey("users.id"))
        category_id = Column(Integer, ForeignKey("categories.id"))
        published = Column(Boolean, default=False)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        # Relationships
        author = relationship("User", back_populates="posts")
        category = relationship("Category", back_populates="posts")
        comments = relationship("Comment", back_populates="post")
        tags = relationship("Tag", secondary=post_tags, back_populates="posts")

    class Comment(Base):
        __tablename__ = "comments"
        
        id = Column(Integer, primary_key=True, index=True)
        content = Column(Text)
        author_id = Column(Integer, ForeignKey("users.id"))
        post_id = Column(Integer, ForeignKey("posts.id"))
        approved = Column(Boolean, default=False)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Relationships
        author = relationship("User", back_populates="comments")
        post = relationship("Post", back_populates="comments")
    ```

??? note "Pydantic Schemas for Blog System"
    ```python
    # schemas.py
    from pydantic import BaseModel, EmailStr, Field
    from datetime import datetime
    from typing import Optional, List

    # User Schemas
    class UserBase(BaseModel):
        username: str = Field(..., min_length=3, max_length=50)
        email: EmailStr
        full_name: str = Field(..., max_length=100)
        is_active: bool = True

    class UserCreate(UserBase):
        pass

    class UserUpdate(UserBase):
        username: Optional[str] = Field(None, min_length=3, max_length=50)
        email: Optional[EmailStr] = None
        full_name: Optional[str] = Field(None, max_length=100)
        is_active: Optional[bool] = None

    class UserRead(UserBase):
        id: int
        created_at: datetime
        
        class Config:
            from_attributes = True

    # Category Schemas
    class CategoryBase(BaseModel):
        name: str = Field(..., max_length=50)
        description: Optional[str] = None

    class CategoryCreate(CategoryBase):
        pass

    class CategoryUpdate(CategoryBase):
        name: Optional[str] = Field(None, max_length=50)

    class CategoryRead(CategoryBase):
        id: int
        
        class Config:
            from_attributes = True

    # Tag Schemas
    class TagBase(BaseModel):
        name: str = Field(..., max_length=30)
        color: str = Field(..., regex=r'^#[0-9A-Fa-f]{6}$')

    class TagCreate(TagBase):
        pass

    class TagUpdate(TagBase):
        name: Optional[str] = Field(None, max_length=30)
        color: Optional[str] = Field(None, regex=r'^#[0-9A-Fa-f]{6}$')

    class TagRead(TagBase):
        id: int
        
        class Config:
            from_attributes = True

    # Post Schemas
    class PostBase(BaseModel):
        title: str = Field(..., max_length=200)
        content: str
        excerpt: Optional[str] = Field(None, max_length=500)
        category_id: int
        published: bool = False

    class PostCreate(PostBase):
        author_id: int

    class PostUpdate(PostBase):
        title: Optional[str] = Field(None, max_length=200)
        content: Optional[str] = None
        category_id: Optional[int] = None
        published: Optional[bool] = None

    class PostRead(PostBase):
        id: int
        author_id: int
        created_at: datetime
        updated_at: datetime
        
        class Config:
            from_attributes = True

    # Comment Schemas
    class CommentBase(BaseModel):
        content: str

    class CommentCreate(CommentBase):
        author_id: int
        post_id: int

    class CommentUpdate(CommentBase):
        content: Optional[str] = None
        approved: Optional[bool] = None

    class CommentRead(CommentBase):
        id: int
        author_id: int
        post_id: int
        approved: bool
        created_at: datetime
        
        class Config:
            from_attributes = True
    ```

#### Registration Pattern

```python
from crudadmin import CRUDAdmin
from models import User, Category, Tag, Post, Comment
from schemas import (
    UserCreate, UserUpdate, UserRead,
    CategoryCreate, CategoryUpdate, CategoryRead,
    TagCreate, TagUpdate, TagRead,
    PostCreate, PostUpdate, PostRead,
    CommentCreate, CommentUpdate, CommentRead
)

# Initialize CRUDAdmin
crud_admin = CRUDAdmin(
    session_backend="database",
    secret_key="your-secret-key-here",
    title="Blog Admin"
)

# Register models in logical order
crud_admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    read_schema=UserRead
)

crud_admin.add_view(
    model=Category,
    create_schema=CategoryCreate,
    update_schema=CategoryUpdate,
    read_schema=CategoryRead
)

crud_admin.add_view(
    model=Tag,
    create_schema=TagCreate,
    update_schema=TagUpdate,
    read_schema=TagRead
)

crud_admin.add_view(
    model=Post,
    create_schema=PostCreate,
    update_schema=PostUpdate,
    read_schema=PostRead
)

crud_admin.add_view(
    model=Comment,
    create_schema=CommentCreate,
    update_schema=CommentUpdate,
    read_schema=CommentRead
)
```

#### Why This Pattern Works

1. **Clear hierarchy**: Users → Categories/Tags → Posts → Comments
2. **Manageable complexity**: Each model has focused responsibility
3. **Relationship visibility**: Foreign key fields show in forms
4. **Data integrity**: Relationships enforce referential integrity

---

## E-commerce Management Pattern

### Product Catalog System

Managing products, inventory, orders, and customers in an e-commerce admin.

??? note "E-commerce Models"
    ```python
    # ecommerce_models.py
    from sqlalchemy import Column, Integer, String, Decimal, ForeignKey, DateTime, Boolean, Text
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import relationship
    from datetime import datetime
    from decimal import Decimal as PyDecimal

    Base = declarative_base()

    class Customer(Base):
        __tablename__ = "customers"
        
        id = Column(Integer, primary_key=True, index=True)
        email = Column(String(100), unique=True, index=True)
        first_name = Column(String(50))
        last_name = Column(String(50))
        phone = Column(String(20))
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Relationships
        orders = relationship("Order", back_populates="customer")

    class ProductCategory(Base):
        __tablename__ = "product_categories"
        
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(100), unique=True)
        description = Column(Text)
        is_active = Column(Boolean, default=True)
        
        # Relationships
        products = relationship("Product", back_populates="category")

    class Product(Base):
        __tablename__ = "products"
        
        id = Column(Integer, primary_key=True, index=True)
        sku = Column(String(50), unique=True, index=True)
        name = Column(String(200))
        description = Column(Text)
        price = Column(Decimal(10, 2))
        cost = Column(Decimal(10, 2))
        category_id = Column(Integer, ForeignKey("product_categories.id"))
        stock_quantity = Column(Integer, default=0)
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        
        # Relationships
        category = relationship("ProductCategory", back_populates="products")
        order_items = relationship("OrderItem", back_populates="product")

    class Order(Base):
        __tablename__ = "orders"
        
        id = Column(Integer, primary_key=True, index=True)
        order_number = Column(String(20), unique=True, index=True)
        customer_id = Column(Integer, ForeignKey("customers.id"))
        status = Column(String(20), default="pending")  # pending, processing, shipped, delivered, cancelled
        total_amount = Column(Decimal(10, 2))
        shipping_address = Column(Text)
        order_date = Column(DateTime, default=datetime.utcnow)
        shipped_date = Column(DateTime, nullable=True)
        
        # Relationships
        customer = relationship("Customer", back_populates="orders")
        items = relationship("OrderItem", back_populates="order")

    class OrderItem(Base):
        __tablename__ = "order_items"
        
        id = Column(Integer, primary_key=True, index=True)
        order_id = Column(Integer, ForeignKey("orders.id"))
        product_id = Column(Integer, ForeignKey("products.id"))
        quantity = Column(Integer)
        unit_price = Column(Decimal(10, 2))
        total_price = Column(Decimal(10, 2))
        
        # Relationships
        order = relationship("Order", back_populates="items")
        product = relationship("Product", back_populates="order_items")
    ```

??? note "E-commerce Schemas"
    ```python
    # ecommerce_schemas.py
    from pydantic import BaseModel, EmailStr, Field, field_validator
    from datetime import datetime
    from typing import Optional
    from decimal import Decimal
    from enum import Enum

    class OrderStatus(str, Enum):
        pending = "pending"
        processing = "processing"
        shipped = "shipped"
        delivered = "delivered"
        cancelled = "cancelled"

    # Customer Schemas
    class CustomerBase(BaseModel):
        email: EmailStr
        first_name: str = Field(..., max_length=50)
        last_name: str = Field(..., max_length=50)
        phone: Optional[str] = Field(None, max_length=20)
        is_active: bool = True

    class CustomerCreate(CustomerBase):
        pass

    class CustomerUpdate(CustomerBase):
        email: Optional[EmailStr] = None
        first_name: Optional[str] = Field(None, max_length=50)
        last_name: Optional[str] = Field(None, max_length=50)

    class CustomerRead(CustomerBase):
        id: int
        created_at: datetime
        
        class Config:
            from_attributes = True

    # Product Category Schemas
    class ProductCategoryBase(BaseModel):
        name: str = Field(..., max_length=100)
        description: Optional[str] = None
        is_active: bool = True

    class ProductCategoryCreate(ProductCategoryBase):
        pass

    class ProductCategoryUpdate(ProductCategoryBase):
        name: Optional[str] = Field(None, max_length=100)
        is_active: Optional[bool] = None

    class ProductCategoryRead(ProductCategoryBase):
        id: int
        
        class Config:
            from_attributes = True

    # Product Schemas
    class ProductBase(BaseModel):
        sku: str = Field(..., max_length=50)
        name: str = Field(..., max_length=200)
        description: Optional[str] = None
        price: Decimal = Field(..., gt=0, decimal_places=2)
        cost: Decimal = Field(..., ge=0, decimal_places=2)
        category_id: int
        stock_quantity: int = Field(..., ge=0)
        is_active: bool = True

        @field_validator('price', 'cost')
        @classmethod
        def validate_price(cls, v):
            if v <= 0:
                raise ValueError('Price and cost must be positive')
            return v

    class ProductCreate(ProductBase):
        pass

    class ProductUpdate(ProductBase):
        sku: Optional[str] = Field(None, max_length=50)
        name: Optional[str] = Field(None, max_length=200)
        price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
        cost: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
        category_id: Optional[int] = None
        stock_quantity: Optional[int] = Field(None, ge=0)
        is_active: Optional[bool] = None

    class ProductRead(ProductBase):
        id: int
        created_at: datetime
        
        class Config:
            from_attributes = True

    # Order Schemas
    class OrderBase(BaseModel):
        customer_id: int
        status: OrderStatus = OrderStatus.pending
        shipping_address: str
        
    class OrderCreate(OrderBase):
        order_number: str = Field(..., max_length=20)
        total_amount: Decimal = Field(..., ge=0, decimal_places=2)

    class OrderUpdate(BaseModel):
        status: Optional[OrderStatus] = None
        shipping_address: Optional[str] = None
        shipped_date: Optional[datetime] = None

    class OrderRead(OrderBase):
        id: int
        order_number: str
        total_amount: Decimal
        order_date: datetime
        shipped_date: Optional[datetime]
        
        class Config:
            from_attributes = True
    ```

#### E-commerce Admin Setup

```python
from crudadmin import CRUDAdmin
from ecommerce_models import Customer, ProductCategory, Product, Order, OrderItem
from ecommerce_schemas import (
    CustomerCreate, CustomerUpdate, CustomerRead,
    ProductCategoryCreate, ProductCategoryUpdate, ProductCategoryRead,
    ProductCreate, ProductUpdate, ProductRead,
    OrderCreate, OrderUpdate, OrderRead
)

# Configure for e-commerce scale
from crudadmin import CRUDAdmin, RedisConfig

redis_config = RedisConfig(url="redis://localhost:6379")
crud_admin = CRUDAdmin(
    session_backend="redis",  # Better for high traffic
    redis_config=redis_config,
    secret_key="your-ecommerce-secret-key",
    title="E-commerce Admin",
    default_page_size=50,  # More records per page
    max_page_size=200
)

# Register in business workflow order
crud_admin.add_view(
    model=ProductCategory,
    create_schema=ProductCategoryCreate,
    update_schema=ProductCategoryUpdate,
    read_schema=ProductCategoryRead
)

crud_admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    read_schema=ProductRead
)

crud_admin.add_view(
    model=Customer,
    create_schema=CustomerCreate,
    update_schema=CustomerUpdate,
    read_schema=CustomerRead
)

crud_admin.add_view(
    model=Order,
    create_schema=OrderCreate,
    update_schema=OrderUpdate,
    read_schema=OrderRead
)
```

#### Why This E-commerce Pattern Works

1. **Business logic validation**: Price/cost validation in schemas
2. **Enum handling**: Order status as proper enums
3. **Decimal precision**: Proper handling of money values
4. **Scalable session backend**: Redis for high traffic
5. **Larger page sizes**: Better for inventory management

---

## Role-Based Access Pattern

!!! note "Workaround Pattern"
    **Important**: CRUDAdmin does not currently support built-in role-based access control. The patterns shown below are workarounds that create separate admin instances with different configurations to simulate different access levels. 
    
    Future versions of CRUDAdmin may include native RBAC features. For now, use these patterns if you need different admin interfaces for different user roles.

### Different Admin Levels

Creating different access levels for various admin roles using separate CRUDAdmin instances.

#### Super Admin Pattern

```python
from crudadmin import CRUDAdmin

# Super Admin - Full access
super_admin = CRUDAdmin(
    session_backend="redis",
    secret_key="super-admin-secret",
    title="Super Admin Panel",
    mount_path="/superadmin"
)

# All models with full CRUD
super_admin.add_view(
    model=User,
    create_schema=UserCreate,
    update_schema=UserUpdate,
    read_schema=UserRead,
    # Full permissions (default)
)

super_admin.add_view(
    model=Order,
    create_schema=OrderCreate,
    update_schema=OrderUpdate,
    read_schema=OrderRead
)
```

#### Content Editor Pattern

```python
# Content Editor - Limited access
content_admin = CRUDAdmin(
    session_backend="redis",
    secret_key="content-editor-secret", 
    title="Content Editor",
    mount_path="/content"
)

# Posts - Full access
content_admin.add_view(
    model=Post,
    create_schema=PostCreate,
    update_schema=PostUpdate,
    read_schema=PostRead
)

# Comments - Read and moderate only
content_admin.add_view(
    model=Comment,
    create_schema=None,  # No creation
    update_schema=CommentModerationUpdate,  # Limited updates
    read_schema=CommentRead,
    delete_permission=True  # Can delete inappropriate comments
)

# Users - Read only
content_admin.add_view(
    model=User,
    create_schema=None,
    update_schema=None,
    read_schema=UserRead,
    delete_permission=False
)
```

#### Customer Service Pattern

```python
# Customer Service - Customer and order focus
service_admin = CRUDAdmin(
    session_backend="redis",
    secret_key="service-secret",
    title="Customer Service",
    mount_path="/service"
)

# Customers - Full access
service_admin.add_view(
    model=Customer,
    create_schema=CustomerCreate,
    update_schema=CustomerUpdate,
    read_schema=CustomerRead
)

# Orders - Update status only
service_admin.add_view(
    model=Order,
    create_schema=None,  # No new order creation
    update_schema=OrderStatusUpdate,  # Status changes only
    read_schema=OrderRead,
    delete_permission=False  # Cannot delete orders
)

# Products - Read only for reference
service_admin.add_view(
    model=Product,
    create_schema=None,
    update_schema=None,
    read_schema=ProductRead,
    delete_permission=False
)
```

#### Implementation Considerations

When using this workaround pattern:

**Pros:**

- ✅ Simple to implement and understand
- ✅ Complete separation between different access levels
- ✅ Different URLs for different roles (`/superadmin`, `/content`, `/service`)
- ✅ Independent authentication for each role

**Cons:**

- ❌ Requires separate admin instances and maintenance
- ❌ No shared user session across different admin interfaces
- ❌ Duplicate configuration and setup code
- ❌ Users need separate credentials for different admin areas

**Future RBAC Features:**

When CRUDAdmin adds native role-based access control, you'll be able to:

- Define roles and permissions in a single admin instance
- Control model visibility and actions per user role
- Share sessions across the same admin interface
- Dynamically show/hide features based on user permissions

---

## Advanced Validation Patterns

### Business Logic Validation

Complex validation rules that go beyond basic field validation.

#### Inventory Management Validation

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Dict, Any
from typing_extensions import Self

class ProductUpdateAdvanced(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('price')
    @classmethod
    def price_must_be_reasonable(cls, v):
        if v is not None and v > 10000:
            raise ValueError('Price cannot exceed $10,000')
        return v

    @field_validator('stock_quantity') 
    @classmethod
    def stock_cannot_be_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError('Stock quantity cannot be negative')
        return v

    @model_validator(mode='after')
    def price_above_cost(self) -> Self:
        if self.price is not None and self.cost is not None:
            if self.price <= self.cost:
                raise ValueError('Price must be greater than cost')
        return self

    @model_validator(mode='after')
    def deactivate_out_of_stock(self) -> Self:
        if self.stock_quantity is not None and self.stock_quantity == 0 and self.is_active is True:
            raise ValueError('Cannot activate product with zero stock')
        return self
```

#### Order Processing Validation

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from typing_extensions import Self
from datetime import datetime, timedelta

class OrderUpdateAdvanced(BaseModel):
    status: Optional[OrderStatus] = None
    shipped_date: Optional[datetime] = None
    tracking_number: Optional[str] = None

    @field_validator('shipped_date')
    @classmethod
    def shipped_date_reasonable(cls, v):
        if v is not None:
            if v < datetime.utcnow().replace(tzinfo=None):
                raise ValueError('Shipped date cannot be in the past')
            if v > datetime.utcnow().replace(tzinfo=None) + timedelta(days=30):
                raise ValueError('Shipped date too far in future')
        return v

    @model_validator(mode='after')
    def status_transition_rules(self) -> Self:
        if self.status == OrderStatus.shipped:
            if not self.shipped_date:
                raise ValueError('Shipped orders must have shipped date')
            if not self.tracking_number:
                raise ValueError('Shipped orders must have tracking number')
                
        if self.status == OrderStatus.delivered:
            if not self.shipped_date:
                raise ValueError('Delivered orders must have been shipped first')
                
        return self
```

---

## Performance Optimization Patterns

### Large Dataset Management

Optimizing CRUDAdmin for applications with millions of records.

#### Pagination Strategy

```python
# Configure for large datasets
crud_admin = CRUDAdmin(
    session_backend="redis",
    secret_key="your-key",
    title="High Volume Admin",
    default_page_size=25,  # Smaller default for faster loading
    max_page_size=100,     # Prevent excessive queries
    session_timeout=1800   # 30 minutes for long admin sessions
)

# Enable database indexes in your models
class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, index=True)  # Indexed for fast lookup
    name = Column(String(200), index=True)             # Indexed for search
    category_id = Column(Integer, ForeignKey("categories.id"), index=True)  # Indexed FK
    price = Column(Decimal(10, 2), index=True)         # Indexed for sorting
    is_active = Column(Boolean, default=True, index=True)  # Indexed for filtering
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # Indexed for sorting
```

#### Memory-Efficient Schema Patterns

```python
# Lightweight read schemas for list views
class ProductListRead(BaseModel):
    id: int
    sku: str
    name: str
    price: Decimal
    is_active: bool
    
    class Config:
        from_attributes = True

# Detailed schema for individual record views
class ProductDetailRead(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    price: Decimal
    cost: Decimal
    category_id: int
    stock_quantity: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Use lightweight schema for list operations
crud_admin.add_view(
    model=Product,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    read_schema=ProductListRead  # Faster list loading
)
```

---

## Integration Patterns

### Existing FastAPI Application

Integrating CRUDAdmin into an existing FastAPI application without conflicts.

#### Modular Integration

```python
# main.py - Your existing FastAPI app
from fastapi import FastAPI
from your_app.routers import api_router
from admin.setup import setup_admin

# Your existing app
app = FastAPI(title="Your API")

# Your existing routes
app.include_router(api_router, prefix="/api/v1")

# Add admin interface
admin_app = setup_admin()
app.mount("/admin", admin_app)

# Your existing startup/shutdown events
@app.on_event("startup")
async def startup():
    # Your existing startup code
    pass
```

```python
# admin/setup.py - Separate admin configuration
from crudadmin import CRUDAdmin
from your_app.models import User, Product, Order
from admin.schemas import AdminUserRead, AdminProductRead, AdminOrderRead

def setup_admin():
    """Configure and return admin application"""
    crud_admin = CRUDAdmin(
        session_backend="database",
        database_url="sqlite:///./admin_sessions.db",  # Separate admin DB
        secret_key="admin-secret-key",
        title="Your App Admin",
        mount_path=""  # Mounted at /admin already
    )
    
    # Register your models
    crud_admin.add_view(
        model=User,
        create_schema=UserCreate,
        update_schema=UserUpdate,
        read_schema=AdminUserRead
    )
    
    crud_admin.add_view(
        model=Product,
        create_schema=ProductCreate,
        update_schema=ProductUpdate,
        read_schema=AdminProductRead
    )
    
    crud_admin.add_view(
        model=Order,
        create_schema=OrderCreate,
        update_schema=OrderUpdate,
        read_schema=AdminOrderRead
    )
    
    return crud_admin.get_app()
```

#### Environment-Based Configuration

```python
# admin/config.py
import os
from typing import Optional

class AdminConfig:
    SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "change-this-in-production")
    SESSION_BACKEND: str = os.getenv("ADMIN_SESSION_BACKEND", "database")
    REDIS_URL: Optional[str] = os.getenv("ADMIN_REDIS_URL")
    DATABASE_URL: str = os.getenv("ADMIN_DATABASE_URL", "sqlite:///./admin_sessions.db")
    TITLE: str = os.getenv("ADMIN_TITLE", "Admin Panel")
    DEBUG: bool = os.getenv("ADMIN_DEBUG", "false").lower() == "true"

# Use in setup
def setup_admin():
    from crudadmin import CRUDAdmin, RedisConfig
    
    config = AdminConfig()
    
    # Configure Redis if URL provided
    redis_config = None
    if config.REDIS_URL:
        redis_config = RedisConfig(url=config.REDIS_URL)
    
    crud_admin = CRUDAdmin(
        session_backend=config.SESSION_BACKEND,
        redis_config=redis_config,
        database_url=config.DATABASE_URL,
        secret_key=config.SECRET_KEY,
        title=config.TITLE
    )
    
    # Register models...
    return crud_admin.get_app()
```

---

## Security Patterns

### Production Security Configuration

Comprehensive security setup for production environments using built-in CRUDAdmin security features.

#### Built-in IP Restrictions

CRUDAdmin provides built-in IP restriction functionality:

```python
from crudadmin import CRUDAdmin
import os

# Production security configuration with built-in IP restrictions
from crudadmin import CRUDAdmin, RedisConfig

redis_config = RedisConfig(url=os.getenv("REDIS_URL"))

crud_admin = CRUDAdmin(
    # Session security
    session_backend="redis",
    redis_config=redis_config,
    secret_key=os.getenv("ADMIN_SECRET_KEY"),  # Strong random key
    
    # Session management settings
    session_timeout_minutes=60,  # 1 hour timeout
    max_sessions_per_user=5,
    
    # Built-in IP restrictions
    allowed_ips=["127.0.0.1", "192.168.1.100"],  # Specific IPs
    allowed_networks=["192.168.1.0/24", "10.0.0.0/8"],  # Network ranges
    
    # Additional security
    secure_cookies=True,
    enforce_https=True
)
```

---

## Next Steps

Master these common patterns to build robust admin interfaces. For more advanced features and configurations, see the **[Advanced Topics](../advanced/overview.md)** section.

These patterns provide the foundation for most real-world CRUDAdmin implementations. Combine them based on your specific requirements to create powerful, efficient admin interfaces.