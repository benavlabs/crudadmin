"""
Authentication utilities for password hashing and verification.

This module provides shared authentication functions that can be used
across the crudadmin application, including password hashing, verification,
and user authentication logic.
"""

import logging
from typing import Any, Optional

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash using bcrypt.

    Args:
        plain_password: The plaintext password to verify
        hashed_password: The bcrypt hashed password to check against

    Returns:
        True if the password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    Generate a bcrypt password hash.

    Args:
        password: The plaintext password to hash

    Returns:
        The bcrypt hashed password as a string
    """
    try:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise


def convert_user_to_dict(user_obj: Any) -> Optional[dict]:
    """
    Helper to unify user record into a dictionary.

    This function handles different user object types (dict, SQLAlchemy models, etc.)
    and converts them to a consistent dictionary format.

    Args:
        user_obj: User object of various types

    Returns:
        Dictionary representation of user or None if conversion fails
    """
    if user_obj is None:
        return None

    if isinstance(user_obj, dict):
        return user_obj

    if hasattr(user_obj, "__dict__"):
        try:
            user_dict = {}

            common_attrs = [
                "id",
                "username",
                "email",
                "hashed_password",
                "is_active",
                "is_superuser",
                "created_at",
                "updated_at",
            ]

            for attr in common_attrs:
                if hasattr(user_obj, attr):
                    user_dict[attr] = getattr(user_obj, attr)

            return user_dict if user_dict else None

        except Exception as e:
            logger.error(f"Error converting user object to dict: {str(e)}")
            return None

    return None


async def authenticate_user_by_credentials(
    username_or_email: str,
    password: str,
    db: AsyncSession,
    crud_users: Any,
) -> Optional[dict[str, Any]]:
    """
    Authenticate a user by username or email and password.

    This is a shared authentication function that can be used across
    different parts of the application.

    Args:
        username_or_email: The username or email to authenticate with
        password: The plaintext password
        db: Database session
        crud_users: CRUD operations instance for users

    Returns:
        User data dictionary if authenticated, None otherwise
    """
    try:
        logger.debug(f"Attempting to authenticate user: {username_or_email}")

        if "@" in username_or_email:
            db_user_raw = await crud_users.get(db=db, email=username_or_email)
        else:
            db_user_raw = await crud_users.get(db=db, username=username_or_email)

        db_user = convert_user_to_dict(db_user_raw)
        if not db_user:
            logger.debug("User not found in database")
            return None

        hashed_password = db_user.get("hashed_password")
        if not hashed_password:
            logger.debug("No hashed_password found in user record")
            return None

        logger.debug("Verifying password")
        if not await verify_password(password, hashed_password):
            logger.debug("Invalid password")
            return None

        logger.debug("Authentication successful")
        return db_user

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        return None
