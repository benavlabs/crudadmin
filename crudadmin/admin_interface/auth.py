from typing import Union, Any, Optional, Dict
import logging
from fastapi import Depends, Cookie, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import UnauthorizedException, ForbiddenException
from ..admin_user.service import AdminUserService
from ..admin_token.service import TokenService
from ..admin_user.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserUpdateInternal,
)
from ..admin_token.schemas import AdminTokenBlacklistCreate, AdminTokenBlacklistUpdate
from ..session.schemas import AdminSessionCreate, AdminSessionUpdate
from ..core.db import DatabaseConfig

logger = logging.getLogger(__name__)


class AdminAuthentication:
    def __init__(
        self,
        database_config: DatabaseConfig,
        user_service: AdminUserService,
        token_service: TokenService,
        oauth2_scheme: OAuth2PasswordBearer,
        event_integration=None,
    ) -> None:
        self.db_config = database_config
        self.user_service = user_service
        self.token_service = token_service
        self.oauth2_scheme = oauth2_scheme
        self.auth_models = {}
        self.event_integration = event_integration

        self.auth_models[self.db_config.AdminUser.__name__] = {
            "model": self.db_config.AdminUser,
            "crud": self.db_config.crud_users,
            "create_schema": AdminUserCreate,
            "update_schema": AdminUserUpdate,
            "update_internal_schema": AdminUserUpdateInternal,
            "delete_schema": None,
        }

        self.auth_models[self.db_config.AdminTokenBlacklist.__name__] = {
            "model": self.db_config.AdminTokenBlacklist,
            "crud": self.db_config.crud_token_blacklist,
            "create_schema": AdminTokenBlacklistCreate,
            "update_schema": AdminTokenBlacklistUpdate,
            "update_internal_schema": AdminTokenBlacklistUpdate,
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
            access_token: Optional[str] = Cookie(None),
        ) -> Union[Dict[str, Any], None]:
            logger.debug(f"Starting get_current_user with token: {access_token}")

            if not access_token:
                logger.debug("No access token found")
                raise UnauthorizedException("Not authenticated")

            token = None
            if access_token.startswith("Bearer "):
                token = access_token.split(" ")[1]
                logger.debug("Extracted token from Bearer")
            else:
                token = access_token
                logger.debug("Using token as-is")

            logger.debug("Verifying token")
            token_data = await self.token_service.verify_token(token, db)
            if token_data is None:
                logger.debug("Token verification failed")
                raise UnauthorizedException("Could not validate credentials")

            logger.debug(f"Token data: {token_data}")

            if "@" in token_data.username_or_email:
                logger.debug("Looking up user by email")
                user = await self.db_config.crud_users.get(
                    db=db, email=token_data.username_or_email
                )
            else:
                logger.debug("Looking up user by username")
                user = await self.db_config.crud_users.get(
                    db=db, username=token_data.username_or_email
                )

            if user:
                logger.debug("User found")
                return user

            logger.debug("User not found")
            raise UnauthorizedException("User not authenticated")

        return get_current_user_inner

    async def get_current_superuser(
        self, current_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if current user is a superuser."""
        if not current_user.get("is_superuser"):
            raise ForbiddenException("You do not have enough privileges.")
        return current_user
