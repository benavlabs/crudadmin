import logging
import os
from collections.abc import AsyncGenerator, Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Type,
    TypeVar,
    cast,
)

from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import Table, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from ..admin_user.schemas import (
        AdminUserCreate,
        AdminUserRead,
        AdminUserUpdate,
        AdminUserUpdateInternal,
    )
    from ..session.schemas import (
        AdminSessionCreate,
        AdminSessionUpdate,
    )

logger = logging.getLogger(__name__)


def get_default_db_path() -> str:
    """Get the default database path relative to the current working directory."""
    cwd = os.getcwd()
    data_dir = os.path.join(cwd, "crudadmin_data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "admin.db")


class AdminBase(DeclarativeBase):
    pass


class _EmptySchema(BaseModel):
    """A placeholder schema for FastCRUD when no schema is needed."""

    pass


ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class DatabaseConfig:
    def __init__(
        self,
        base: Type[DeclarativeBase],
        session: AsyncSession,
        admin_db_url: Optional[str] = None,
        admin_db_path: Optional[str] = None,
        admin_user: Optional[Type[DeclarativeBase]] = None,
        admin_session: Optional[Type[DeclarativeBase]] = None,
        admin_event_log: Optional[Type[DeclarativeBase]] = None,
        admin_audit_log: Optional[Type[DeclarativeBase]] = None,
        crud_admin_user: Optional[
            FastCRUD[
                DeclarativeBase,
                "AdminUserCreate",
                "AdminUserUpdate",
                "AdminUserUpdateInternal",
                "_EmptySchema",
                "AdminUserRead",
            ]
        ] = None,
        crud_admin_session: Optional[
            FastCRUD[
                DeclarativeBase,
                "AdminSessionCreate",
                "AdminSessionUpdate",
                "AdminSessionUpdate",
                "_EmptySchema",
                "_EmptySchema",
            ]
        ] = None,
    ) -> None:
        self.base: Type[DeclarativeBase] = base
        self.session: AsyncSession = session

        if admin_db_url is None:
            if admin_db_path is None:
                admin_db_path = get_default_db_path()
            admin_db_url = f"sqlite+aiosqlite:///{admin_db_path}"

        self.admin_engine: AsyncEngine = create_async_engine(admin_db_url)
        self.admin_session: AsyncSession = AsyncSession(
            self.admin_engine, expire_on_commit=False
        )

        async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
            yield self.admin_session
            await self.admin_session.commit()

        self.get_admin_db: Callable[[], AsyncGenerator[AsyncSession, None]] = (
            get_admin_db
        )

        if admin_user is None:
            from ..admin_user.models import create_admin_user

            admin_user = create_admin_user(base)
        self.AdminUser: Type[DeclarativeBase] = admin_user

        if admin_session is None:
            from ..session import create_admin_session_model

            admin_session = create_admin_session_model(base)
        self.AdminSession: Type[DeclarativeBase] = admin_session

        self.AdminEventLog: Optional[Type[DeclarativeBase]] = admin_event_log
        self.AdminAuditLog: Optional[Type[DeclarativeBase]] = admin_audit_log

        if crud_admin_user is None:
            CRUDUser = FastCRUD[
                DeclarativeBase,
                "AdminUserCreate",
                "AdminUserUpdate",
                "AdminUserUpdateInternal",
                "_EmptySchema",
                "AdminUserRead",
            ]
            crud_admin_user = CRUDUser(admin_user)
        assert crud_admin_user is not None
        self.crud_users: FastCRUD[
            DeclarativeBase,
            AdminUserCreate,
            AdminUserUpdate,
            AdminUserUpdateInternal,
            _EmptySchema,
            AdminUserRead,
        ] = crud_admin_user

        if crud_admin_session is None:
            CRUDSession = FastCRUD[
                DeclarativeBase,
                "AdminSessionCreate",
                "AdminSessionUpdate",
                "AdminSessionUpdate",
                "_EmptySchema",
                "_EmptySchema",
            ]
            crud_admin_session = CRUDSession(admin_session)
        assert crud_admin_session is not None
        self.crud_sessions: FastCRUD[
            DeclarativeBase,
            AdminSessionCreate,
            AdminSessionUpdate,
            AdminSessionUpdate,
            _EmptySchema,
            _EmptySchema,
        ] = crud_admin_session

    async def initialize_admin_db(self) -> None:
        """Initialize the admin database with required tables."""
        logger.info("Initializing admin database tables...")
        try:
            async with self.admin_engine.begin() as conn:
                tables_to_create = [
                    self.AdminUser,
                    self.AdminSession,
                ]

                if self.AdminEventLog is not None:
                    tables_to_create.append(self.AdminEventLog)
                if self.AdminAuditLog is not None:
                    tables_to_create.append(self.AdminAuditLog)

                for table in tables_to_create:
                    logger.info(f"Creating table: {table.__tablename__}")
                    table_obj = cast(Table, table.__table__)
                    await conn.run_sync(table_obj.create, checkfirst=True)
            logger.info("Admin database tables created successfully")
        except Exception as e:
            logger.error(
                f"Error creating admin database tables: {str(e)}", exc_info=True
            )
            raise

    def get_admin_session(self) -> AsyncSession:
        """Get a session for the admin database."""
        return self.admin_session

    def get_app_session(self) -> AsyncSession:
        """Get a session for the main application database."""
        return self.session

    def get_primary_key(self, model: Type[DeclarativeBase]) -> Optional[str]:
        """Get the primary key of a SQLAlchemy model."""
        inspector = inspect(model)
        primary_key_columns = inspector.primary_key
        return primary_key_columns[0].name if primary_key_columns else None

    def get_primary_key_info(
        self, model: Type[DeclarativeBase]
    ) -> Optional[Dict[str, Any]]:
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
