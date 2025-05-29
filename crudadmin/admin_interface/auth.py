import logging
from typing import Optional

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
from ..session.schemas import AdminSessionCreate, AdminSessionUpdate

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

        self.auth_models[self.db_config.AdminUser.__name__] = {
            "model": self.db_config.AdminUser,
            "crud": self.db_config.crud_users,
            "create_schema": AdminUserCreate,
            "update_schema": AdminUserUpdate,
            "update_internal_schema": AdminUserUpdateInternal,
            "delete_schema": None,
        }

        self.auth_models[self.db_config.AdminSession.__name__] = {
            "model": self.db_config.AdminSession,
            "crud": self.db_config.crud_sessions,
            "create_schema": AdminSessionCreate,
            "update_schema": AdminSessionUpdate,
            "update_internal_schema": AdminSessionUpdate,
            "delete_schema": None,
        }

    def get_current_user(self):
        async def get_current_user_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            session_id: Optional[str] = Cookie(None),
        ) -> Optional[AdminUserRead]:
            logger.debug(f"Starting get_current_user with session_id: {session_id}")

            if not session_id:
                logger.debug("No session_id found")
                raise UnauthorizedException("Not authenticated")

            is_valid_session = await self.session_manager.validate_session(
                db, session_id
            )
            if not is_valid_session:
                logger.debug("Session validation failed")
                raise UnauthorizedException("Could not validate credentials")

            session_data = await self.session_manager.get_session_metadata(
                db, session_id
            )
            if not session_data or "user_id" not in session_data:
                logger.debug("User ID not found in session data")
                raise UnauthorizedException("Could not validate credentials")

            user_id = session_data["user_id"]
            user = await self.db_config.crud_users.get(db=db, id=user_id)

            if user:
                logger.debug("User found")
                if isinstance(user, dict):
                    try:
                        user = AdminUserRead(**user)
                    except Exception as e:
                        raise UnauthorizedException("Invalid user data") from e
                elif not isinstance(user, AdminUserRead):
                    try:
                        user = AdminUserRead.from_orm(user)
                    except Exception as e:
                        raise UnauthorizedException("Invalid user data") from e
                return user

            logger.debug("User not found")
            raise UnauthorizedException("User not authenticated")

        return get_current_user_inner

    async def get_current_superuser(self, current_user: AdminUserRead) -> AdminUserRead:
        """Check if current user is a superuser."""
        if not current_user.is_superuser:
            raise ForbiddenException("You do not have enough privileges.")
        return current_user
