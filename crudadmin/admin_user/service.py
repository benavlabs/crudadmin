from typing import Union, Any, Annotated, Dict, Literal
import logging
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt

from ..core.db import DatabaseConfig
from .schemas import AdminUserCreate

logger = logging.getLogger(__name__)


class AdminUserService:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config
        self.crud_users = db_config.crud_users

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    async def authenticate_user(
        self, username_or_email: str, password: str, db: AsyncSession
    ) -> Union[Dict[str, Any], Literal[False]]:
        """Authenticate a user by username/email and password."""
        try:
            logger.debug(f"Attempting to authenticate user: {username_or_email}")

            if "@" in username_or_email:
                logger.debug("Searching by email")
                db_user: dict | None = await self.crud_users.get(
                    db=db, email=username_or_email
                )
            else:
                logger.debug("Searching by username")
                db_user = await self.crud_users.get(db=db, username=username_or_email)

            if not db_user:
                logger.debug("User not found in database")
                return False

            logger.debug("Verifying password")
            if not await self.verify_password(password, db_user["hashed_password"]):
                logger.debug("Invalid password")
                return False

            logger.debug("Authentication successful")
            return db_user
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            return False

    async def create_first_admin(self):
        async def create_first_admin_inner(
            name: str,
            username: str,
            email: str,
            password: str,
            db: Annotated[AsyncSession, Depends(self.db_config.get_admin_db)],
        ):
            exists = await self.crud_users.exists(db, username=username, email=email)
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
            await self.crud_users.create(db=db, obj_in=admin_data)

        return create_first_admin_inner
