import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from crudadmin import CRUDAdmin

logger = logging.getLogger(__name__)


class AdminAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, admin_instance: "CRUDAdmin"):
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
                access_token = request.cookies.get("access_token")
                session_id = request.cookies.get("session_id")

                logger.debug(
                    f"Found tokens - Access: {bool(access_token)}, Session: {bool(session_id)}"
                )

                if not access_token or not session_id:
                    logger.debug("Missing required tokens")
                    return RedirectResponse(
                        url=f"/{self.admin_instance.mount_path}/login?error=Please+log+in+to+access+this+page",
                        status_code=303,
                    )

                token = (
                    access_token.replace("Bearer ", "")
                    if access_token.startswith("Bearer ")
                    else access_token
                )

                try:
                    token_data = await self.admin_instance.token_service.verify_token(
                        token, db
                    )
                    if not token_data:
                        logger.debug("Token verification failed")
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=Session+expired",
                            status_code=303,
                        )

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

                    if "@" in token_data.username_or_email:
                        user = await self.admin_instance.db_config.crud_users.get(
                            db=db, email=token_data.username_or_email
                        )
                    else:
                        user = await self.admin_instance.db_config.crud_users.get(
                            db=db, username=token_data.username_or_email
                        )

                    if not user:
                        logger.debug("User not found")
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
