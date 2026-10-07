import logging
from typing import Any, Callable, Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_user.schemas import (
    AdminUserCreate,
    AdminUserRead,
    AdminUserUpdate,
    AdminUserUpdateInternal,
)
from ..admin_user.service import AdminUserService
from ..core.db import DatabaseConfig
from ..core.exceptions import ForbiddenException, UnauthorizedException
from ..session.manager import SessionManager
from ..session.schemas import (
    AdminSessionCreate,
    AdminSessionListItem,
    AdminSessionUpdate,
    AdminSessionUpdateInternal,
)

logger = logging.getLogger(__name__)


class AdminAuthentication:
    def __init__(
        self,
        database_config: DatabaseConfig,
        user_service: AdminUserService,
        session_manager: SessionManager,
        oauth2_scheme: OAuth2PasswordBearer,
        event_integration=None,
    ) -> None:
        self.db_config = database_config
        self.user_service = user_service
        self.oauth2_scheme = oauth2_scheme
        self.auth_models = {}
        self.event_integration = event_integration
        self.session_manager = session_manager
        self._current_user_dependency: Optional[Callable[..., Any]] = None

        self.auth_models[self.db_config.AdminUser.__name__] = {
            "model": self.db_config.AdminUser,
            "crud": self.db_config.crud_users,
            "create_schema": AdminUserCreate,
            "update_schema": AdminUserUpdate,
            "update_internal_schema": AdminUserUpdateInternal,
            "delete_schema": None,
            "select_schema": AdminUserRead,
        }

        self.auth_models[self.db_config.AdminSession.__name__] = {
            "model": self.db_config.AdminSession,
            "crud": self.db_config.crud_sessions,
            "create_schema": AdminSessionCreate,
            "update_schema": AdminSessionUpdate,
            "update_internal_schema": AdminSessionUpdateInternal,
            "delete_schema": None,
            "select_schema": AdminSessionListItem,
        }

    def get_current_user(self) -> Callable[..., Any]:
        """Return the dependency that resolves the session cookie to an admin user.

        The dependency is built once and reused, so routes that declare it at more
        than one level (router and route) share a single callable and FastAPI's
        dependency cache resolves it once per request.
        """
        if self._current_user_dependency is not None:
            return self._current_user_dependency

        async def get_current_user_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            session_id: Optional[str] = Cookie(None),
        ) -> Optional[AdminUserRead]:
            if not session_id:
                raise UnauthorizedException("Not authenticated")

            session_data = await self.session_manager.validate_session(
                session_id=session_id
            )
            if not session_data or not session_data.user_id:
                raise UnauthorizedException("Could not validate credentials")

            user_id = session_data.user_id
            user = await self.db_config.crud_users.get(
                db=db,
                id=user_id,
                schema_to_select=AdminUserRead,
                return_as_model=True,
            )

            if user:
                return user

            logger.debug("User not found")
            raise UnauthorizedException("User not authenticated")

        self._current_user_dependency = get_current_user_inner
        return get_current_user_inner

    async def get_current_superuser(self, current_user: AdminUserRead) -> AdminUserRead:
        """Check if current user is a superuser."""
        if not current_user.is_superuser:
            raise ForbiddenException("You do not have enough privileges.")
        return current_user
