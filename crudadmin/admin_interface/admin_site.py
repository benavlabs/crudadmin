import logging
from collections.abc import AsyncGenerator, Callable
from functools import partial
from typing import Any, Dict, Optional, cast

from crudauth.exceptions import (
    RateLimitException,
    SudoLockoutError,
    UnauthorizedException,
)
from crudauth.utils import is_cross_site, safe_redirect_path
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_user.schemas import AdminUserRead
from ..core.db import DatabaseConfig
from .auth import AdminAuthentication
from .paths import AdminPaths
from .record_counts import RecordCounts
from .typing import RouteResponse

logger = logging.getLogger(__name__)

EndpointCallable = Callable[..., Any]

LOGIN_MESSAGE_FOR_ERROR_CODE = {
    "login_required": "Please log in to access this page.",
    "session_ended": "Your session has ended. Please log in again.",
}

INVALID_CREDENTIALS = "Invalid username or password."
INCORRECT_PASSWORD = "Incorrect password."
TOO_MANY_ATTEMPTS = "Too many failed attempts. Please wait a few minutes and try again."
CROSS_SITE_LOGIN = "Log in from the admin's own login page."


class AdminSite:
    """Routes for logging in and out, the dashboard and the sessions page.

    Authentication is crudauth's: passwords are checked by
    ``authenticate_password`` (with its login lockout), sessions are created by the
    session transport's ``complete_login`` and ended by ``complete_logout``. This
    class renders the HTML around them.

    Args:
        database_config: Database configuration for the admin interface.
        templates_directory: Path to the template files.
        models: The registered models.
        admin_authentication: The admin's authentication.
        mount_path: URL prefix of the admin routes.
        theme: Active UI theme.
        event_integration: Event logging, when enabled.
    """

    def __init__(
        self,
        database_config: DatabaseConfig,
        templates_directory: str,
        models: Dict[str, Any],
        admin_authentication: AdminAuthentication,
        mount_path: str,
        theme: str,
        event_integration: Optional[Any] = None,
    ) -> None:
        self.db_config: DatabaseConfig = database_config
        self.router: APIRouter = APIRouter()
        self.public_router: APIRouter = APIRouter()
        self.templates: Jinja2Templates = Jinja2Templates(directory=templates_directory)
        self.models: Dict[str, Any] = models
        self.admin_authentication: AdminAuthentication = admin_authentication
        self.mount_path: str = mount_path
        self.paths = AdminPaths.for_mount_segment(mount_path)
        self.theme: str = theme
        self.event_integration: Optional[Any] = event_integration
        self.record_counts = RecordCounts()

    def get_url_prefix(self) -> str:
        """Get the URL prefix for admin routes, handling root mount path correctly."""
        return self.paths.prefix

    @property
    def dashboard_url(self) -> str:
        return self.paths.home

    def setup_routes(self) -> None:
        """Register the admin site's routes.

        Login and logout go on ``public_router``. Everything else goes on
        ``router``, which ``CRUDAdmin`` mounts behind the logged-in-admin
        dependency, so a route added here is protected without declaring it.
        """
        public_routes: list[tuple[str, EndpointCallable, str]] = [
            ("/login", self.login_page(), "GET"),
            ("/login", self.login_endpoint(), "POST"),
            ("/logout", self.logout_endpoint(), "POST"),
        ]
        protected_routes: list[tuple[str, EndpointCallable, str]] = [
            ("/sudo", self.sudo_page(), "GET"),
            ("/sudo", self.sudo_endpoint(), "POST"),
            ("/", self.dashboard_page(), "GET"),
            ("/dashboard-content", self.dashboard_content(), "GET"),
            ("/management/sessions", self.sessions_page(), "GET"),
            ("/management/sessions/content", self.sessions_content(), "GET"),
            ("/management/sessions/revoke", self.revoke_session_endpoint(), "POST"),
        ]
        for router, routes in (
            (self.public_router, public_routes),
            (self.router, protected_routes),
        ):
            for path, endpoint, method in routes:
                router.add_api_route(
                    path,
                    endpoint,
                    methods=[method],
                    include_in_schema=False,
                    response_model=None,
                )

    def _login_response(
        self, request: Request, error: Optional[str], status_code: int = 200
    ) -> Response:
        return self.templates.TemplateResponse(
            name="auth/login.html",
            request=request,
            context={
                "error": error,
                "url_prefix": self.get_url_prefix(),
                "theme": self.theme,
            },
            status_code=status_code,
        )

    def login_page(self) -> EndpointCallable:
        """The login form; an admin who is already logged in goes to the dashboard."""

        async def login_page_inner(request: Request) -> RouteResponse:
            principal = await self.admin_authentication.auth.resolve_principal(request)
            if principal is not None:
                return RedirectResponse(url=self.dashboard_url, status_code=303)
            error_code = request.query_params.get("error", "")
            error = LOGIN_MESSAGE_FOR_ERROR_CODE.get(error_code)
            return self._login_response(request, error)

        return cast(EndpointCallable, login_page_inner)

    def login_endpoint(self) -> EndpointCallable:
        """Check the credentials, then create the session and set its cookies.

        The password check is crudauth's: it counts failures toward the login
        lockout, takes as long for an unknown username as for a wrong password, and
        upgrades a password hash written by an older crudadmin.
        """
        auth = self.admin_authentication.auth
        transport = self.admin_authentication.session_transport

        async def login_endpoint_inner(
            request: Request,
            username: str = Form(),
            password: str = Form(),
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            if is_cross_site(request):
                return self._login_response(request, CROSS_SITE_LOGIN, 403)
            try:
                user = await auth.authenticate_password(
                    db, username, password, request=request
                )
            except RateLimitException:
                return self._login_response(request, TOO_MANY_ATTEMPTS, 429)
            except UnauthorizedException:
                return self._login_response(request, INVALID_CREDENTIALS, 401)

            response = RedirectResponse(url=self.dashboard_url, status_code=303)
            await transport.complete_login(request, response, user, {})
            return response

        return cast(EndpointCallable, login_endpoint_inner)

    def logout_endpoint(self) -> EndpointCallable:
        """End the session and clear its cookies.

        A POST that needs the ``X-CSRF-Token`` header while the session is live, so
        a link or an image on another page can't log the admin out.
        """
        transport = self.admin_authentication.session_transport

        async def logout_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            response = RedirectResponse(url=self.paths.login, status_code=303)
            await transport.complete_logout(request, response, db)
            return response

        return cast(EndpointCallable, logout_endpoint_inner)

    def sudo_page(self) -> EndpointCallable:
        """Ask the admin to confirm their password before changing admin accounts."""

        async def sudo_page_inner(request: Request) -> RouteResponse:
            user = request.state.user
            return self.templates.TemplateResponse(
                name="auth/login.html",
                request=request,
                context={
                    "url_prefix": self.get_url_prefix(),
                    "theme": self.theme,
                    "username": user["username"],
                    "sudo_next": safe_redirect_path(
                        request.query_params.get("next"), self.dashboard_url
                    ),
                },
            )

        return cast(EndpointCallable, sudo_page_inner)

    def sudo_endpoint(self) -> EndpointCallable:
        """Check the password and mark the session as recently confirmed."""
        sudo = self.admin_authentication.auth.sudo
        assert sudo is not None

        async def sudo_endpoint_inner(
            request: Request,
            password: str = Form(),
            next: str = Form(default=""),
        ) -> RouteResponse:
            next_path = safe_redirect_path(next, self.dashboard_url)
            try:
                await sudo.elevate(request.state.principal, password, request=request)
            except UnauthorizedException:
                return self._sudo_page_with_error(
                    request, next_path, INCORRECT_PASSWORD, 401
                )
            except (RateLimitException, SudoLockoutError):
                return self._sudo_page_with_error(
                    request, next_path, TOO_MANY_ATTEMPTS, 429
                )
            return RedirectResponse(url=next_path, status_code=303)

        return cast(EndpointCallable, sudo_endpoint_inner)

    def _sudo_page_with_error(
        self, request: Request, next_path: str, error: str, status_code: int
    ) -> Response:
        return self.templates.TemplateResponse(
            name="auth/login.html",
            request=request,
            context={
                "url_prefix": self.get_url_prefix(),
                "theme": self.theme,
                "username": request.state.user["username"],
                "sudo_next": next_path,
                "error": error,
            },
            status_code=status_code,
        )

    def dashboard_content(self) -> EndpointCallable:
        """Dashboard partial for HTMX updates."""

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
            context = self.get_base_context(request)
            auth_model_counts, model_counts = await self._record_counts(
                admin_db, app_db, context["is_superuser"]
            )
            context.update(
                {"auth_model_counts": auth_model_counts, "model_counts": model_counts}
            )
            return self.templates.TemplateResponse(
                name="admin/dashboard/dashboard_content.html",
                request=request,
                context=context,
            )

        return cast(EndpointCallable, dashboard_content_inner)

    def get_base_context(self, request: Optional[Request] = None) -> Dict[str, Any]:
        """Context every admin page template needs: navigation and the user."""
        user: Optional[Dict[str, Any]] = (
            getattr(request.state, "user", None) if request is not None else None
        )
        return {
            "auth_table_names": self.admin_authentication.auth_models.keys(),
            "table_names": self.models.keys(),
            "url_prefix": self.get_url_prefix(),
            "track_events": self.event_integration is not None,
            "theme": self.theme,
            "current_user": user,
            "is_superuser": bool(user and user.get("is_superuser")),
            "csrf_cookie_name": self.admin_authentication.csrf_cookie_name,
        }

    async def _record_counts(
        self, admin_db: AsyncSession, app_db: AsyncSession, is_superuser: bool
    ) -> tuple[Dict[str, int], Dict[str, int]]:
        """Counts for the dashboard: every model's, and the admins' for a superuser."""
        auth_model_counts: Dict[str, int] = {}
        if is_superuser:
            for model_name, model_data in self.admin_authentication.auth_models.items():
                auth_crud = cast(FastCRUD, model_data["crud"])
                auth_model_counts[model_name] = await self.record_counts.get(
                    model_name, partial(auth_crud.count, admin_db)
                )

        model_counts: Dict[str, int] = {}
        for model_name, model_data in self.models.items():
            model_crud = cast(FastCRUD, model_data["crud"])
            model_counts[model_name] = await self.record_counts.get(
                model_name, partial(model_crud.count, app_db)
            )
        return auth_model_counts, model_counts

    def dashboard_page(self) -> EndpointCallable:
        """The admin dashboard."""

        async def dashboard_page_inner(
            request: Request,
        ) -> RouteResponse:
            context = self.get_base_context(request)
            context.update({"include_sidebar_and_header": True})
            return self.templates.TemplateResponse(
                name="admin/dashboard/dashboard.html", request=request, context=context
            )

        return cast(EndpointCallable, dashboard_page_inner)

    def sessions_page(self) -> EndpointCallable:
        """The sessions page: an admin's own sessions, or every admin's for a superuser."""

        async def sessions_page_inner(
            request: Request,
        ) -> RouteResponse:
            context = self.get_base_context(request)
            context.update({"include_sidebar_and_header": True})
            return self.templates.TemplateResponse(
                name="admin/management/sessions.html",
                request=request,
                context=context,
            )

        return cast(EndpointCallable, sessions_page_inner)

    async def _visible_admins(
        self, request: Request, admin_db: AsyncSession
    ) -> list[Dict[str, Any]]:
        """The admins whose sessions the current admin may see and end."""
        user = request.state.user
        if not user["is_superuser"]:
            return [user]
        admins = await self.db_config.crud_users.get_multi(
            db=admin_db, schema_to_select=AdminUserRead, limit=None
        )
        return admins["data"]

    def sessions_content(self) -> EndpointCallable:
        """The sessions list, grouped by admin."""

        async def sessions_content_inner(
            request: Request,
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            return await self._render_sessions(request, admin_db)

        return cast(EndpointCallable, sessions_content_inner)

    async def _render_sessions(
        self, request: Request, admin_db: AsyncSession
    ) -> RouteResponse:
        manager = self.admin_authentication.auth.sessions
        current_session = request.cookies.get(manager.session_cookie_name)
        groups = []
        for admin in await self._visible_admins(request, admin_db):
            sessions = await manager.list_for_user(
                admin["id"], current_session_id=current_session
            )
            sessions.sort(key=lambda s: s["last_activity"], reverse=True)
            groups.append(
                {
                    "user_id": admin["id"],
                    "username": admin["username"],
                    "sessions": sessions,
                }
            )
        return self.templates.TemplateResponse(
            name="admin/management/sessions_content.html",
            request=request,
            context={"session_groups": groups, "url_prefix": self.get_url_prefix()},
        )

    def revoke_session_endpoint(self) -> EndpointCallable:
        """End one session. An admin may end their own; a superuser, anyone's."""

        async def revoke_session_inner(
            request: Request,
            user_id: int = Form(),
            handle: str = Form(),
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> RouteResponse:
            user = request.state.user
            if user_id != user["id"] and not user["is_superuser"]:
                return Response(status_code=403)
            await self.admin_authentication.auth.sessions.revoke_by_handle(
                handle, owner_id=user_id
            )
            return await self._render_sessions(request, admin_db)

        return cast(EndpointCallable, revoke_session_inner)
