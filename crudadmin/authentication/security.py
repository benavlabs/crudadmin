from typing import Union, Literal, Dict, Any
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from ..db.database_config import DatabaseConfig


class SecurityUtils:
    def __init__(
        self,
        SECRET_KEY: str,
        ALGORITHM: str,
        ACCESS_TOKEN_EXPIRE_MINUTES: int,
        REFRESH_TOKEN_EXPIRE_DAYS: int,
        db_config: DatabaseConfig,
    ) -> None:
        self.SECRET_KEY = SECRET_KEY
        self.ALGORITHM = ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
        self.REFRESH_TOKEN_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS
        self.db_config = db_config
        self.crud_users = db_config.crud_users
        self.crud_token_blacklist = db_config.crud_token_blacklist

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    def get_password_hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    async def authenticate_user(
        self, username_or_email: str, password: str, db: AsyncSession
    ) -> Union[Dict[str, Any], Literal[False]]:
        async for admin_session in self.db_config.get_admin_db():
            try:
                if "@" in username_or_email:
                    db_user: dict | None = await self.crud_users.get(
                        db=admin_session, email=username_or_email
                    )
                else:
                    db_user = await self.crud_users.get(
                        db=admin_session, username=username_or_email
                    )

                if not db_user:
                    return False

                if not await self.verify_password(password, db_user["hashed_password"]):
                    return False

                return db_user
            except Exception as e:
                return False

    async def create_access_token(
        self, data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt: str = jwt.encode(
            to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM
        )
        return encoded_jwt

    async def create_refresh_token(
        self, data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=self.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire})
        encoded_jwt: str = jwt.encode(
            to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM
        )
        return encoded_jwt
