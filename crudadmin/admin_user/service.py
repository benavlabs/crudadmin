import logging
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Literal, Optional, Union

import bcrypt
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_user.schemas import AdminUser
from ..core.db import DatabaseConfig
from .schemas import AdminUserCreate

logger = logging.getLogger(__name__)


def _convert_user_to_dict(
    user_obj: Union[Dict[str, Any], AdminUser, Any, None],
) -> Optional[Dict[str, Any]]:
    """
    Helper to unify user record into a dictionary.
    If the object is None, returns None.
    If it's already a dict, returns it.
    If it's an AdminUser model, converts to a dict with relevant fields.
    If it's some unknown type, returns None or convert as needed.
    """
    if user_obj is None:
        return None

    if isinstance(user_obj, dict):
        return user_obj

    if isinstance(user_obj, AdminUser):
        return {
            "id": user_obj.id,
            "username": user_obj.username,
            "hashed_password": user_obj.hashed_password,
        }

    return None


class AdminUserService:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config
        self.crud_users = db_config.crud_users

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash using bcrypt."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    def get_password_hash(self, password: str) -> str:
        """Generate a bcrypt password hash using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    async def authenticate_user(
        self,
        username_or_email: str,
        password: str,
        db: AsyncSession,
    ) -> Union[Dict[str, Any], Literal[False]]:
        """
        Authenticate a user by username or email, returning either a dict with user data or False.
        """
        try:
            logger.debug(f"Attempting to authenticate user: {username_or_email}")

            if "@" in username_or_email:
                db_user_raw = await self.crud_users.get(db=db, email=username_or_email)
            else:
                db_user_raw = await self.crud_users.get(
                    db=db, username=username_or_email
                )

            db_user = _convert_user_to_dict(db_user_raw)
            if not db_user:
                logger.debug("User not found in database")
                return False

            hashed_password = db_user.get("hashed_password")
            if not hashed_password:
                logger.debug("No hashed_password found in user record")
                return False

            logger.debug("Verifying password")
            if not await self.verify_password(password, hashed_password):
                logger.debug("Invalid password")
                return False

            logger.debug("Authentication successful")
            return db_user

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}", exc_info=True)
            return False

    def create_first_admin(self) -> Callable[..., Awaitable[Optional[Dict[str, Any]]]]:
        """
        Returns a function that, when called, creates the first admin user
        if none matching the given username exists. Returns a dict or None.
        """

        async def create_first_admin_inner(
            username: str,
            password: str,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ) -> Optional[Dict[str, Any]]:
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

            created_user = _convert_user_to_dict(created_user_raw)
            logger.debug(f"Created admin user: {created_user}")
            return created_user

        return create_first_admin_inner
