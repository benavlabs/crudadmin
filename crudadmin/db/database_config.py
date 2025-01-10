from typing import Type

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect
from fastcrud import FastCRUD

from ..schemas.admin_user import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserUpdateInternal,
    AdminUser
)
from ..schemas.admin_token import AdminTokenBlacklistCreate, AdminTokenBlacklistUpdate
from ..models.admin_user import create_admin_user
from ..models.admin_token_blacklist import create_admin_token_blacklist

class DatabaseConfig:
    """
    Configuration for database entities related to admin functionality.
    """

    def __init__(
        self,
        base: DeclarativeBase,
        engine: AsyncEngine,
        session: AsyncSession,
        admin_user: Type[DeclarativeBase] | None = None,
        admin_token_blacklist: Type[DeclarativeBase] | None = None,
        crud_admin_user: FastCRUD | None = None,
        crud_admin_token_blacklist: FastCRUD | None = None,
    ) -> None:
        self.base = base
        self.engine = engine
        self.session = session

        if admin_user is None:
            admin_user = create_admin_user(base)

        self.AdminUser = admin_user

        if admin_token_blacklist is None:
            admin_token_blacklist = create_admin_token_blacklist(base)

        self.AdminTokenBlacklist = admin_token_blacklist

        if crud_admin_user is None:
            CRUDUser = FastCRUD[
                admin_user,
                AdminUserCreate,
                AdminUserUpdate,
                AdminUserUpdateInternal,
                None,
                AdminUser
            ]
            crud_admin_user = CRUDUser(admin_user)

        self.crud_users = crud_admin_user

        if crud_admin_token_blacklist is None:
            CRUDAdminTokenBlacklist = FastCRUD[
                admin_token_blacklist,
                AdminTokenBlacklistCreate,
                AdminTokenBlacklistUpdate,
                AdminTokenBlacklistUpdate,
                None,
                AdminUser
            ]
            crud_admin_token_blacklist = CRUDAdminTokenBlacklist(admin_token_blacklist)

        self.crud_token_blacklist = crud_admin_token_blacklist

    def get_primary_key(self, model: DeclarativeBase) -> str:
        """Get the primary key of a SQLAlchemy model."""
        inspector = inspect(model)
        primary_key_columns = inspector.primary_key
        return primary_key_columns[0].name if primary_key_columns else None
