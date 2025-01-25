import os
import logging
from typing import Type, Optional, AsyncGenerator, Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect
from fastcrud import FastCRUD

logger = logging.getLogger(__name__)


def get_default_db_path() -> str:
    """Get the default database path relative to the current working directory."""
    cwd = os.getcwd()
    data_dir = os.path.join(cwd, "crudadmin_data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "admin.db")


class AdminBase(DeclarativeBase):
    pass


class DatabaseConfig:
    def __init__(
        self,
        base: DeclarativeBase,
        session: AsyncSession,
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        admin_user: Optional[Type[DeclarativeBase]] = None,
        admin_token_blacklist: Optional[Type[DeclarativeBase]] = None,
        admin_session: Optional[Type[DeclarativeBase]] = None,
        admin_event_log: Optional[Type[DeclarativeBase]] = None,
        admin_audit_log: Optional[Type[DeclarativeBase]] = None,
        crud_admin_user: Optional[FastCRUD] = None,
        crud_admin_token_blacklist: Optional[FastCRUD] = None,
        crud_admin_session: Optional[FastCRUD] = None,
    ) -> None:
        self.base = base
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
            from ..admin_user.models import create_admin_user

            admin_user = create_admin_user(base)
        self.AdminUser = admin_user

        if admin_token_blacklist is None:
            from ..admin_token.models import create_admin_token_blacklist

            admin_token_blacklist = create_admin_token_blacklist(base)
        self.AdminTokenBlacklist = admin_token_blacklist

        if admin_session is None:
            from ..session import create_admin_session_model

            admin_session = create_admin_session_model(base)
        self.AdminSession = admin_session

        self.AdminEventLog = admin_event_log
        self.AdminAuditLog = admin_audit_log

        if crud_admin_user is None:
            from ..admin_user.schemas import (
                AdminUserCreate,
                AdminUserUpdate,
                AdminUserUpdateInternal,
                AdminUser,
            )

            CRUDUser = FastCRUD[
                admin_user,
                AdminUserCreate,
                AdminUserUpdate,
                AdminUserUpdateInternal,
                None,
                AdminUser,
            ]
            crud_admin_user = CRUDUser(admin_user)
        self.crud_users = crud_admin_user

        if crud_admin_token_blacklist is None:
            from ..admin_token.schemas import (
                AdminTokenBlacklistCreate,
                AdminTokenBlacklistUpdate,
                AdminTokenBlacklistBase,
            )

            CRUDAdminTokenBlacklist = FastCRUD[
                admin_token_blacklist,
                AdminTokenBlacklistCreate,
                AdminTokenBlacklistUpdate,
                AdminTokenBlacklistUpdate,
                None,
                AdminTokenBlacklistBase,
            ]
            crud_admin_token_blacklist = CRUDAdminTokenBlacklist(admin_token_blacklist)
        self.crud_token_blacklist = crud_admin_token_blacklist

        if crud_admin_session is None:
            from ..session import AdminSessionCreate, AdminSessionUpdate

            CRUDSession = FastCRUD[
                admin_session,
                AdminSessionCreate,
                AdminSessionUpdate,
                AdminSessionUpdate,
                None,
                None,
            ]
            crud_admin_session = CRUDSession(admin_session)
        self.crud_sessions = crud_admin_session

    async def initialize_admin_db(self):
        """Initialize the admin database with required tables."""
        logger.info("Initializing admin database tables...")
        try:
            async with self.admin_engine.begin() as conn:
                for table in [
                    self.AdminUser,
                    self.AdminTokenBlacklist,
                    self.AdminSession,
                ]:
                    logger.info(f"Creating table: {table.__tablename__}")
                    await conn.run_sync(
                        lambda metadata: table.__table__.create(
                            metadata.bind, checkfirst=True
                        )
                    )
                logger.info("Admin database tables created successfully")
        except Exception as e:
            logger.error(
                f"Error creating admin database tables: {str(e)}", exc_info=True
            )
            raise

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

    def get_primary_key_info(self, model: DeclarativeBase) -> Dict[str, Any]:
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
            "type_name": python_type.__name__,
        }
