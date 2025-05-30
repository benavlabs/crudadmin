import logging
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import Any, Dict, Optional, cast

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_user.service import AdminUserService
from ..core.db import DatabaseConfig
from ..event import EventType, log_auth_action
from ..session.manager import SessionManager
from .auth import AdminAuthentication
from .typing import RouteResponse

logger = logging.getLogger(__name__)

EndpointCallable = Callable[..., Any]


class AdminSite:
    """
    Core admin interface site handler managing authentication, routing, and views.

    **Handles the core functionality of the admin interface including:**
    - Authentication and session management
    - Route configuration and URL handling
    - Template rendering and context management
    - Dashboard and model views
    - Event logging and audit trails
    - Security and access control

    The AdminSite class serves as the central coordinator for all admin functionality,
    managing user sessions, handling authentication flows, and providing secure access
    to administrative features.

    Args:
        database_config: Database configuration for admin interface
        templates_directory: Path to template files
        models: Dictionary of registered models
        admin_authentication: Authentication handler
        mount_path: URL prefix for admin routes
        theme: Active UI theme
        secure_cookies: Enable secure cookie flags
        event_integration: Optional event logging integration

    Attributes:
        db_config: Database configuration instance
        router: FastAPI router for admin endpoints
        templates: Jinja2 template handler
        models: Dictionary of registered models
        admin_user_service: Service for user management
        admin_authentication: Authentication handler
        mount_path: URL prefix for admin routes
        theme: Active UI theme
        event_integration: Event logging handler
        session_manager: Session tracking service
        secure_cookies: Cookie security flag

    Examples:
        Basic setup with SQLite:
        ```python
        from fastapi.templating import Jinja2Templates
        from .auth import AdminAuthentication
        from .db import DatabaseConfig

        admin_site = AdminSite(
            database_config=db_config,
            templates_directory="templates",
            models={},  # Empty initially
            admin_authentication=auth_handler,
            mount_path="/admin",
            theme="dark-theme",
            secure_cookies=True
        )

        # Add routes
        admin_site.setup_routes()
        ```

        Production configuration:
        ```python
        admin_site = AdminSite(
            database_config=db_config,
            templates_directory=templates_path,
            models=model_registry,
            admin_authentication=auth_handler,
            mount_path="/admin",
            theme="dark-theme",
            secure_cookies=True,
            event_integration=event_logger
        )
        ```
    """

    def __init__(
        self,
        database_config: DatabaseConfig,
        templates_directory: str,
        models: Dict[str, Any],
        admin_authentication: AdminAuthentication,
        mount_path: str,
        theme: str,
        secure_cookies: bool,
        event_integration: Optional[Any] = None,
    ) -> None:
        self.db_config: DatabaseConfig = database_config
        self.router: APIRouter = APIRouter()
        self.templates: Jinja2Templates = Jinja2Templates(directory=templates_directory)
        self.models: Dict[str, Any] = models
        self.admin_user_service: AdminUserService = AdminUserService(
            db_config=database_config
        )
        self.admin_authentication: AdminAuthentication = admin_authentication
        self.admin_user_service = admin_authentication.user_service

        self.mount_path: str = mount_path
        self.theme: str = theme
        self.event_integration: Optional[Any] = event_integration

        self.session_manager: SessionManager = SessionManager(
            self.db_config,
            max_sessions_per_user=5,
            session_timeout_minutes=30,
            cleanup_interval_minutes=15,
        )

        self.secure_cookies: bool = secure_cookies

    def setup_routes(self) -> None:
        """
        Configure all admin interface routes including auth, dashboard and model views.

        Routes Created:
            **Auth Routes:**
                - POST /login - Handle login form submission
                - GET /login - Display login page
                - GET /logout - Process user logout

            **Dashboard Routes:**
                - GET / - Main dashboard view
                - GET /dashboard-content - HTMX dashboard updates

        Notes:
            - All routes except login require authentication
            - Routes use Jinja2 templates for rendering
            - HTMX integration for dynamic updates
            - Event logging integration if enabled

        Example:
            ```python
            admin_site = AdminSite(...)
            admin_site.setup_routes()
            app.include_router(admin_site.router)
            ```
        """
        self.router.add_api_route(
            "/login",
            self.login_page(),
            methods=["POST"],
            include_in_schema=False,
            response_model=None,
        )
        self.router.add_api_route(
            "/logout",
            self.logout_endpoint(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user)],
            response_model=None,
        )
        self.router.add_api_route(
            "/login",
            self.admin_login_page(),
            methods=["GET"],
            include_in_schema=False,
            response_model=None,
        )
        self.router.add_api_route(
            "/dashboard-content",
            self.dashboard_content(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user)],
            response_model=None,
        )
        self.router.add_api_route(
            "/",
            self.dashboard_page(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user)],
            response_model=None,
        )

    def login_page(self) -> EndpointCallable:
        """
        Create login form handler for admin authentication.

        Returns:
            FastAPI route handler that processes login form submission.

        Notes:
            - Validates credentials and creates user session on success
            - Sets secure cookies with session ID
            - Logs login attempts if event tracking enabled
        """

        @log_auth_action(EventType.LOGIN)
        async def login_page_inner(
            request: Request,
            response: Response,
            form_data: OAuth2PasswordRequestForm = Depends(),
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            event_integration: Optional[Any] = Depends(lambda: self.event_integration),
        ) -> RouteResponse:
            logger.info("Processing login attempt...")
            try:
                user = await self.admin_user_service.authenticate_user(
                    form_data.username, form_data.password, db=db
                )
                if not user:
                    logger.warning(
                        f"Authentication failed for user: {form_data.username}"
                    )
                    return self.templates.TemplateResponse(
                        "auth/login.html",
                        {
                            "request": request,
                            "error": "Invalid credentials. Please try again.",
                            "mount_path": self.mount_path,
                            "theme": self.theme,
                        },
                    )

                request.state.user = user
                logger.info("User authenticated successfully, creating session")

                try:
                    logger.info("Creating user session...")
                    session = await self.session_manager.create_session(
                        request=request,
                        user_id=user["id"],
                        metadata={
                            "login_type": "password",
                            "username": user["username"],
                            "creation_time": datetime.now(UTC).isoformat(),
                        },
                    )

                    if not session:
                        logger.error("Failed to create session")
                        raise Exception("Session creation failed")

                    logger.info(f"Session created successfully: {session.session_id}")

                    response = RedirectResponse(
                        url=f"/{self.mount_path}/", status_code=303
                    )

                    session_timeout_seconds = int(
                        self.session_manager.session_timeout.total_seconds()
                    )

                    response.set_cookie(
                        key="session_id",
                        value=session.session_id,
                        httponly=True,
                        secure=self.secure_cookies,
                        max_age=session_timeout_seconds,
                        path=f"/{self.mount_path}",
                        samesite="lax",
                    )

                    await db.commit()
                    logger.info("Login completed successfully")
                    return response

                except Exception as e:
                    logger.error(
                        f"Error during session creation: {str(e)}", exc_info=True
                    )
                    await db.rollback()
                    return self.templates.TemplateResponse(
                        "auth/login.html",
                        {
                            "request": request,
                            "error": f"Error creating session: {str(e)}",
                            "mount_path": self.mount_path,
                            "theme": self.theme,
                        },
                    )

            except Exception as e:
                logger.error(f"Error during login: {str(e)}", exc_info=True)
                return self.templates.TemplateResponse(
                    "auth/login.html",
                    {
                        "request": request,
                        "error": "An error occurred during login. Please try again.",
                        "mount_path": self.mount_path,
                        "theme": self.theme,
                    },
                )

        return cast(EndpointCallable, login_page_inner)

    def logout_endpoint(self) -> EndpointCallable:
        """
        Create logout handler for admin authentication.

        Returns:
            FastAPI route handler that terminates session and clears auth cookies.

        Notes:
            - Revokes access tokens
            - Terminates active sessions
            - Cleans up auth cookies
            - Logs logout events if tracking enabled
        """

        @log_auth_action(EventType.LOGOUT)
        async def logout_endpoint_inner(
            request: Request,
            response: Response,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            session_id: Optional[str] = Cookie(None),
            event_integration: Optional[Any] = Depends(lambda: self.event_integration),
        ) -> RouteResponse:
            if session_id:
                await self.session_manager.terminate_session(
                    db=db, session_id=session_id
                )

            response = RedirectResponse(
                url=f"/{self.mount_path}/login", status_code=303
            )

            response.delete_cookie(key="session_id", path=f"/{self.mount_path}")

            return response

        return cast(EndpointCallable, logout_endpoint_inner)

    def admin_login_page(self) -> EndpointCallable:
        """
        Create login page handler for the admin interface.

        Returns:
            FastAPI route handler for login page

        Notes:
            - Checks for existing auth cookies
            - Validates active sessions
            - Redirects authenticated users to dashboard
            - Displays login form with any error messages
        """

        async def admin_login_page_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            try:
                session_id = request.cookies.get("session_id")

                if session_id:
                    is_valid_session = await self.session_manager.validate_session(
                        db=db, session_id=session_id
                    )

                    if is_valid_session:
                        return RedirectResponse(
                            url=f"/{self.mount_path}/", status_code=303
                        )

            except Exception:
                pass

            error = request.query_params.get("error")
            return self.templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "mount_path": self.mount_path,
                    "theme": self.theme,
                    "error": error,
                },
            )

        return cast(EndpointCallable, admin_login_page_inner)

    def dashboard_content(self) -> EndpointCallable:
        """
        Create dashboard content handler for HTMX dynamic updates.

        Returns:
            FastAPI route handler for dashboard content
        """

        async def dashboard_content_inner(
            request: Request,
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            app_db: AsyncSession = Depends(
                cast(
                    Callable[..., AsyncGenerator[AsyncSession, None]],
                    self.db_config.session,
                )
            ),
        ) -> RouteResponse:
            """
            Renders partial content for the dashboard (HTMX).
            """
            context = await self.get_base_context(admin_db=admin_db, app_db=app_db)
            context.update({"request": request})
            return self.templates.TemplateResponse(
                "admin/dashboard/dashboard_content.html", context
            )

        return cast(EndpointCallable, dashboard_content_inner)

    async def get_base_context(
        self, admin_db: AsyncSession, app_db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get common context data needed for base template.

        Args:
            db: Database session for queries

        Returns:
            Dictionary containing auth tables, model data, and config

        Notes:
            - Queries model counts asynchronously
            - Includes auth model stats and status
            - Required by all admin templates
        """
        auth_model_counts: Dict[str, int] = {}
        for model_name, model_data in self.admin_authentication.auth_models.items():
            crud_obj = cast(FastCRUD, model_data["crud"])
            if model_name == "AdminSession":
                total_count = await crud_obj.count(self.db_config.admin_session)
                active_count = await crud_obj.count(
                    self.db_config.admin_session, is_active=True
                )
                auth_model_counts[model_name] = total_count
                auth_model_counts[f"{model_name}_active"] = active_count
            else:
                count = await crud_obj.count(self.db_config.admin_session)
                auth_model_counts[model_name] = count

        model_counts: Dict[str, int] = {}
        for model_name, model_data in self.models.items():
            crud = cast(FastCRUD, model_data["crud"])
            cnt = await crud.count(app_db)
            model_counts[model_name] = cnt

        return {
            "auth_table_names": self.admin_authentication.auth_models.keys(),
            "table_names": self.models.keys(),
            "auth_model_counts": auth_model_counts,
            "model_counts": model_counts,
            "mount_path": self.mount_path,
            "track_events": self.event_integration is not None,
            "theme": self.theme,
        }

    def dashboard_page(self) -> EndpointCallable:
        """
        Create main dashboard page handler.

        Returns:
            FastAPI route handler for the admin dashboard
        """

        async def dashboard_page_inner(
            request: Request,
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            app_db: AsyncSession = Depends(
                cast(
                    Callable[..., AsyncGenerator[AsyncSession, None]],
                    self.db_config.session,
                )
            ),
        ) -> RouteResponse:
            context = await self.get_base_context(admin_db=admin_db, app_db=app_db)
            context.update({"request": request, "include_sidebar_and_header": True})
            return self.templates.TemplateResponse(
                "admin/dashboard/dashboard.html", context
            )

        return cast(EndpointCallable, dashboard_page_inner)

    def admin_auth_model_page(self, model_key: str) -> EndpointCallable:
        """
        Create page handler for authentication model views.

        Args:
            model_key: Name of authentication model to display

        Returns:
            FastAPI route handler for auth model list view

        Notes:
            - Handles pagination and sorting
            - Formats special fields like JSON
            - Integrates with event logging if enabled
        """

        async def admin_auth_model_page_inner(
            request: Request,
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            auth_model = self.admin_authentication.auth_models[model_key]
            sqlalchemy_model = cast(Any, auth_model["model"])

            table_columns = []
            if hasattr(sqlalchemy_model, "__table__"):
                table_columns = [
                    column.key for column in sqlalchemy_model.__table__.columns
                ]

            page_str = request.query_params.get("page", "1")
            limit_str = request.query_params.get("rows-per-page-select", "10")

            try:
                page = int(page_str)
                limit = int(limit_str)
            except ValueError:
                page = 1
                limit = 10

            offset = (page - 1) * limit
            items: Dict[str, Any] = {"data": [], "total_count": 0}
            try:
                crud = cast(FastCRUD, auth_model["crud"])
                fetched = await crud.get_multi(db=admin_db, offset=offset, limit=limit)
                items = dict(fetched)

                logger.info(f"Retrieved items for {model_key}: {items}")
                total_items = items.get("total_count", 0)

                if model_key == "AdminSession":
                    formatted_items = []
                    data = items["data"]
                    for item in data:
                        if not isinstance(item, dict):
                            item = {
                                k: v
                                for k, v in vars(item).items()
                                if not k.startswith("_")
                            }
                        if "device_info" in item and isinstance(
                            item["device_info"], dict
                        ):
                            item["device_info"] = str(item["device_info"])
                        if "session_metadata" in item and isinstance(
                            item["session_metadata"], dict
                        ):
                            item["session_metadata"] = str(item["session_metadata"])
                        formatted_items.append(item)
                    items["data"] = formatted_items
            except Exception as e:
                logger.error(
                    f"Error retrieving {model_key} data: {str(e)}", exc_info=True
                )
                total_items = 0

            total_pages = max(1, (total_items + limit - 1) // limit)

            context = await self.get_base_context(admin_db=admin_db, app_db=db)
            context.update(
                {
                    "request": request,
                    "model_items": items["data"],
                    "model_name": model_key,
                    "table_columns": table_columns,
                    "current_page": page,
                    "rows_per_page": limit,
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "primary_key_info": self.db_config.get_primary_key_info(
                        cast(Any, sqlalchemy_model)
                    ),
                    "sort_column": None,
                    "sort_order": "asc",
                    "include_sidebar_and_header": True,
                }
            )

            return self.templates.TemplateResponse("admin/model/list.html", context)

        return cast(EndpointCallable, admin_auth_model_page_inner)
