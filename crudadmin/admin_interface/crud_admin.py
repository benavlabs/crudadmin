import os
from collections.abc import Callable
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    NamedTuple,
    Optional,
    Type,
    TypedDict,
    Union,
    cast,
)

from crudauth import AuthHooks
from crudauth.ratelimit import LockoutConfig
from fastapi import APIRouter, Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ..admin_interface.auth import AdminAuthentication
from ..admin_interface.middleware.auth import AdminAuthMiddleware
from ..admin_interface.middleware.ip_restriction import IPRestrictionMiddleware
from ..config import (
    ACCESS_ARGUMENTS,
    SESSION_ARGUMENTS,
    AccessConfig,
    SessionConfig,
    config_from_arguments,
)
from ..core.db import DatabaseConfig, new_admin_base
from ..event.recorder import AdminEvents
from ..session.configs import MemcachedConfig, RedisConfig
from .admin_accounts import create_initial_admin
from .admin_site import AdminSite
from .auth_events import auth_event_hooks
from .exception_handlers import add_auth_exception_handlers
from .management import ManagementPages
from .model_view import ModelView
from .paths import AdminPaths
from .session_backends import build_redis_client, resolve_session_backend


class ProtectedRouter(NamedTuple):
    """A router mounted behind authentication, and whether it needs a superuser."""

    prefix: str
    router: APIRouter
    superuser: bool


class ModelConfig(TypedDict):
    model: Type[DeclarativeBase]
    create_schema: Type[BaseModel]
    update_schema: Type[BaseModel]
    update_internal_schema: Optional[Type[BaseModel]]
    delete_schema: Optional[Type[BaseModel]]
    crud: FastCRUD
    display_field: Optional[str]


class CRUDAdmin:
    """
    A FastAPI admin interface for your SQLAlchemy models.

    It mounts as a sub-application, keeps its admins, sessions and event log in
    an admin database of its own, and protects every page with a login.

    Args:
        session: Your app's async session dependency; the admin reads and writes
            your models through it.
        SECRET_KEY: Keys the stored session ids and CSRF tokens. Use at least 32
            random bytes, kept out of version control, for example from
            ``python -c "import secrets; print(secrets.token_urlsafe(32))"``.
            Changing it signs every admin out.
        mount_path: Where the admin is mounted, ``"/admin"`` by default; ``"/"``
            for the root.
        theme: ``"dark-theme"`` or ``"light-theme"``.
        admin_db_url: The admin database's URL. Defaults to SQLite in
            ``./crudadmin_data/admin.db``.
        admin_db_path: A path for a SQLite admin database, instead of a URL.
        db_config: A ``DatabaseConfig`` to use instead of the two above.
        setup_on_initialization: Mount the routes now; with False, call
            ``setup()`` yourself.
        initial_admin: Credentials of a superuser created by ``initialize()`` when
            no admin exists yet.
        track_events: Record logins, logouts and every create, update and delete
            in the event log.
        sessions: How sessions are kept: a [SessionConfig][crudadmin.config.SessionConfig].
        access: Who may reach the admin: an [AccessConfig][crudadmin.config.AccessConfig].
        allowed_ips: Deprecated; use ``access=AccessConfig(allowed_ips=...)``.
        allowed_networks: Deprecated; use ``access=AccessConfig(allowed_networks=...)``.
        max_sessions_per_user: Deprecated; use ``sessions=SessionConfig(max_per_admin=...)``.
        session_timeout_minutes: Deprecated; use ``sessions=SessionConfig(timeout_minutes=...)``.
        cleanup_interval_minutes: Deprecated; use
            ``sessions=SessionConfig(cleanup_interval_minutes=...)``.
        secure_cookies: Deprecated; use ``sessions=SessionConfig(secure_cookies=...)``.
        enforce_https: Deprecated; use ``access=AccessConfig(enforce_https=...)``.
        https_port: Deprecated; use ``access=AccessConfig(https_port=...)``.
        track_sessions_in_db: Deprecated; use ``sessions=SessionConfig(backend="database")``.
        session_backend: Deprecated; use ``sessions=SessionConfig(backend=...)``.
        redis_config: Deprecated; use ``sessions=SessionConfig(redis=...)``.
        memcached_config: No longer supported; passing it raises.
        trusted_proxy_hops: Deprecated; use ``access=AccessConfig(trusted_proxy_hops=...)``.
        lockout: Deprecated; use ``access=AccessConfig(lockout=...)``.

    Raises:
        ValueError: If ``SECRET_KEY`` is empty, the session backend is unknown or
            Memcached, or a deprecated argument is passed together with the
            config object that replaces it.

    Example:
        ```python
        admin = CRUDAdmin(
            session=get_session,
            SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
            initial_admin={"username": "admin", "password": os.environ["ADMIN_PASSWORD"]},
        )
        admin.add_view(model=Product, create_schema=ProductCreate, update_schema=ProductUpdate)
        app.mount("/admin", admin.app)
        ```

        In production, with sessions shared between workers:
        ```python
        admin = CRUDAdmin(
            session=get_session,
            SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
            admin_db_url="postgresql+asyncpg://user:pass@db/admin",
            track_events=True,
            sessions=SessionConfig(
                backend="redis",
                redis=RedisConfig(url=os.environ["REDIS_URL"]),
                timeout_minutes=15,
            ),
            access=AccessConfig(
                allowed_networks=["10.0.0.0/8"],
                enforce_https=True,
                trusted_proxy_hops=1,
            ),
        )
        ```

        Call ``await admin.initialize()`` when your app starts and
        ``await admin.shutdown()`` when it stops, from its lifespan.
    """

    def __init__(
        self,
        session: Callable[[], AsyncGenerator[AsyncSession, None]],
        SECRET_KEY: str,
        mount_path: Optional[str] = "/admin",
        theme: Optional[str] = "dark-theme",
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        db_config: Optional[DatabaseConfig] = None,
        setup_on_initialization: bool = True,
        initial_admin: Optional[Union[dict, BaseModel]] = None,
        track_events: bool = False,
        sessions: Optional[SessionConfig] = None,
        access: Optional[AccessConfig] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
        max_sessions_per_user: Optional[int] = None,
        session_timeout_minutes: Optional[int] = None,
        cleanup_interval_minutes: Optional[int] = None,
        secure_cookies: Optional[bool] = None,
        enforce_https: Optional[bool] = None,
        https_port: Optional[int] = None,
        track_sessions_in_db: bool = False,
        session_backend: Optional[str] = None,
        redis_config: Optional[Union[RedisConfig, Dict[str, Any]]] = None,
        memcached_config: Optional[Union[MemcachedConfig, Dict[str, Any]]] = None,
        trusted_proxy_hops: Optional[int] = None,
        lockout: Optional[LockoutConfig] = None,
    ) -> None:
        if not SECRET_KEY:
            raise ValueError("SECRET_KEY is required")
        if mount_path == "/":
            self.mount_path = ""
        elif mount_path:
            self.mount_path = mount_path.strip("/")
        else:
            self.mount_path = "admin"
        self.paths = AdminPaths.for_mount_segment(self.mount_path)
        self.theme = theme or "dark-theme"
        self.track_events = track_events
        self.sessions = config_from_arguments(
            SessionConfig,
            "sessions",
            sessions,
            {
                "session_backend": session_backend,
                "redis_config": redis_config,
                "session_timeout_minutes": session_timeout_minutes,
                "max_sessions_per_user": max_sessions_per_user,
                "cleanup_interval_minutes": cleanup_interval_minutes,
                "secure_cookies": secure_cookies,
            },
            SESSION_ARGUMENTS,
        )
        self.access = config_from_arguments(
            AccessConfig,
            "access",
            access,
            {
                "allowed_ips": allowed_ips,
                "allowed_networks": allowed_networks,
                "enforce_https": enforce_https,
                "https_port": https_port,
                "trusted_proxy_hops": trusted_proxy_hops,
                "lockout": lockout,
            },
            ACCESS_ARGUMENTS,
        )
        self._session_backend = resolve_session_backend(
            self.sessions.backend, track_sessions_in_db, memcached_config
        )

        self.templates_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "templates"
        )

        self.static_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "static"
        )

        self.app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
        self.app.mount(
            "/static", StaticFiles(directory=self.static_directory), name="admin_static"
        )

        self.app.add_middleware(AdminAuthMiddleware, admin_instance=self)

        from ..event import create_admin_audit_log, create_admin_event_log

        admin_base = new_admin_base()
        event_log_model: Optional[Type[DeclarativeBase]] = None
        audit_log_model: Optional[Type[DeclarativeBase]] = None

        if self.track_events and db_config is None:
            event_log_model = create_admin_event_log(admin_base)
            audit_log_model = create_admin_audit_log(admin_base)

        self.db_config = db_config or DatabaseConfig(
            base=admin_base,
            session=session,
            admin_db_url=admin_db_url,
            admin_db_path=admin_db_path,
            admin_event_log=event_log_model,
            admin_audit_log=audit_log_model,
        )

        if self.track_events:
            self._add_missing_event_models()

        if self.track_events:
            from ..event import init_event_system

            self.event_service, self.event_integration = init_event_system(
                self.db_config
            )
        else:
            self.event_service = None
            self.event_integration = None
        self.events = AdminEvents(self.event_integration)

        self.SECRET_KEY = SECRET_KEY
        self.initial_admin = initial_admin
        self.models: Dict[str, ModelConfig] = {}
        self.router = APIRouter(tags=["admin"])
        self.protected_routers: list[ProtectedRouter] = []
        self._is_set_up = False
        self.secure_cookies = self.sessions.secure_cookies

        self._redis_client = (
            build_redis_client(self.sessions.redis)
            if self._session_backend == "redis"
            else None
        )

        self.admin_authentication = AdminAuthentication(
            database_config=self.db_config,
            secret_key=SECRET_KEY,
            mount_prefix=self.paths.prefix,
            cookie_path=self.paths.cookie_path,
            secure_cookies=self.sessions.secure_cookies,
            session_backend=self._session_backend,
            redis_client=self._redis_client,
            session_timeout_minutes=self.sessions.timeout_minutes,
            max_sessions_per_user=self.sessions.max_per_admin,
            cleanup_interval_minutes=self.sessions.cleanup_interval_minutes,
            trusted_proxy_hops=self.access.trusted_proxy_hops,
            lockout=self.access.lockout,
            hooks=self._auth_hooks(),
        )

        self.templates = Jinja2Templates(directory=self.templates_directory)
        add_auth_exception_handlers(self.app, self.paths)

        if setup_on_initialization:
            self.setup()

        if self.access.allowed_ips or self.access.allowed_networks:
            self.app.add_middleware(
                IPRestrictionMiddleware,
                allowed_ips=self.access.allowed_ips,
                allowed_networks=self.access.allowed_networks,
            )

        if self.access.enforce_https:
            from .middleware.https import HTTPSRedirectMiddleware

            self.app.add_middleware(
                HTTPSRedirectMiddleware, https_port=self.access.https_port
            )

    def _add_missing_event_models(self) -> None:
        """Give a ``db_config`` passed in without event models its own, on its base."""
        from ..event import create_admin_audit_log, create_admin_event_log

        if self.db_config.AdminEventLog is None:
            self.db_config.AdminEventLog = create_admin_event_log(self.db_config.base)
        if self.db_config.AdminAuditLog is None:
            self.db_config.AdminAuditLog = create_admin_audit_log(self.db_config.base)

    @property
    def session_manager(self) -> Any:
        """crudauth's session manager: list, revoke and inspect admin sessions.

        Example:
            ```python
            await admin.session_manager.revoke_all(user_id)
            ```
        """
        return self.admin_authentication.auth.sessions

    def _auth_hooks(self) -> AuthHooks:
        """Hooks that record authentication in the event log, when events are tracked."""
        if not self.track_events or self.event_integration is None:
            return AuthHooks()
        return auth_event_hooks(
            self.event_integration, self.db_config.admin_session_maker
        )

    def get_url_prefix(self) -> str:
        """Get the URL prefix for admin routes, handling root mount path correctly."""
        return self.paths.prefix

    def _mount_protected(
        self, router: APIRouter, prefix: str = "", superuser: bool = False
    ) -> None:
        """Mount a router behind the logged-in-admin dependency (or the superuser one).

        Every admin route except login, logout and static files reaches the app
        through here, so none can be added without authentication.
        """
        authentication = self.admin_authentication
        admin_dependency = (
            authentication.get_current_superuser()
            if superuser
            else authentication.get_current_user()
        )
        self.protected_routers.append(ProtectedRouter(prefix, router, superuser))
        self.app.include_router(
            router,
            prefix=prefix,
            dependencies=[Depends(admin_dependency)],
            include_in_schema=False,
        )

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
                session=get_session,
                SECRET_KEY="key",
                setup_on_initialization=False
            )
            await admin.initialize()
            ```
        """
        await self.db_config.initialize_admin_db()
        await self.admin_authentication.initialize()

        if self.initial_admin:
            await create_initial_admin(self.db_config, self.initial_admin)

    async def shutdown(self) -> None:
        """Close the session stores and the Redis client crudadmin opened.

        Call it from your app's lifespan after ``yield``.
        """
        await self.admin_authentication.shutdown()
        if self._redis_client is not None:
            await self._redis_client.aclose()

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
            - Runs once; later calls return without mounting anything again
            - Respects allowed_actions configuration
        """
        if self._is_set_up:
            return
        self._is_set_up = True

        self.admin_site = AdminSite(
            database_config=self.db_config,
            templates_directory=self.templates_directory,
            models=self.models,
            admin_authentication=self.admin_authentication,
            mount_path=self.mount_path,
            theme=self.theme,
            event_integration=self.event_integration if self.track_events else None,
        )

        self.admin_site.setup_routes()

        for model_name, data in self.admin_authentication.auth_models.items():
            allowed_actions = {
                "AdminUser": {"view", "create", "update"},
            }.get(model_name, {"view"})

            model = cast(Type[DeclarativeBase], data["model"])
            create_schema = cast(Type[BaseModel], data["create_schema"])
            update_schema = cast(Type[BaseModel], data["update_schema"])
            update_internal_schema = cast(
                Optional[Type[BaseModel]], data["update_internal_schema"]
            )
            delete_schema = cast(Optional[Type[BaseModel]], data["delete_schema"])
            select_schema = cast(Optional[Type[BaseModel]], data.get("select_schema"))

            self.add_view(
                model=model,
                create_schema=create_schema,
                update_schema=update_schema,
                update_internal_schema=update_internal_schema,
                delete_schema=delete_schema,
                select_schema=select_schema,
                include_in_models=False,
                allowed_actions=allowed_actions,
            )

        get_superuser_dependency = self.admin_authentication.get_current_superuser()
        management = ManagementPages(
            admin_site=self.admin_site,
            templates=self.templates,
            database_config=self.db_config,
            admin_authentication=self.admin_authentication,
            session_backend=self._session_backend,
        )

        self.router.add_api_route(
            "/management/health",
            management.health_check_page(),
            methods=["GET"],
            include_in_schema=False,
            response_model=None,
        )

        self.router.add_api_route(
            "/management/health/content",
            management.health_check_content(),
            methods=["GET"],
            include_in_schema=False,
            response_model=None,
        )

        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                management.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(get_superuser_dependency)],
                response_model=None,
            )
            self.router.add_api_route(
                "/management/events/content",
                management.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(get_superuser_dependency)],
                response_model=None,
            )

        self._mount_protected(self.admin_site.router)
        self._mount_protected(self.router)
        self.app.include_router(self.admin_site.public_router, include_in_schema=False)

    def add_view(
        self,
        model: Type[DeclarativeBase],
        create_schema: Type[BaseModel],
        update_schema: Type[BaseModel],
        update_internal_schema: Optional[Type[BaseModel]] = None,
        delete_schema: Optional[Type[BaseModel]] = None,
        select_schema: Optional[Type[BaseModel]] = None,
        include_in_models: bool = True,
        allowed_actions: Optional[set[str]] = None,
        password_transformer: Optional[Any] = None,
        display_field: Optional[str] = None,
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
            select_schema: Optional schema for read operations (excludes fields from queries)
            include_in_models: Show in models list in admin UI
            allowed_actions: **Set of allowed operations:**
                - **"view"**: Allow viewing records
                - **"create"**: Allow creating new records
                - **"update"**: Allow updating existing records
                - **"delete"**: Allow deleting records
                Defaults to all actions if None
            password_transformer: PasswordTransformer instance for handling password field transformation
            display_field: Column used as this model's human-readable label when
                it is shown as a related record from another model's view (e.g.
                ``"name"`` so a foreign key renders the name instead of the id).
                Falls back to the primary key when not set.

        Raises:
            ValueError: If schemas don't match model structure
            TypeError: If model is not a SQLAlchemy model

        Notes:
            - Forms are auto-generated with field types determined from Pydantic schemas
            - Actions controlled by allowed_actions parameter
            - Use select_schema to exclude problematic fields (e.g., TSVector) from read operations
            - Use password_transformer for models with password fields that need hashing

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

            Excluding problematic fields (e.g., TSVector):
            ```python
            class DocumentCreate(BaseModel):
                title: str
                content: str
                # TSVector field excluded from this schema

            class DocumentSelect(BaseModel):
                id: int
                title: str
                content: str
                created_at: datetime
                # search_vector (TSVector) field excluded

            admin.add_view(
                model=Document,
                create_schema=DocumentCreate,
                update_schema=DocumentCreate,
                select_schema=DocumentSelect,  # TSVector field excluded from reads
                allowed_actions={"view", "create", "update"}
            )
            ```

            User with password handling:
            ```python
            from crudadmin.admin_interface.model_view import PasswordTransformer
            import bcrypt

            def hash_password(password: str) -> str:
                return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            class UserCreateWithPassword(BaseModel):
                username: str
                email: EmailStr
                password: str  # This will be transformed to hashed_password

            transformer = PasswordTransformer(
                password_field="password",
                hashed_field="hashed_password",
                hash_function=hash_password,
                required_fields=["username", "email"]
            )

            admin.add_view(
                model=User,
                create_schema=UserCreateWithPassword,
                update_schema=UserUpdate,
                update_internal_schema=None,
                delete_schema=None,
                password_transformer=transformer
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
                "display_field": display_field,
            }

        allowed_actions = allowed_actions or {"view", "create", "update", "delete"}

        authentication = self.admin_site.admin_authentication
        is_admin_user = model is self.db_config.AdminUser
        admin_account_change_guards = [
            Depends(authentication.get_recently_confirmed_superuser())
        ]
        write_dependencies = admin_account_change_guards if is_admin_user else []

        admin_view = ModelView(
            database_config=self.db_config,
            templates=self.templates,
            model=model,
            create_schema=create_schema,
            update_schema=update_schema,
            update_internal_schema=update_internal_schema,
            delete_schema=delete_schema,
            select_schema=select_schema,
            admin_site=self.admin_site,
            allowed_actions=allowed_actions,
            event_integration=self.event_integration,
            password_transformer=password_transformer,
            write_dependencies=write_dependencies,
        )

        self._mount_protected(
            admin_view.router, prefix=f"/{model_key}", superuser=is_admin_user
        )
