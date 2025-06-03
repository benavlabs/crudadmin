import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import (
    authenticate_user_by_credentials,
    convert_user_to_dict,
    get_password_hash,
    verify_password,
)
from ..core.db import DatabaseConfig
from .schemas import AdminUserCreate

logger = logging.getLogger(__name__)


class AdminUserService:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config
        self.crud_users = db_config.crud_users

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash using bcrypt."""
        return await verify_password(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate a bcrypt password hash using bcrypt."""
        return get_password_hash(password)

    async def authenticate_user(
        self,
        username_or_email: str,
        password: str,
        db: AsyncSession,
    ) -> Any:
        """
        Authenticate a user by username or email, returning either a dict with user data or False.
        """
        result = await authenticate_user_by_credentials(
            username_or_email=username_or_email,
            password=password,
            db=db,
            crud_users=self.crud_users,
        )

        return result if result is not None else False

    def create_first_admin(self) -> Callable[..., Awaitable[Optional[dict]]]:
        """
        Returns a function that, when called, creates the first admin user
        if none matching the given username exists. Returns a dict or None.
        """

        async def create_first_admin_inner(
            username: str,
            password: str,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> Optional[dict]:
            """
            Creates the first admin user if it doesn't already exist.
            Adjust fields to match your actual AdminUserCreate schema.
            """
            exists = await self.crud_users.exists(db, username=username)
            if exists:
                logger.debug(f"Admin user '{username}' already exists.")
                return None

            hashed_password = self.get_password_hash(password)

            admin_data = AdminUserCreate(
                username=username,
                password=hashed_password,
            )

            created_user_raw = await self.crud_users.create(db=db, object=admin_data)

            created_user = convert_user_to_dict(created_user_raw)
            logger.debug(f"Created admin user: {created_user}")
            return created_user

        return create_first_admin_inner
