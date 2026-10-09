import logging
import os
import warnings
from collections.abc import AsyncGenerator, Callable
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    cast,
)
from uuid import UUID

from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import Table, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from ..admin_user.schemas import (
        AdminUserCreate,
        AdminUserRead,
        AdminUserUpdate,
        AdminUserUpdateInternal,
    )

logger = logging.getLogger(__name__)


def get_default_db_path() -> str:
    """Get the default database path relative to the current working directory."""
    cwd = os.getcwd()
    data_dir = os.path.join(cwd, "crudadmin_data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "admin.db")


def get_primary_key_name(model: type[DeclarativeBase]) -> str:
    """Return the name of the model's first primary key column.

    Used as the filter key for FastCRUD lookups so models whose primary key is
    not named ``id`` (e.g. ``job_id``) work in get/update/delete operations.

    Raises:
        ValueError: If the model has no primary key.
    """
    primary_key_columns = inspect(model).primary_key
    if not primary_key_columns:
        raise ValueError(
            f"Model {model.__name__} has no primary key; CRUDAdmin requires "
            "a primary key to manage a model."
        )
    return str(primary_key_columns[0].name)


def convert_id_to_pk_type(
    id_value: int | str | None,
    db_config: "DatabaseConfig",
    model: type[DeclarativeBase],
) -> int | str | float | UUID | None:
    """Convert the ID value to the appropriate type based on the model's primary key type."""
    if id_value is None:
        return None

    primary_key_info = db_config.get_primary_key_info(model)
    if not primary_key_info:
        return id_value

    pk_type = primary_key_info.get("type")

    if pk_type is int:
        return int(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is str:
        return str(id_value)
    elif pk_type is float:
        return float(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is UUID:
        return UUID(str(id_value))
    else:
        return str(id_value)


ADMIN_USER_COLUMNS_ADDED_IN_0_6 = {
    "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
    "token_version": "INTEGER NOT NULL DEFAULT 0",
}


def new_admin_base() -> type[DeclarativeBase]:
    """A declarative base of its own, so each admin's tables get a separate registry.

    Two admins on one base would both define ``admin_user`` on the same metadata,
    which SQLAlchemy refuses; a base per admin lets several run in one process.
    """

    class AdminBase(DeclarativeBase):
        pass

    return AdminBase


class _EmptySchema(BaseModel):
    """A placeholder schema for FastCRUD when no schema is needed."""

    pass


ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class DatabaseConfig:
    def __init__(
        self,
        base: type[DeclarativeBase],
        session: Callable[[], AsyncGenerator[AsyncSession, None]],
        admin_db_url: str | None = None,
        admin_db_path: str | None = None,
        admin_user: type[DeclarativeBase] | None = None,
        admin_session: type[DeclarativeBase] | None = None,
        admin_event_log: type[DeclarativeBase] | None = None,
        admin_audit_log: type[DeclarativeBase] | None = None,
        crud_admin_user: FastCRUD[
            DeclarativeBase,
            "AdminUserCreate",
            "AdminUserUpdate",
            "AdminUserUpdateInternal",
            "_EmptySchema",
            "AdminUserRead",
        ]
        | None = None,
        crud_admin_session: Any = None,
    ) -> None:
        if admin_session is not None or crud_admin_session is not None:
            warnings.warn(
                "admin_session and crud_admin_session are ignored: sessions are kept "
                "by crudauth since crudadmin 0.6, not in an admin_session table.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.base: type[DeclarativeBase] = base
        self.session: Callable[[], AsyncGenerator[AsyncSession, None]] = session

        if admin_db_url is None:
            if admin_db_path is None:
                admin_db_path = get_default_db_path()
            admin_db_url = f"sqlite+aiosqlite:///{admin_db_path}"

        self.admin_engine: AsyncEngine = create_async_engine(admin_db_url)
        self.admin_session: AsyncSession = AsyncSession(
            self.admin_engine, expire_on_commit=False
        )
        self.admin_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.admin_engine, expire_on_commit=False
        )

        async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
            async with self.admin_session_maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        self.get_admin_db: Callable[[], AsyncGenerator[AsyncSession, None]] = (
            get_admin_db
        )

        if admin_user is None:
            from ..admin_user.models import create_admin_user

            admin_user = create_admin_user(base)
        self.AdminUser: type[DeclarativeBase] = admin_user

        self.AdminEventLog: type[DeclarativeBase] | None = admin_event_log
        self.AdminAuditLog: type[DeclarativeBase] | None = admin_audit_log

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

    async def initialize_admin_db(self) -> None:
        """Create the admin tables, and add columns that older versions lacked.

        Tables are created with ``checkfirst``. On an ``admin_user`` table made by
        crudadmin 0.5 or earlier, the ``is_active`` and ``token_version`` columns are
        added in place, so an existing admin database keeps working without a
        manual migration.
        """
        logger.info("Initializing admin database tables...")
        async with self.admin_engine.begin() as conn:
            tables_to_create = [self.AdminUser]

            if self.AdminEventLog is not None:
                tables_to_create.append(self.AdminEventLog)
            if self.AdminAuditLog is not None:
                tables_to_create.append(self.AdminAuditLog)

            for table in tables_to_create:
                logger.info("Creating table: %s", table.__tablename__)
                table_obj = cast(Table, table.__table__)
                await conn.run_sync(table_obj.create, checkfirst=True)

        await self._add_missing_admin_user_columns()
        await self._widen_event_session_ids()
        logger.info("Admin database tables created successfully")

    async def _add_missing_admin_user_columns(self) -> None:
        """Add the columns crudadmin 0.6 introduced to an older ``admin_user`` table.

        Each column is added in a transaction of its own. Several workers starting
        at once may all find a column missing; the ones whose ``ALTER TABLE`` loses
        the race get a duplicate-column error, see that the column now exists, and
        carry on.
        """
        table = cast(Table, self.AdminUser.__table__)
        for name, definition in ADMIN_USER_COLUMNS_ADDED_IN_0_6.items():
            if name not in table.columns:
                continue
            if name in await self._admin_user_column_names():
                continue
            logger.info("Adding column %s.%s", table.name, name)
            try:
                async with self.admin_engine.begin() as conn:
                    await conn.execute(
                        self._add_column_statement(table, name, definition)
                    )
            except DBAPIError:
                if name not in await self._admin_user_column_names():
                    raise
                logger.info(
                    "Column %s.%s was added by another worker", table.name, name
                )

    async def _widen_event_session_ids(self) -> None:
        """Widen ``admin_event_log.session_id`` from the 36 characters of 0.6.

        crudauth's session handles are 64 characters, so on a database that
        enforces lengths every event insert failed. SQLite doesn't enforce them and
        is left alone. Widening an already wide column changes nothing, so several
        workers may run it at once.
        """
        if self.AdminEventLog is None:
            return
        dialect = self.admin_engine.dialect.name
        if dialect not in ("postgresql", "mysql", "mariadb"):
            return
        table = cast(Table, self.AdminEventLog.__table__)
        wanted: int | None = getattr(table.c.session_id.type, "length", None)
        current = await self._column_length(table.name, "session_id")
        if current is None or wanted is None or current >= wanted:
            return
        preparer = self.admin_engine.dialect.identifier_preparer
        column = preparer.quote("session_id")
        if dialect == "postgresql":
            change = f"ALTER COLUMN {column} TYPE VARCHAR({wanted})"
        else:
            change = f"MODIFY {column} VARCHAR({wanted}) NOT NULL"
        logger.info("Widening %s.session_id to %s characters", table.name, wanted)
        async with self.admin_engine.begin() as conn:
            await conn.execute(
                text(f"ALTER TABLE {preparer.format_table(table)} {change}")
            )

    async def _column_length(self, table_name: str, column_name: str) -> int | None:
        async with self.admin_engine.connect() as conn:
            columns = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns(table_name)
            )
        for column in columns:
            if column["name"] == column_name:
                return getattr(column["type"], "length", None)
        return None

    async def _admin_user_column_names(self) -> set[str]:
        table_name = cast(Table, self.AdminUser.__table__).name
        async with self.admin_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: {
                    column["name"]
                    for column in inspect(sync_conn).get_columns(table_name)
                }
            )

    def _add_column_statement(self, table: Table, name: str, definition: str) -> Any:
        preparer = self.admin_engine.dialect.identifier_preparer
        return text(
            f"ALTER TABLE {preparer.format_table(table)} "
            f"ADD COLUMN {preparer.quote(name)} {definition}"
        )

    def get_admin_session(self) -> AsyncSession:
        """Get a session for the admin database."""
        return self.admin_session

    def get_app_session(self) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
        """Get a session dependency for the main application database."""
        return self.session

    def get_primary_key(self, model: type[DeclarativeBase]) -> str | None:
        """Get the primary key of a SQLAlchemy model."""
        inspector = inspect(model)
        primary_key_columns = inspector.primary_key
        return primary_key_columns[0].name if primary_key_columns else None

    def get_primary_key_info(
        self, model: type[DeclarativeBase]
    ) -> dict[str, Any] | None:
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
