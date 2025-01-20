import logging
import os
from typing import Type, Dict, Any, Union, Optional, List

from fastapi import APIRouter, FastAPI, Depends
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .model_view import ModelView
from .admin_site import AdminSite
from ..admin_interface.auth import AdminAuthentication
from ..admin_interface.middleware.auth import AdminAuthMiddleware
from ..admin_interface.middleware.ip_restriction import IPRestrictionMiddleware
from ..session import create_admin_session_model, SessionManager
from ..token.service import TokenService
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
    ) -> None:
        self.mount_path = mount_path.strip('/')
        self.theme = theme
        self.templates_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "templates"
        )

        self.static_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "static"
        )

        self.app = FastAPI()
        self.app.mount(
            "/static", 
            StaticFiles(directory=self.static_directory), 
            name="admin_static"
        )

        self.app.add_middleware(AdminAuthMiddleware, admin_instance=self)

        self.db_config = db_config or DatabaseConfig(
            base=base,
            session=session,
            admin_db_url=admin_db_url,
            admin_db_path=admin_db_path,
            admin_session=create_admin_session_model(base),
        )

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
            cleanup_interval_minutes=15
        )

        self.templates = Jinja2Templates(directory=self.templates_directory)

        if setup_on_initialization:
            self.setup()

        if allowed_ips or allowed_networks:
            self.app.add_middleware(
                IPRestrictionMiddleware,
                allowed_ips=allowed_ips,
                allowed_networks=allowed_networks
            )

        if enforce_https:
            from .middleware.https import HTTPSRedirectMiddleware
            self.app.add_middleware(
                HTTPSRedirectMiddleware,
                https_port=https_port
            )
        
        self.app.include_router(self.router)

    async def initialize(self):
        """Initialize the admin database tables."""
        async with self.db_config.admin_engine.begin() as conn:
            await conn.run_sync(self.db_config.AdminUser.metadata.create_all)
            await conn.run_sync(self.db_config.AdminTokenBlacklist.metadata.create_all)
            await conn.run_sync(self.db_config.AdminSession.metadata.create_all)
        
        if self.initial_admin:
            await self._create_initial_admin(self.initial_admin)

    def setup(
        self,
    ) -> None:
        self.admin_authentication = AdminAuthentication(
            database_config=self.db_config,
            user_service=self.admin_user_service,
            token_service=self.token_service,
            oauth2_scheme=self.oauth2_scheme,
        )

        self.admin_site = AdminSite(
            database_config=self.db_config,
            templates_directory=self.templates_directory,
            models=self.models,
            admin_authentication=self.admin_authentication,
            mount_path=self.mount_path,
            theme=self.theme,
            secure_cookies=self.secure_cookies,
        )

        self.admin_site.setup_routes()

        for data in self.admin_authentication.auth_models.values():
            self.add_view(
                model=data["model"],
                create_schema=data["create_schema"],
                update_schema=data["update_schema"],
                update_internal_schema=data["update_internal_schema"],
                delete_schema=data["delete_schema"],
                include_in_models=False
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
    ) -> None:
        model_key = model.__name__
        if include_in_models:
            self.models[model_key] = {
                "model": model,
                "create_schema": create_schema,
                "update_schema": update_schema,
                "update_internal_schema": update_internal_schema,
                "delete_schema": delete_schema,
                "crud": FastCRUD(model)
            }

        admin_view = ModelView(
            database_config=self.db_config,
            templates=self.templates,
            model=model,
            create_schema=create_schema,
            update_schema=update_schema,
            update_internal_schema=update_internal_schema,
            delete_schema=delete_schema,
            admin_site=self.admin_site,
        )

        router_info = {
            "router": admin_view.router,
            "prefix": f"/{model_key}",
            "include_in_schema": False,
        }

        self.app.router.include_router(
            dependencies=[
                Depends(self.admin_site.admin_authentication.get_current_user)
            ], 
            **router_info
        )

    async def _create_initial_admin(
        self, 
        admin_data: Union[dict, BaseModel]
    ) -> None:
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
                        msg = "Initial admin data must be either a dict or Pydantic model"
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
                        admin_session, 
                        object=internal_data
                    )
                    await admin_session.commit()
                    logger.info("Created initial admin user - username: %s", create_data.username)

            except Exception as e:
                logger.error("Error creating initial admin user: %s", str(e), exc_info=True)
                raise
