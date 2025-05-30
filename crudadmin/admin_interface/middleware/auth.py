import logging
from typing import TYPE_CHECKING

from fastapi import Request
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

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(f"/{self.admin_instance.mount_path}/"):
            return await call_next(request)

        is_login_path = request.url.path.endswith("/login")
        is_static_path = "/static/" in request.url.path

        if is_login_path or is_static_path:
            return await call_next(request)

        logger.debug(f"Checking auth for path: {request.url.path}")

        async for db in self.admin_instance.db_config.get_admin_db():
            try:
                session_id = request.cookies.get("session_id")

                logger.debug(f"Found session_id: {bool(session_id)}")

                if not session_id:
                    logger.debug("Missing session_id")
                    return RedirectResponse(
                        url=f"/{self.admin_instance.mount_path}/login?error=Please+log+in+to+access+this+page",
                        status_code=303,
                    )

                try:
                    is_valid_session = (
                        await self.admin_instance.session_manager.validate_session(
                            db=db, session_id=session_id, update_activity=True
                        )
                    )
                    if not is_valid_session:
                        logger.debug("Invalid session")
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=Session+expired",
                            status_code=303,
                        )

                    # Retrieve user_id from session data
                    session_data = (
                        await self.admin_instance.session_manager.get_session_metadata(
                            db, session_id
                        )
                    )
                    if not session_data or "user_id" not in session_data:
                        logger.debug("User ID not found in session data")
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=Session+corrupted",  # Or some other error
                            status_code=303,
                        )

                    user_id = session_data["user_id"]
                    user = await self.admin_instance.db_config.crud_users.get(
                        db=db, id=user_id
                    )

                    if not user:
                        logger.debug("User not found for session")
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=User+not+found",
                            status_code=303,
                        )

                    request.state.user = user

                    await self.admin_instance.session_manager.cleanup_expired_sessions(
                        db
                    )

                    response = await call_next(request)
                    return response

                except Exception as e:
                    logger.error(f"Auth error: {str(e)}", exc_info=True)
                    if (
                        request.url.path.endswith("/crud")
                        or "/crud/" in request.url.path
                    ):
                        raise
                    return RedirectResponse(
                        url=f"/{self.admin_instance.mount_path}/login?error=Authentication+error",
                        status_code=303,
                    )

            except Exception as e:
                logger.error(f"Middleware error: {str(e)}", exc_info=True)
                raise

        return await call_next(request)
