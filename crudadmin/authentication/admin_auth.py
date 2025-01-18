from typing import Union, Any, Annotated, Optional
from datetime import datetime
import logging

from jose import jwt, JWTError
from sqlalchemy.ext.asyncio.session import AsyncSession
from fastapi import Depends, Cookie, Request
from fastapi.security import OAuth2PasswordBearer

from ..core.exceptions import UnauthorizedException, ForbiddenException

from ..authentication.security import SecurityUtils
from ..token.schemas import (
    AdminTokenData,
    AdminTokenBlacklistCreate,
    AdminTokenBlacklistUpdate,
)
from ..core.db import DatabaseConfig
from ..admin_user.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserUpdateInternal,
)
from ..session.schemas import AdminSessionCreate, AdminSessionUpdate

logger = logging.getLogger(__name__)

class AdminAuthentication:
    def __init__(
        self,
        database_config: DatabaseConfig,
        security_utils: SecurityUtils,
        oauth2_scheme: OAuth2PasswordBearer,
    ) -> None:
        self.db_config = database_config
        self.admin_user = self.db_config.AdminUser
        self.security_utils = security_utils
        self.oauth2_scheme = oauth2_scheme
        self.auth_models = {}

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


    async def create_user_table(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(self.admin_user.metadata.create_all)

    async def async_get_db(self) -> AsyncSession:
        async_session = self.db_config.session

        async with async_session() as db:
            yield db
            await db.commit()

    async def verify_token(self, token: str, db: AsyncSession) -> AdminTokenData | None:
        """Verify a JWT token and return TokenData if valid."""
        try:
            logger.info("Checking if token is blacklisted")
            is_blacklisted = await self.db_config.crud_token_blacklist.exists(
                db, token=token
            )
            if is_blacklisted:
                logger.warning("Token is blacklisted")
                return None

            try:
                logger.info("Decoding JWT token")
                payload = jwt.decode(
                    token,
                    self.security_utils.SECRET_KEY,
                    algorithms=[self.security_utils.ALGORITHM],
                )
                username_or_email: str = payload.get("sub")
                if username_or_email is None:
                    logger.warning("No username/email found in token")
                    return None
                    
                logger.info("Token verified successfully")
                return AdminTokenData(username_or_email=username_or_email)

            except JWTError as e:
                logger.error(f"JWT decode error: {str(e)}")
                return None

        except Exception as e:
            logger.error(f"Token verification error: {str(e)}", exc_info=True)
            return None

    async def blacklist_token(
        self,
        token: str,
        db: AsyncSession,
    ) -> None:
        """Blacklist a token."""
        try:
            payload = jwt.decode(
                token,
                self.security_utils.SECRET_KEY,
                algorithms=[self.security_utils.ALGORITHM],
            )
            expires_at = datetime.fromtimestamp(payload.get("exp"))
            await self.security_utils.crud_token_blacklist.create(
                db,
                object=AdminTokenBlacklistCreate(
                    **{"token": token, "expires_at": expires_at}
                ),
            )
        except JWTError:
            pass

    async def get_token_from_cookie(
        self,
        request: Request,
        access_token: Optional[str] = Cookie(None)
    ) -> Optional[str]:
        """Get token from cookie."""
        if access_token and access_token.startswith('Bearer '):
            return access_token.split(' ')[1]
        return None

    def get_current_user(self):
        async def get_current_user_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            access_token: Optional[str] = Cookie(None)
        ) -> Union[dict[str, Any], None]:
            if not access_token:
                raise UnauthorizedException("Not authenticated")
                
            token = None
            if access_token.startswith('Bearer '):
                token = access_token.split(' ')[1]
            else:
                token = access_token
                
            token_data = await self.verify_token(token, db)
            if token_data is None:
                raise UnauthorizedException("Could not validate credentials")

            if "@" in token_data.username_or_email:
                user: dict | None = await self.db_config.crud_users.get(
                    db=db, email=token_data.username_or_email
                )
            else:
                user = await self.db_config.crud_users.get(
                    db=db, username=token_data.username_or_email
                )

            if user:
                return user

            raise UnauthorizedException("User not authenticated")

        return get_current_user_inner

    async def get_current_superuser(
        current_user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        if not current_user["is_superuser"]:
            raise ForbiddenException("You do not have enough privileges.")

        return current_user

    async def create_first_admin(self):
        async def create_first_admin_inner(
            name: str,
            username: str,
            email: str,
            password: str,
            db: Annotated[AsyncSession, Depends(self.async_get_db)],
        ):
            exists = await self.db_config.crud_users.exists(
                db, username=username, email=email
            )
            if exists:
                return None

            hashed_password = password

            admin_data = AdminUserCreate(
                name=name,
                username=username,
                email=email,
                hashed_password=hashed_password,
                is_superuser=True,
            )
            await self.db_config.crud_users.create(db=db, obj_in=admin_data)

        return create_first_admin_inner
