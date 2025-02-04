import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import DatabaseConfig
from .schemas import AdminTokenBlacklistCreate, AdminTokenData

logger = logging.getLogger(__name__)


class TokenService:
    def __init__(
        self,
        db_config: DatabaseConfig,
        SECRET_KEY: str,
        ALGORITHM: str,
        ACCESS_TOKEN_EXPIRE_MINUTES: int,
        REFRESH_TOKEN_EXPIRE_DAYS: int,
    ):
        self.db_config = db_config
        self.SECRET_KEY = SECRET_KEY
        self.ALGORITHM = ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
        self.REFRESH_TOKEN_EXPIRE_DAYS = REFRESH_TOKEN_EXPIRE_DAYS
        self.crud_token_blacklist = db_config.crud_token_blacklist

    async def create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a new access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        to_encode.update({"exp": expire})

        encoded_jwt: str = jwt.encode(
            to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM
        )
        return encoded_jwt

    async def create_refresh_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a new refresh token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=self.REFRESH_TOKEN_EXPIRE_DAYS
            )
        to_encode.update({"exp": expire})

        encoded_jwt: str = jwt.encode(
            to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM
        )
        return encoded_jwt

    async def verify_token(
        self, token: str, db: AsyncSession
    ) -> Optional[AdminTokenData]:
        """Verify a JWT token and return TokenData if valid."""
        try:
            logger.info("Checking if token is blacklisted")
            is_blacklisted = await self.crud_token_blacklist.exists(db, token=token)
            if is_blacklisted:
                logger.warning("Token is blacklisted")
                return None

            try:
                logger.info("Decoding JWT token")
                payload = jwt.decode(
                    token,
                    self.SECRET_KEY,
                    algorithms=[self.ALGORITHM],
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
                self.SECRET_KEY,
                algorithms=[self.ALGORITHM],
            )
            expires_at = datetime.fromtimestamp(payload.get("exp"))
            await self.crud_token_blacklist.create(
                db,
                object=AdminTokenBlacklistCreate(token=token, expires_at=expires_at),
            )
        except JWTError as e:
            logger.error(f"Error blacklisting token: {str(e)}", exc_info=True)
            pass
