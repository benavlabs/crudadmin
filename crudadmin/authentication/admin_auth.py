from typing import Union, Any, Annotated
from datetime import datetime

from jose import jwt, JWTError
from sqlalchemy.ext.asyncio.session import AsyncSession
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from ..exceptions.http_exceptions import UnauthorizedException, ForbiddenException

from ..authentication.security import SecurityUtils
from ..schemas.admin_token import (
    AdminTokenData,
    AdminTokenBlacklistCreate,
    AdminTokenBlacklistUpdate,
)
from ..db.database_config import DatabaseConfig
from ..schemas.admin_user import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserUpdateInternal,
)


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

    async def create_user_table(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(self.admin_user.metadata.create_all)

    async def async_get_db(self) -> AsyncSession:
        async_session = self.db_config.session

        async with async_session() as db:
            yield db
            await db.commit()

    async def verify_token(self, token: str, db: AsyncSession) -> AdminTokenData | None:
        """
        Verify a JWT token and return TokenData if valid.

        Parameters
        ----------
        token: str
            The JWT token to be verified.
        db: AsyncSession
            Database session for performing database operations.

        Returns
        -------
        TokenData | None
            TokenData instance if the token is valid, None otherwise.
        """
        is_blacklisted = await self.db_config.crud_token_blacklist.exists(
            db, token=token
        )
        if is_blacklisted:
            return None

        try:
            payload = jwt.decode(
                token,
                self.security_utils.SECRET_KEY,
                algorithms=[self.security_utils.ALGORITHM],
            )
            username_or_email: str = payload.get("sub")
            if username_or_email is None:
                return None
            return AdminTokenData(username_or_email=username_or_email)

        except JWTError:
            return None

    async def blacklist_token(self):
        async def blacklist_token_inner(
            token: Annotated[str, Depends(self.oauth2_scheme)],
            db: Annotated[AsyncSession, Depends(self.async_get_db)],
        ) -> None:
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

        return blacklist_token_inner

    async def get_current_user(self):
        async def get_current_user_inner(
            token: Annotated[str, Depends(self.oauth2_scheme)],
            db: Annotated[AsyncSession, Depends(self.async_get_db)],
        ) -> Union[dict[str, Any], None]:
            token_data = await self.verify_token(token, db)
            if token_data is None:
                raise UnauthorizedException("User not authenticated.")

            if "@" in token_data.username_or_email:
                user: dict | None = await self.db_config.crud_users.get(
                    db=db, email=token_data.username_or_email, is_deleted=False
                )
            else:
                user = await self.db_config.crud_users.get(
                    db=db, username=token_data.username_or_email, is_deleted=False
                )

            if user:
                return user

            raise UnauthorizedException("User not authenticated.")

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
