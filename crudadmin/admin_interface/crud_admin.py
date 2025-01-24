import logging
import os
from typing import Type, Dict, Any, Union, Optional, List
from datetime import datetime, timezone
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

from .model_view import ModelView
from .admin_site import AdminSite
from ..admin_interface.auth import AdminAuthentication
from ..admin_interface.middleware.auth import AdminAuthMiddleware
from ..admin_interface.middleware.ip_restriction import IPRestrictionMiddleware
from ..session import create_admin_session_model, SessionManager
from ..admin_token.service import TokenService
from ..admin_user.service import AdminUserService
from ..core.db import DatabaseConfig
from ..admin_user.schemas import AdminUserCreate, AdminUserCreateInternal

logger = logging.getLogger("crudadmin")


class CRUDAdmin:
    def __init__(
        self,
        base: DeclarativeBase,
        session: AsyncSession,
        SECRET_KEY: str,
        mount_path: str | None = "/admin",
        theme: str | None = "dark-theme",
        ALGORITHM: str | None = "HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES: int = 30,
        REFRESH_TOKEN_EXPIRE_DAYS: int = 1,
        admin_db_url: str | None = None,
        admin_db_path: str | None = None,
        db_config: DatabaseConfig | None = None,
        setup_on_initialization: bool = True,
        initial_admin: Optional[Union[dict, BaseModel]] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
        secure_cookies: bool = True,
        enforce_https: bool = False,
        https_port: int = 443,
        track_events: bool = False,
    ) -> None:
        self.mount_path = mount_path.strip("/")
        self.theme = theme
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

        event_log_model = None
        audit_log_model = None
        if self.track_events:
            event_log_model = create_admin_event_log(base)
            audit_log_model = create_admin_audit_log(base)

        self.db_config = db_config or DatabaseConfig(
            base=base,
            session=session,
            admin_db_url=admin_db_url,
            admin_db_path=admin_db_path,
            admin_session=create_admin_session_model(base),
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
        self.ALGORITHM = ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
        self.REFRESH_TOKEN_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS

        self.token_service = TokenService(
            db_config=self.db_config,
            SECRET_KEY=SECRET_KEY,
            ALGORITHM=ALGORITHM,
            ACCESS_TOKEN_EXPIRE_MINUTES=ACCESS_TOKEN_EXPIRE_MINUTES,
            REFRESH_TOKEN_EXPIRE_DAYS=REFRESH_TOKEN_EXPIRE_DAYS,
        )

        self.admin_user_service = AdminUserService(db_config=self.db_config)

        self.initial_admin = initial_admin

        self.models: Dict[str, Dict[str, Any]] = {}
        self.router = APIRouter(tags=["admin"])
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/{mount_path}/login")
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

    async def initialize(self):
        """Initialize the admin database tables."""
        async with self.db_config.admin_engine.begin() as conn:
            await conn.run_sync(self.db_config.AdminUser.metadata.create_all)
            await conn.run_sync(self.db_config.AdminTokenBlacklist.metadata.create_all)
            await conn.run_sync(self.db_config.AdminSession.metadata.create_all)

            if (
                self.track_events
                and hasattr(self.db_config, "AdminEventLog")
                and hasattr(self.db_config, "AdminAuditLog")
            ):
                await conn.run_sync(self.db_config.AdminEventLog.metadata.create_all)
                await conn.run_sync(self.db_config.AdminAuditLog.metadata.create_all)

        if self.initial_admin:
            await self._create_initial_admin(self.initial_admin)

    def setup_event_routes(self):
        """Set up the event management routes."""
        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                self.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
            )
            self.router.add_api_route(
                "/management/events/content",
                self.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
            )

    def event_log_page(self):
        """Event log main page endpoint."""

        async def event_log_page_inner(
            request: Request, db: AsyncSession = Depends(self.db_config.session)
        ):
            from ..event import EventType, EventStatus

            context = await self.admin_site.get_base_context(db)
            context.update(
                {
                    "request": request,
                    "include_sidebar_and_header": True,
                    "event_types": [e.value for e in EventType],
                    "statuses": [s.value for s in EventStatus],
                    "mount_path": self.mount_path,
                }
            )

            return self.templates.TemplateResponse(
                "admin/management/events.html", context
            )

        return event_log_page_inner

    def event_log_content(self):
        """Event log content endpoint with filtering and pagination."""

        async def event_log_content_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            page: int = 1,
            limit: int = 10,
        ):
            try:
                crud_events = FastCRUD(self.db_config.AdminEventLog)
                events = await crud_events.get_multi(
                    db=db,
                    offset=(page - 1) * limit,
                    limit=limit,
                    sort_columns=["timestamp"],
                    sort_orders=["desc"],
                )

                enriched_events = []
                for event in events["data"]:
                    event_data = dict(event)

                    # Get user info
                    user = await self.db_config.crud_users.get(
                        db=db, id=event["user_id"]
                    )
                    event_data["username"] = user["username"] if user else "Unknown"

                    # Get audit log details if exists
                    if event["resource_type"] and event["resource_id"]:
                        crud_audits = FastCRUD(self.db_config.AdminAuditLog)
                        audit = await crud_audits.get(db=db, event_id=event["id"])
                        if audit:
                            event_data["details"] = {
                                "resource_details": {
                                    "model": event["resource_type"],
                                    "id": event["resource_id"],
                                    "changes": audit["new_state"]
                                    if audit["new_state"]
                                    else None,
                                }
                            }

                    enriched_events.append(event_data)

                return self.templates.TemplateResponse(
                    "admin/management/events_content.html",
                    {
                        "request": request,
                        "events": enriched_events,
                        "page": page,
                        "total_pages": (events["total_count"] + limit - 1) // limit,
                        "mount_path": self.mount_path,
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

            self.add_view(
                model=data["model"],
                create_schema=data["create_schema"],
                update_schema=data["update_schema"],
                update_internal_schema=data["update_internal_schema"],
                delete_schema=data["delete_schema"],
                include_in_models=False,
                allowed_actions=allowed_actions,
            )

        self.router.add_api_route(
            "/management/health",
            self.health_check_page(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user())],
        )

        self.router.add_api_route(
            "/management/health/content",
            self.health_check_content(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user())],
        )

        if self.track_events:
            self.router.add_api_route(
                "/management/events",
                self.event_log_page(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
            )
            self.router.add_api_route(
                "/management/events/content",
                self.event_log_content(),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
            )

        self.router.include_router(router=self.admin_site.router)

    def add_view(
        self,
        model: Type[DeclarativeBase],
        create_schema: Type[Any],
        update_schema: Type[Any],
        update_internal_schema: Type[Any],
        delete_schema: Type[Any],
        include_in_models: bool = True,
        allowed_actions: Optional[set[str]] = None,
    ) -> None:
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

        router_info = {
            "router": admin_view.router,
            "prefix": f"/{model_key}",
            "include_in_schema": False,
        }

        self.app.router.include_router(
            dependencies=[
                Depends(self.admin_site.admin_authentication.get_current_user)
            ],
            **router_info,
        )

    def health_check_page(self):
        async def health_check_page_inner(
            request: Request, db: AsyncSession = Depends(self.db_config.session)
        ):
            context = await self.admin_site.get_base_context(db)
            context.update({"request": request, "include_sidebar_and_header": True})

            return self.templates.TemplateResponse(
                "admin/management/health.html", context
            )

        return health_check_page_inner

    def health_check_content(self):
        async def health_check_content_inner(
            request: Request, db: AsyncSession = Depends(self.db_config.session)
        ):
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
                        admin_session, object=internal_data
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
