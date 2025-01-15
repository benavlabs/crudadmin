import os
from typing import Type, Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import inspect
from fastcrud import FastCRUD

from ..schemas.admin_user import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserUpdateInternal,
    AdminUser
)
from ..schemas.admin_token import AdminTokenBlacklistCreate, AdminTokenBlacklistUpdate, AdminTokenBlacklistBase
from ..models.admin_user import create_admin_user
from ..models.admin_token_blacklist import create_admin_token_blacklist


def get_default_db_path() -> str:
    """Get the default database path relative to the current working directory."""
    cwd = os.getcwd()
    
    data_dir = os.path.join(cwd, 'crudadmin_data')
    os.makedirs(data_dir, exist_ok=True)
    
    return os.path.join(data_dir, 'admin.db')


class DatabaseConfig:
    """
    Configuration for database entities related to admin functionality.
    Supports separate database for admin authentication by default.
    """

    def __init__(
        self,
        base: DeclarativeBase,
        engine: AsyncEngine,
        session: AsyncSession,
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        admin_user: Optional[Type[DeclarativeBase]] = None,
        admin_token_blacklist: Optional[Type[DeclarativeBase]] = None,
        crud_admin_user: Optional[FastCRUD] = None,
        crud_admin_token_blacklist: Optional[FastCRUD] = None,
    ) -> None:
        """
        Initialize database configuration.

        Parameters
        ----------
        base : DeclarativeBase
            SQLAlchemy declarative base
        engine : AsyncEngine
            Main application database engine
        session : AsyncSession
            Main application database session
        admin_db_url : Optional[str]
            Complete database URL for admin database. Takes precedence over admin_db_path.
        admin_db_path : Optional[str]
            Path where SQLite database should be stored. Only used if admin_db_url is None.
        admin_user : Optional[Type[DeclarativeBase]]
            Custom admin user model
        admin_token_blacklist : Optional[Type[DeclarativeBase]]
            Custom token blacklist model
        crud_admin_user : Optional[FastCRUD]
            Custom CRUD operations for admin user
        crud_admin_token_blacklist : Optional[FastCRUD]
            Custom CRUD operations for token blacklist
        """
        self.base = base
        self.engine = engine
        self.session = session

        if admin_db_url is None:
            if admin_db_path is None:
                admin_db_path = get_default_db_path()
            admin_db_url = f"sqlite+aiosqlite:///{admin_db_path}"

        self.admin_engine = create_async_engine(admin_db_url)
        self.admin_session = AsyncSession(self.admin_engine, expire_on_commit=False)

        async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
            yield self.admin_session
            await self.admin_session.commit()

        self.get_admin_db = get_admin_db

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
                AdminTokenBlacklistBase
            ]
            crud_admin_token_blacklist = CRUDAdminTokenBlacklist(admin_token_blacklist)
        self.crud_token_blacklist = crud_admin_token_blacklist

    async def initialize_admin_db(self):
        """Initialize the admin database with required tables."""
        async with self.admin_engine.begin() as conn:
            await conn.run_sync(self.base.metadata.create_all)

    def get_admin_session(self) -> AsyncSession:
        """Get a session for the admin database."""
        return self.admin_session()

    def get_app_session(self) -> AsyncSession:
        """Get a session for the main application database."""
        return self.session()

    def get_primary_key(self, model: DeclarativeBase) -> str:
        """Get the primary key of a SQLAlchemy model."""
        inspector = inspect(model)
        primary_key_columns = inspector.primary_key
        return primary_key_columns[0].name if primary_key_columns else None
    
    def get_primary_key_info(self, model: DeclarativeBase) -> dict:
        """Get the primary key information of a SQLAlchemy model."""
        inspector = inspect(model)
        primary_key_columns = inspector.primary_key
        if not primary_key_columns:
            return None
        
        pk_column = primary_key_columns[0]
        python_type = pk_column.type.python_type
        
        return {
            "name": pk_column.name,
            "type": python_type,
            "type_name": python_type.__name__
        }
