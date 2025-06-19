import logging
from typing import TYPE_CHECKING

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from crudadmin import CRUDAdmin

logger = logging.getLogger(__name__)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, admin_instance: "CRUDAdmin"):
        super().__init__(app)
        self.admin_instance = admin_instance

    def _add_no_cache_headers(self, response: Response) -> None:
        """Add HTTP headers to prevent browser caching of admin pages.

        This prevents the issue where admin pages remain accessible after
        logout due to browser caching.
        """
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    def _should_add_cache_headers(self, response: Response) -> bool:
        """Determine if cache headers should be added to the response.

        Returns False for redirect responses to avoid interfering with
        browser redirect handling and cookie transmission.
        """
        return not (300 <= response.status_code < 400)

    async def dispatch(self, request: Request, call_next):
        expected_prefix = (
            f"/{self.admin_instance.mount_path}/"
            if self.admin_instance.mount_path
            else "/"
        )
        if not request.url.path.startswith(expected_prefix):
            return await call_next(request)

        is_login_path = request.url.path.endswith("/login")
        is_static_path = "/static/" in request.url.path

        if is_login_path or is_static_path:
            response = await call_next(request)
            return response

        logger.debug(f"Checking auth for path: {request.url.path}")

        async for db in self.admin_instance.db_config.get_admin_db():
            try:
                session_id = request.cookies.get("session_id")

                logger.debug(f"Found session_id: {bool(session_id)}")

                if not session_id:
                    logger.debug("Missing session_id")
                    login_url = f"{self.admin_instance.get_url_prefix()}/login?error=Please+log+in+to+access+this+page"
                    return RedirectResponse(
                        url=login_url,
                        status_code=303,
                    )

                try:
                    session_data = (
                        await self.admin_instance.session_manager.validate_session(
                            session_id=session_id, update_activity=True
                        )
                    )

                    if not session_data:
                        logger.debug("Invalid or expired session")
                        login_url = f"{self.admin_instance.get_url_prefix()}/login?error=Session+expired"
                        return RedirectResponse(
                            url=login_url,
                            status_code=303,
                        )

                    user_id = session_data.user_id
                    user = await self.admin_instance.db_config.crud_users.get(
                        db=db, id=user_id
                    )

                    if not user:
                        logger.debug("User not found for session")
                        login_url = f"{self.admin_instance.get_url_prefix()}/login?error=User+not+found"
                        return RedirectResponse(
                            url=login_url,
                            status_code=303,
                        )

                    request.state.user = user

                    await self.admin_instance.session_manager.cleanup_expired_sessions()

                    response = await call_next(request)

                    if self._should_add_cache_headers(response):
                        self._add_no_cache_headers(response)

                    return response

                except Exception as e:
                    logger.error(f"Auth error: {str(e)}", exc_info=True)
                    if (
                        request.url.path.endswith("/crud")
                        or "/crud/" in request.url.path
                    ):
                        raise
                    login_url = f"{self.admin_instance.get_url_prefix()}/login?error=Authentication+error"
                    return RedirectResponse(
                        url=login_url,
                        status_code=303,
                    )

            except Exception as e:
                logger.error(f"Middleware error: {str(e)}", exc_info=True)
                raise

        return await call_next(request)
