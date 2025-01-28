import logging
import os
from typing import (
    TypeVar,
    Type,
    Dict,
    Any,
    Union,
    Optional,
    List,
    Callable,
    Awaitable,
    cast,
    TypedDict,
)
from datetime import datetime, timezone, timedelta
import time

from fastapi import APIRouter, FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing_extensions import TypeAlias

from .model_view import ModelView
from .admin_site import AdminSite
from .typing import RouteResponse
from ..admin_interface.auth import AdminAuthentication
from ..admin_interface.middleware.auth import AdminAuthMiddleware
from ..admin_interface.middleware.ip_restriction import IPRestrictionMiddleware
from ..session import create_admin_session_model, SessionManager
from ..admin_token.service import TokenService
from ..admin_user.service import AdminUserService
from ..core.db import DatabaseConfig, AdminBase
from ..admin_user.schemas import AdminUserCreate, AdminUserCreateInternal

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

    This class provides a complete admin interface with features like:
    - Model CRUD operations with automatic form generation
    - User authentication and session management
    - Event logging and audit trails
    - Health monitoring
    - IP restriction and HTTPS enforcement

    Args:
        SECRET_KEY: Required secret key for JWT token generation.
        session: Async SQLAlchemy session
        mount_path: URL path where admin interface is mounted
        theme: UI theme ('dark-theme' or 'light-theme')
        ALGORITHM: JWT encryption algorithm
        ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiry in minutes
        REFRESH_TOKEN_EXPIRE_DAYS: Refresh token expiry in days
        admin_db_url: SQLite database URL for admin data
        admin_db_path: File path for SQLite admin database
        db_config: Optional pre-configured DatabaseConfig
        setup_on_initialization: Whether to run setup on init
        initial_admin: Initial admin user credentials
        allowed_ips: List of allowed IP addresses
        allowed_networks: List of allowed IP networks
        secure_cookies: Enable secure cookie flag
        enforce_https: Redirect HTTP to HTTPS
        https_port: HTTPS port for redirects
        track_events: Enable event logging
    """

    def __init__(
        self,
        session: AsyncSession,
        SECRET_KEY: str,
        mount_path: Optional[str] = "/admin",
        theme: Optional[str] = "dark-theme",
        ALGORITHM: Optional[str] = "HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES: int = 30,
        REFRESH_TOKEN_EXPIRE_DAYS: int = 1,
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        db_config: Optional[DatabaseConfig] = None,
        setup_on_initialization: bool = True,
        initial_admin: Optional[Union[dict, BaseModel]] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
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

        from ..event import create_admin_event_log, create_admin_audit_log

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
        self.ALGORITHM = ALGORITHM or "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
        self.REFRESH_TOKEN_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS

        self.token_service = TokenService(
            db_config=self.db_config,
            SECRET_KEY=SECRET_KEY,
            ALGORITHM=self.ALGORITHM,
            ACCESS_TOKEN_EXPIRE_MINUTES=ACCESS_TOKEN_EXPIRE_MINUTES,
            REFRESH_TOKEN_EXPIRE_DAYS=REFRESH_TOKEN_EXPIRE_DAYS,
        )

        self.admin_user_service = AdminUserService(db_config=self.db_config)
        self.initial_admin = initial_admin
        self.models: Dict[str, ModelConfig] = {}
        self.router = APIRouter(tags=["admin"])
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/{self.mount_path}/login")
        self.secure_cookies = secure_cookies

        self.session_manager = SessionManager(
            self.db_config,
            max_sessions_per_user=5,
            session_timeout_minutes=30,
            cleanup_interval_minutes=15,
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
        """
        if hasattr(self.db_config, "AdminEventLog") and self.db_config.AdminEventLog:
            assert hasattr(
                self.db_config.AdminEventLog, "metadata"
            ), "AdminEventLog must have metadata"

        if hasattr(self.db_config, "AdminAuditLog") and self.db_config.AdminAuditLog:
            assert hasattr(
                self.db_config.AdminAuditLog, "metadata"
            ), "AdminAuditLog must have metadata"

        async with self.db_config.admin_engine.begin() as conn:
            await conn.run_sync(self.db_config.AdminUser.metadata.create_all)
            await conn.run_sync(self.db_config.AdminTokenBlacklist.metadata.create_all)
            await conn.run_sync(self.db_config.AdminSession.metadata.create_all)

            if (
                self.track_events
                and self.db_config.AdminEventLog
                and self.db_config.AdminAuditLog
            ):
                await conn.run_sync(self.db_config.AdminEventLog.metadata.create_all)
                await conn.run_sync(self.db_config.AdminAuditLog.metadata.create_all)

    def setup_event_routes(self) -> None:
        """
        Set up routes for event log management.
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
        """

        db_dependency = cast(Callable[..., AsyncSession], self.db_config.get_admin_db)

        async def event_log_page_inner(
            request: Request, db: AsyncSession = Depends(db_dependency)
        ) -> RouteResponse:
            from ..event import EventType, EventStatus

            users = await self.db_config.crud_users.get_multi(db=db)

            context = await self.admin_site.get_base_context(db)
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
        """

        db_dependency = cast(Callable[..., AsyncSession], self.db_config.get_admin_db)

        async def event_log_content_inner(
            request: Request,
            db: AsyncSession = Depends(db_dependency),
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
                    user = await self.db_config.crud_users.get(db=db, username=username)
                    if user and isinstance(user, dict):
                        filter_criteria["user_id"] = user.get("id")

                if start_date:
                    start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    filter_criteria["timestamp__gte"] = start

                if end_date:
                    end = (
                        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    ).replace(tzinfo=timezone.utc)
                    filter_criteria["timestamp__lt"] = end

                events = await crud_events.get_multi(
                    db=db,
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
                                db=db, id=event.get("user_id")
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
                                    db=db, event_id=event.get("id")
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

                total_items: int = events.get("total_count", 0)
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
        """
        self.admin_authentication = AdminAuthentication(
            database_config=self.db_config,
            user_service=self.admin_user_service,
            token_service=self.token_service,
            oauth2_scheme=self.oauth2_scheme,
            event_integration=self.event_integration if self.track_events else None,
        )

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
                "AdminTokenBlacklist": {"view"},
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

        db_dependency = cast(
            Callable[..., AsyncSession], self.admin_authentication.get_current_user
        )

        self.router.add_api_route(
            "/management/health",
            self.health_check_page(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(db_dependency)],
            response_model=None,
        )

        self.router.add_api_route(
            "/management/health/content",
            self.health_check_content(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(db_dependency)],
            response_model=None,
        )

        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                self.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(db_dependency)],
                response_model=None,
            )
            self.router.add_api_route(
                "/management/events/content",
                self.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(db_dependency)],
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
        """

        db_dependency = cast(Callable[..., AsyncSession], self.db_config.session)

        async def health_check_page_inner(
            request: Request, db: AsyncSession = Depends(db_dependency)
        ) -> RouteResponse:
            context = await self.admin_site.get_base_context(db)
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

            try:
                test_token = await self.token_service.create_access_token(
                    {"test": "data"}
                )
                if test_token:
                    health_checks["token_service"] = {
                        "status": "healthy",
                        "message": "Token generation working",
                    }
            except Exception as e:
                health_checks["token_service"] = {
                    "status": "unhealthy",
                    "message": str(e),
                }

            context = {
                "request": request,
                "health_checks": health_checks,
                "last_checked": datetime.now(timezone.utc),
            }

            return self.templates.TemplateResponse(
                "admin/management/health_content.html", context
            )

        return health_check_content_inner

    async def _create_initial_admin(self, admin_data: Union[dict, BaseModel]) -> None:
        """
        Create initial admin user if none exists.
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
