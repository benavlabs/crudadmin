import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Type,
    TypeAlias,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ..admin_interface.auth import AdminAuthentication
from ..admin_interface.middleware.auth import AdminAuthMiddleware
from ..admin_interface.middleware.ip_restriction import IPRestrictionMiddleware
from ..admin_user.schemas import AdminUserCreate, AdminUserCreateInternal
from ..admin_user.service import AdminUserService
from ..core.db import AdminBase, DatabaseConfig
from ..session import SessionManager, create_admin_session_model
from .admin_site import AdminSite
from .model_view import ModelView
from .typing import RouteResponse

logger = logging.getLogger("crudadmin")

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
SchemaType = TypeVar("SchemaType", bound=BaseModel)
EndpointFunction: TypeAlias = Callable[
    [Request, AsyncSession], Awaitable[RouteResponse]
]


class ModelConfig(TypedDict):
    model: Type[DeclarativeBase]
    create_schema: Type[BaseModel]
    update_schema: Type[BaseModel]
    update_internal_schema: Optional[Type[BaseModel]]
    delete_schema: Optional[Type[BaseModel]]
    crud: FastCRUD


class AdminModelProtocol:
    """
    Protocol-like class to indicate an Admin model.
    (For simpler mypy compatibility, we avoid `Protocol` here and
    ensure it fits `DeclarativeBase`.)
    """

    __tablename__: str
    metadata: Any


class CRUDAdmin:
    """
    FastAPI-based admin interface for managing database models and authentication.

    Features:
        - Selective CRUD for added models
        - Event logging and audit trails
        - Health monitoring and dashboard
        - IP restriction and HTTPS enforcement
        - Session management
        - Token-based authentication

    Args:
        session: Async SQLAlchemy session for database operations
        SECRET_KEY: Secret key for session management and cookie signing. Generate securely using:
            **Python one-liner (recommended)**
            python -c "import secrets; print(secrets.token_urlsafe(32))"

            **OpenSSL**
            openssl rand -base64 32

            **/dev/urandom (Unix/Linux)**
            head -c 32 /dev/urandom | base64

            **The secret key must be:**
            - At least 32 bytes (256 bits) long
            - Stored securely (e.g., in environment variables)
            - Different for each environment
            - Not committed to version control

        mount_path: URL path where admin interface is mounted, default "/admin"
        theme: UI theme ('dark-theme' or 'light-theme'), default "dark-theme"
        admin_db_url: SQLite/PostgreSQL database URL for admin data
        admin_db_path: File path for SQLite admin database
        db_config: Optional pre-configured DatabaseConfig
        setup_on_initialization: Whether to run setup on init, default True
        initial_admin: Initial admin user credentials
        allowed_ips: List of allowed IP addresses
        allowed_networks: List of allowed IP networks in CIDR notation
        max_sessions_per_user: Limit concurrent sessions, default 5
        session_timeout_minutes: Session inactivity timeout, default 30 minutes
        cleanup_interval_minutes: How often to remove expired sessions, default 15 minutes
        secure_cookies: Enable secure cookie flag, default True
        enforce_https: Redirect HTTP to HTTPS, default False
        https_port: HTTPS port for redirects, default 443
        track_events: Enable event logging, default False

    Raises:
        ValueError: If mount_path is invalid or theme is unsupported
        ImportError: If required dependencies are missing
        RuntimeError: If database connection fails

    Notes:
        - Database Configuration uses SQLite by default in ./crudadmin_data/admin.db
        - Database is auto-initialized unless setup_on_initialization=False

    Example:
        Basic setup with SQLite:
        ```python
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import declarative_base
        from sqlalchemy import Column, Integer, String
        import os

        # Generate secret key
        SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY") or os.urandom(32).hex()

        # Define models
        Base = declarative_base()

        class User(Base):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)
            username = Column(String, unique=True)
            email = Column(String)
            role = Column(String)

        # Setup database
        engine = create_async_engine("sqlite+aiosqlite:///app.db")
        session = AsyncSession(engine)

        # Create admin interface
        admin = CRUDAdmin(
            session=session,
            SECRET_KEY=SECRET_KEY,
            initial_admin={
                "username": "admin",
                "password": "secure_pass123"
            }
        )
        ```

        Production setup with security features:
        ```python
        admin = CRUDAdmin(
            session=session,
            SECRET_KEY=SECRET_KEY,
            # Security features
            allowed_ips=["10.0.0.1", "10.0.0.2"],
            allowed_networks=["192.168.1.0/24"],
            secure_cookies=True,
            enforce_https=True,
            # Custom PostgreSQL admin database
            admin_db_url="postgresql+asyncpg://user:pass@localhost/admin",
            # Session configuration
            max_sessions_per_user=3,
            session_timeout_minutes=15,
            # Enable audit logging
            track_events=True
        )
        ```

        Session management configuration:
        ```python
        admin = CRUDAdmin(
            session=session,
            SECRET_KEY=SECRET_KEY,
            # Session management settings
            max_sessions_per_user=5,
            session_timeout_minutes=30,
            cleanup_interval_minutes=15,
            # Secure cookie settings
            secure_cookies=True,
            # Initial admin user
            initial_admin={
                "username": "admin",
                "password": "very_secure_password_123",
                "is_superuser": True
            }
        )
        ```

        Setup with multiple models and custom schemas:
        ```python
        from pydantic import BaseModel, EmailStr
        from decimal import Decimal
        from datetime import datetime

        # Models
        class Product(Base):
            __tablename__ = "products"
            id = Column(Integer, primary_key=True)
            name = Column(String)
            price = Column(Decimal)
            created_at = Column(DateTime)

        class Order(Base):
            __tablename__ = "orders"
            id = Column(Integer, primary_key=True)
            user_id = Column(Integer, ForeignKey("users.id"))
            total = Column(Decimal)
            status = Column(String)
            order_date = Column(DateTime)

        # Schemas
        class ProductCreate(BaseModel):
            name: str
            price: Decimal
            created_at: datetime = Field(default_factory=datetime.utcnow)

        class ProductUpdate(BaseModel):
            name: Optional[str] = None
            price: Optional[Decimal] = None

        class OrderCreate(BaseModel):
            user_id: int
            total: Decimal
            status: str = "pending"
            order_date: datetime = Field(default_factory=datetime.utcnow)

        class OrderUpdate(BaseModel):
            status: Optional[str] = None
            total: Optional[Decimal] = None

        # Add views
        admin.add_view(
            model=Product,
            create_schema=ProductCreate,
            update_schema=ProductUpdate,
            update_internal_schema=None,
            delete_schema=None,
            allowed_actions={"view", "create", "update"}  # No deletion
        )

        admin.add_view(
            model=Order,
            create_schema=OrderCreate,
            update_schema=OrderUpdate,
            update_internal_schema=None,
            delete_schema=None,
            allowed_actions={"view", "update"}  # View and update only
        )
        ```

        Event tracking and audit logs:
        ```python
        admin = CRUDAdmin(
            session=session,
            SECRET_KEY=SECRET_KEY,
            track_events=True,  # Enable event tracking
            # Custom admin database for logs
            admin_db_url="postgresql+asyncpg://user:pass@localhost/admin_logs",
        )

        # Events tracked automatically:
        # - User logins/logouts
        # - Model creates/updates/deletes
        # - Failed authentication attempts
        # - System health status
        ```
    """

    def __init__(
        self,
        session: AsyncSession,
        SECRET_KEY: str,
        mount_path: Optional[str] = "/admin",
        theme: Optional[str] = "dark-theme",
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        db_config: Optional[DatabaseConfig] = None,
        setup_on_initialization: bool = True,
        initial_admin: Optional[Union[dict, BaseModel]] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
        max_sessions_per_user: int = 5,
        session_timeout_minutes: int = 30,
        cleanup_interval_minutes: int = 15,
        secure_cookies: bool = True,
        enforce_https: bool = False,
        https_port: int = 443,
        track_events: bool = False,
    ) -> None:
        self.mount_path = mount_path.strip("/") if mount_path else "admin"
        self.theme = theme or "dark-theme"
        self.track_events = track_events

        self.templates_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "templates"
        )

        self.static_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "static"
        )

        self.app = FastAPI()
        self.app.mount(
            "/static", StaticFiles(directory=self.static_directory), name="admin_static"
        )

        self.app.add_middleware(AdminAuthMiddleware, admin_instance=self)

        from ..event import create_admin_audit_log, create_admin_event_log

        event_log_model: Optional[Type[DeclarativeBase]] = None
        audit_log_model: Optional[Type[DeclarativeBase]] = None

        if self.track_events:
            event_log_model = cast(
                Type[DeclarativeBase], create_admin_event_log(AdminBase)
            )
            audit_log_model = cast(
                Type[DeclarativeBase], create_admin_audit_log(AdminBase)
            )

        self.db_config = db_config or DatabaseConfig(
            base=AdminBase,
            session=session,
            admin_db_url=admin_db_url,
            admin_db_path=admin_db_path,
            admin_session=create_admin_session_model(AdminBase),
            admin_event_log=event_log_model,
            admin_audit_log=audit_log_model,
        )

        if self.track_events:
            from ..event import init_event_system

            self.event_service, self.event_integration = init_event_system(
                self.db_config
            )
        else:
            self.event_service = None
            self.event_integration = None

        self.SECRET_KEY = SECRET_KEY

        self.admin_user_service = AdminUserService(db_config=self.db_config)
        self.initial_admin = initial_admin
        self.models: Dict[str, ModelConfig] = {}
        self.router = APIRouter(tags=["admin"])
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/{self.mount_path}/login")
        self.secure_cookies = secure_cookies

        self.session_manager = SessionManager(
            self.db_config,
            max_sessions_per_user=max_sessions_per_user,
            session_timeout_minutes=session_timeout_minutes,
            cleanup_interval_minutes=cleanup_interval_minutes,
        )

        self.admin_authentication = AdminAuthentication(
            database_config=self.db_config,
            user_service=self.admin_user_service,
            session_manager=self.session_manager,
            oauth2_scheme=self.oauth2_scheme,
            event_integration=self.event_integration,
        )

        self.templates = Jinja2Templates(directory=self.templates_directory)

        if setup_on_initialization:
            self.setup()

        if allowed_ips or allowed_networks:
            self.app.add_middleware(
                IPRestrictionMiddleware,
                allowed_ips=allowed_ips,
                allowed_networks=allowed_networks,
            )

        if enforce_https:
            from .middleware.https import HTTPSRedirectMiddleware

            self.app.add_middleware(HTTPSRedirectMiddleware, https_port=https_port)

        self.app.include_router(self.router)

    async def initialize(self) -> None:
        """
        Initialize admin database tables and create initial admin user.

        Creates required tables:
        - AdminUser for user management
        - AdminSession for session tracking
        - AdminEventLog and AdminAuditLog if event tracking enabled

        Also creates initial admin user if credentials were provided.

        Raises:
            AssertionError: If event log models are misconfigured
            ValueError: If database initialization fails

        Notes:
            - This is called automatically if setup_on_initialization=True
            - Tables are created with 'checkfirst' to avoid conflicts
            - Initial admin is only created if no admin exists

        Example:
            Manual initialization:
            ```python
            admin = CRUDAdmin(
                session=async_session,
                SECRET_KEY="key",
                setup_on_initialization=False
            )
            await admin.initialize()
            ```
        """
        if hasattr(self.db_config, "AdminEventLog") and self.db_config.AdminEventLog:
            assert hasattr(self.db_config.AdminEventLog, "metadata"), (
                "AdminEventLog must have metadata"
            )

        if hasattr(self.db_config, "AdminAuditLog") and self.db_config.AdminAuditLog:
            assert hasattr(self.db_config.AdminAuditLog, "metadata"), (
                "AdminAuditLog must have metadata"
            )

        async with self.db_config.admin_engine.begin() as conn:
            await conn.run_sync(self.db_config.AdminUser.metadata.create_all)
            await conn.run_sync(self.db_config.AdminSession.metadata.create_all)

            if (
                self.track_events
                and self.db_config.AdminEventLog
                and self.db_config.AdminAuditLog
            ):
                await conn.run_sync(self.db_config.AdminEventLog.metadata.create_all)
                await conn.run_sync(self.db_config.AdminAuditLog.metadata.create_all)

        if self.initial_admin:
            await self._create_initial_admin(self.initial_admin)

    def setup_event_routes(self) -> None:
        """
        Set up routes for event log management.

        Creates endpoints:
        - GET /management/events - Event log page
        - GET /management/events/content - Event log data

        Notes:
            - Only created if track_events=True
            - Routes require authentication
        """
        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                self.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
                response_model=None,
            )
            self.router.add_api_route(
                "/management/events/content",
                self.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
                response_model=None,
            )

    def event_log_page(
        self,
    ) -> Callable[[Request, AsyncSession], Awaitable[RouteResponse]]:
        """
        Create endpoint for event log main page.

        Returns:
            FastAPI route handler that renders event log template
            with filtering options
        """

        admin_db_db_dependency = cast(
            Callable[..., AsyncSession], self.db_config.get_admin_db
        )
        app_db_dependency = cast(Callable[..., AsyncSession], self.db_config.session)

        async def event_log_page_inner(
            request: Request,
            admin_db: AsyncSession = Depends(admin_db_db_dependency),
            app_db: AsyncSession = Depends(app_db_dependency),
        ) -> RouteResponse:
            from ..event import EventStatus, EventType

            users = await self.db_config.crud_users.get_multi(db=app_db)

            context = await self.admin_site.get_base_context(
                admin_db=admin_db, app_db=app_db
            )
            context.update(
                {
                    "request": request,
                    "include_sidebar_and_header": True,
                    "event_types": [e.value for e in EventType],
                    "statuses": [s.value for s in EventStatus],
                    "users": users["data"],
                    "mount_path": self.mount_path,
                }
            )

            return self.templates.TemplateResponse(
                "admin/management/events.html", context
            )

        return event_log_page_inner

    def event_log_content(self) -> EndpointFunction:
        """
        Create endpoint for event log data with filtering and pagination.

        Returns:
            FastAPI route handler that provides filtered event data
            with user and audit details

        Notes:
            - Supports filtering by:
            - Event type
            - Status
            - Username
            - Date range
            - Returns enriched events with:
            - Username
            - Resource details
            - Audit trail data
            - Includes pagination metadata

        Examples:
            Filter events:
            GET /management/events/content?event_type=create&status=success

            Filter by date:
            GET /management/events/content?start_date=2024-01-01&end_date=2024-01-31
        """

        admin_db_db_dependency = cast(
            Callable[..., AsyncSession], self.db_config.get_admin_db
        )

        async def event_log_content_inner(
            request: Request,
            admin_db: AsyncSession = Depends(admin_db_db_dependency),
            page: int = 1,
            limit: int = 10,
        ) -> RouteResponse:
            try:
                if not self.db_config.AdminEventLog:
                    raise ValueError("AdminEventLog is not configured")

                crud_events: FastCRUD = FastCRUD(self.db_config.AdminEventLog)

                event_type = cast(Optional[str], request.query_params.get("event_type"))
                status = cast(Optional[str], request.query_params.get("status"))
                username = cast(Optional[str], request.query_params.get("username"))
                start_date = cast(Optional[str], request.query_params.get("start_date"))
                end_date = cast(Optional[str], request.query_params.get("end_date"))

                filter_criteria: Dict[str, Any] = {}
                if event_type:
                    filter_criteria["event_type"] = event_type
                if status:
                    filter_criteria["status"] = status

                if username:
                    user = await self.db_config.crud_users.get(
                        db=admin_db, username=username
                    )
                    if user and isinstance(user, dict):
                        filter_criteria["user_id"] = user.get("id")

                if start_date:
                    start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                        tzinfo=UTC
                    )
                    filter_criteria["timestamp__gte"] = start

                if end_date:
                    end = (
                        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    ).replace(tzinfo=UTC)
                    filter_criteria["timestamp__lt"] = end

                events = await crud_events.get_multi(
                    db=admin_db,
                    offset=(page - 1) * limit,
                    limit=limit,
                    sort_columns=["timestamp"],
                    sort_orders=["desc"],
                    **filter_criteria,
                )

                enriched_events = []
                if isinstance(events["data"], list):
                    for event in events["data"]:
                        if isinstance(event, dict):
                            event_data = dict(event)
                            user = await self.db_config.crud_users.get(
                                db=admin_db, id=event.get("user_id")
                            )
                            if isinstance(user, dict):
                                event_data["username"] = user.get("username", "Unknown")

                            if event.get("resource_type") and event.get("resource_id"):
                                if not self.db_config.AdminAuditLog:
                                    raise ValueError("AdminAuditLog is not configured")

                                crud_audits: FastCRUD = FastCRUD(
                                    self.db_config.AdminAuditLog
                                )
                                audit = await crud_audits.get(
                                    db=admin_db, event_id=event.get("id")
                                )
                                if audit and isinstance(audit, dict):
                                    event_data["details"] = {
                                        "resource_details": {
                                            "model": event.get("resource_type"),
                                            "id": event.get("resource_id"),
                                            "changes": audit.get("new_state"),
                                        }
                                    }

                            enriched_events.append(event_data)

                total_items = events.get("total_count", 0)
                assert isinstance(total_items, int), (
                    f"'total_count' should be int, got {type(total_items)}"
                )

                total_pages = max(1, (total_items + limit - 1) // limit)

                return self.templates.TemplateResponse(
                    "admin/management/events_content.html",
                    {
                        "request": request,
                        "events": enriched_events,
                        "page": page,
                        "total_pages": total_pages,
                        "mount_path": self.mount_path,
                        "start_date": start_date,
                        "end_date": end_date,
                        "selected_type": event_type,
                        "selected_status": status,
                        "selected_user": username,
                    },
                )

            except Exception as e:
                logger.error(f"Error retrieving events: {str(e)}")
                return self.templates.TemplateResponse(
                    "admin/management/events_content.html",
                    {
                        "request": request,
                        "events": [],
                        "page": 1,
                        "total_pages": 1,
                        "mount_path": self.mount_path,
                    },
                )

        return event_log_content_inner

    def setup(
        self,
    ) -> None:
        """
        Set up admin interface routes and views.

        Configures:
        - Authentication routes and middleware
        - Model CRUD views
        - Management views (health check, events)
        - Static files

        Notes:
            - Called automatically if setup_on_initialization=True
            - Can be called manually after initialization
            - Respects allowed_actions configuration
        """
        self.admin_site = AdminSite(
            database_config=self.db_config,
            templates_directory=self.templates_directory,
            models=self.models,
            admin_authentication=self.admin_authentication,
            mount_path=self.mount_path,
            theme=self.theme,
            secure_cookies=self.secure_cookies,
            event_integration=self.event_integration if self.track_events else None,
        )

        self.admin_site.setup_routes()

        for model_name, data in self.admin_authentication.auth_models.items():
            allowed_actions = {
                "AdminUser": {"view", "create", "update"},
                "AdminSession": {"view", "delete"},
            }.get(model_name, {"view"})

            model = cast(Type[DeclarativeBase], data["model"])
            create_schema = cast(Type[BaseModel], data["create_schema"])
            update_schema = cast(Type[BaseModel], data["update_schema"])
            update_internal_schema = cast(
                Optional[Type[BaseModel]], data["update_internal_schema"]
            )
            delete_schema = cast(Optional[Type[BaseModel]], data["delete_schema"])

            self.add_view(
                model=model,
                create_schema=create_schema,
                update_schema=update_schema,
                update_internal_schema=update_internal_schema,
                delete_schema=delete_schema,
                include_in_models=False,
                allowed_actions=allowed_actions,
            )

        get_user_dependency = cast(
            Callable[..., AsyncSession], self.admin_authentication.get_current_user
        )

        self.router.add_api_route(
            "/management/health",
            self.health_check_page(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(get_user_dependency)],
            response_model=None,
        )

        self.router.add_api_route(
            "/management/health/content",
            self.health_check_content(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(get_user_dependency)],
            response_model=None,
        )

        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                self.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(get_user_dependency)],
                response_model=None,
            )
            self.router.add_api_route(
                "/management/events/content",
                self.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(get_user_dependency)],
                response_model=None,
            )

        self.router.include_router(router=self.admin_site.router)

    def add_view(
        self,
        model: Type[DeclarativeBase],
        create_schema: Type[BaseModel],
        update_schema: Type[BaseModel],
        update_internal_schema: Optional[Type[BaseModel]],
        delete_schema: Optional[Type[BaseModel]],
        include_in_models: bool = True,
        allowed_actions: Optional[set[str]] = None,
    ) -> None:
        """
        Add CRUD view for a database model.

        Creates a web interface for managing model instances with forms generated
        from Pydantic schemas.

        Args:
            model: SQLAlchemy model class to manage
            create_schema: Pydantic schema for create operations
            update_schema: Pydantic schema for update operations
            update_internal_schema: Internal schema for special update cases
            delete_schema: Schema for delete operations
            include_in_models: Show in models list in admin UI
            allowed_actions: **Set of allowed operations:**
                - **"view"**: Allow viewing records
                - **"create"**: Allow creating new records
                - **"update"**: Allow updating existing records
                - **"delete"**: Allow deleting records
                Defaults to all actions if None

        Raises:
            ValueError: If schemas don't match model structure
            TypeError: If model is not a SQLAlchemy model

        Notes:
            - Forms are auto-generated with field types determined from Pydantic schemas
            - Actions controlled by allowed_actions parameter

            URL Routes:
            - List view: /admin/<model_name>/
            - Create: /admin/<model_name>/create
            - Update: /admin/<model_name>/update/<id>
            - Delete: /admin/<model_name>/delete/<id>

        Example:
            Basic user management:
            ```python
            from pydantic import BaseModel, EmailStr, Field
            from typing import Optional
            from datetime import datetime

            class UserCreate(BaseModel):
                username: str = Field(..., min_length=3, max_length=50)
                email: EmailStr
                role: str = Field(default="user")
                active: bool = Field(default=True)
                join_date: datetime = Field(default_factory=datetime.utcnow)

            class UserUpdate(BaseModel):
                email: Optional[EmailStr] = None
                role: Optional[str] = None
                active: Optional[bool] = None

            admin.add_view(
                model=User,
                create_schema=UserCreate,
                update_schema=UserUpdate,
                update_internal_schema=None,
                delete_schema=None,
                allowed_actions={"view", "create", "update"}  # No deletion
            )
            ```

            Product catalog with custom validation:
            ```python
            from decimal import Decimal
            from pydantic import Field, validator

            class ProductCreate(BaseModel):
                name: str = Field(..., min_length=2, max_length=100)
                price: Decimal = Field(..., ge=0)
                description: Optional[str] = Field(None, max_length=500)
                category: str
                in_stock: bool = True

                @validator("price")
                def validate_price(cls, v):
                    if v > 1000000:
                        raise ValueError("Price cannot exceed 1,000,000")
                    return v

            class ProductUpdate(BaseModel):
                name: Optional[str] = Field(None, min_length=2, max_length=100)
                price: Optional[Decimal] = Field(None, ge=0)
                description: Optional[str] = None
                in_stock: Optional[bool] = None

            admin.add_view(
                model=Product,
                create_schema=ProductCreate,
                update_schema=ProductUpdate,
                update_internal_schema=None,
                delete_schema=None,
                allowed_actions={"view", "create", "update"}
            )
            ```

            Order management with enum and relationships:
            ```python
            from enum import Enum
            from typing import List

            class OrderStatus(str, Enum):
                pending = "pending"
                paid = "paid"
                shipped = "shipped"
                delivered = "delivered"
                cancelled = "cancelled"

            class OrderCreate(BaseModel):
                user_id: int = Field(..., gt=0)
                items: List[int] = Field(..., min_items=1)
                shipping_address: str
                status: OrderStatus = Field(default=OrderStatus.pending)
                notes: Optional[str] = None

                class Config:
                    json_schema_extra = {
                        "example": {
                            "user_id": 1,
                            "items": [1, 2, 3],
                            "shipping_address": "123 Main St",
                            "status": "pending"
                        }
                    }

            class OrderUpdate(BaseModel):
                status: Optional[OrderStatus] = None
                notes: Optional[str] = None

            # Custom delete schema with soft delete
            class OrderDelete(BaseModel):
                archive: bool = Field(default=False, description="Archive instead of delete")
                reason: Optional[str] = Field(None, max_length=200)

            admin.add_view(
                model=Order,
                create_schema=OrderCreate,
                update_schema=OrderUpdate,
                update_internal_schema=None,
                delete_schema=OrderDelete,
                allowed_actions={"view", "create", "update", "delete"}
            )
            ```

            Read-only audit log:
            ```python
            class AuditLogSchema(BaseModel):
                id: int
                timestamp: datetime
                user_id: int
                action: str
                details: dict

                class Config:
                    orm_mode = True

            admin.add_view(
                model=AuditLog,
                create_schema=AuditLogSchema,
                update_schema=AuditLogSchema,
                update_internal_schema=None,
                delete_schema=None,
                allowed_actions={"view"},  # Read-only
                include_in_models=False  # Hide from nav
            )
            ```
        """
        model_key = model.__name__
        if include_in_models:
            self.models[model_key] = {
                "model": model,
                "create_schema": create_schema,
                "update_schema": update_schema,
                "update_internal_schema": update_internal_schema,
                "delete_schema": delete_schema,
                "crud": FastCRUD(model),
            }

        allowed_actions = allowed_actions or {"view", "create", "update", "delete"}

        admin_view = ModelView(
            database_config=self.db_config,
            templates=self.templates,
            model=model,
            create_schema=create_schema,
            update_schema=update_schema,
            update_internal_schema=update_internal_schema,
            delete_schema=delete_schema,
            admin_site=self.admin_site,
            allowed_actions=allowed_actions,
            event_integration=self.event_integration if self.track_events else None,
        )

        if self.track_events and self.event_integration:
            admin_view.event_integration = self.event_integration

        current_user_dep = cast(
            Callable[..., Any], self.admin_site.admin_authentication.get_current_user
        )
        self.app.include_router(
            admin_view.router,
            prefix=f"/{model_key}",
            dependencies=[Depends(current_user_dep)],
            include_in_schema=False,
        )

    def health_check_page(
        self,
    ) -> Callable[[Request, AsyncSession], Awaitable[RouteResponse]]:
        """
        Create endpoint for system health check page.

        Returns:
            FastAPI route handler that renders health check template
        """

        admin_db_db_dependency = cast(
            Callable[..., AsyncSession], self.db_config.get_admin_db
        )
        app_db_dependency = cast(Callable[..., AsyncSession], self.db_config.session)

        async def health_check_page_inner(
            request: Request,
            admin_db: AsyncSession = Depends(admin_db_db_dependency),
            app_db: AsyncSession = Depends(app_db_dependency),
        ) -> RouteResponse:
            context = await self.admin_site.get_base_context(
                admin_db=admin_db, app_db=app_db
            )
            context.update({"request": request, "include_sidebar_and_header": True})

            return self.templates.TemplateResponse(
                "admin/management/health.html", context
            )

        return health_check_page_inner

    def health_check_content(
        self,
    ) -> Callable[[Request, AsyncSession], Awaitable[RouteResponse]]:
        """
        Create endpoint for health check data.

        Returns:
            FastAPI route handler that checks:
            - Database connectivity
            - Session management
            - Token service
        """

        db_dependency = cast(Callable[..., AsyncSession], self.db_config.session)

        async def health_check_content_inner(
            request: Request, db: AsyncSession = Depends(db_dependency)
        ) -> RouteResponse:
            health_checks = {}

            start_time = time.time()
            try:
                await db.execute(text("SELECT 1"))
                latency = (time.time() - start_time) * 1000
                health_checks["database"] = {
                    "status": "healthy",
                    "message": "Connected successfully",
                    "latency": latency,
                }
            except Exception as e:
                health_checks["database"] = {"status": "unhealthy", "message": str(e)}

            try:
                await self.session_manager.cleanup_expired_sessions(db)
                health_checks["session_management"] = {
                    "status": "healthy",
                    "message": "Session cleanup working",
                }
            except Exception as e:
                health_checks["session_management"] = {
                    "status": "unhealthy",
                    "message": str(e),
                }

            context = {
                "request": request,
                "health_checks": health_checks,
                "last_checked": datetime.now(UTC),
            }

            return self.templates.TemplateResponse(
                "admin/management/health_content.html", context
            )

        return health_check_content_inner

    async def _create_initial_admin(self, admin_data: Union[dict, BaseModel]) -> None:
        """
        Create initial admin user if none exists.

        Args:
            admin_data: Admin credentials as dict or Pydantic model

        Raises:
            ValueError: If admin_data has invalid format
            Exception: If database operations fail

        Notes:
            - Only creates admin if no users exist
            - Handles both dict and Pydantic model input
            - Password is hashed before storage
        """
        async for admin_session in self.db_config.get_admin_db():
            try:
                admins_count = await self.db_config.crud_users.count(admin_session)

                if admins_count < 1:
                    if isinstance(admin_data, dict):
                        create_data = AdminUserCreate(**admin_data)
                    elif isinstance(admin_data, BaseModel):
                        if isinstance(admin_data, AdminUserCreate):
                            create_data = admin_data
                        else:
                            create_data = AdminUserCreate(**admin_data.dict())
                    else:
                        msg = (
                            "Initial admin data must be either a dict or Pydantic model"
                        )
                        logger.error(msg)
                        raise ValueError(msg)

                    hashed_password = self.admin_user_service.get_password_hash(
                        create_data.password
                    )
                    internal_data = AdminUserCreateInternal(
                        username=create_data.username,
                        hashed_password=hashed_password,
                    )

                    await self.db_config.crud_users.create(
                        admin_session, object=cast(Any, internal_data)
                    )
                    await admin_session.commit()
                    logger.info(
                        "Created initial admin user - username: %s",
                        create_data.username,
                    )

            except Exception as e:
                logger.error(
                    "Error creating initial admin user: %s", str(e), exc_info=True
                )
                raise
