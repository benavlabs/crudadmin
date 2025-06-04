from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Optional, Type
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import pytest_asyncio
from fastapi import Request, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    make_url,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.sql import func
from testcontainers.core.docker_client import DockerClient
from testcontainers.mysql import MySqlContainer
from testcontainers.postgres import PostgresContainer

from crudadmin.admin_interface.crud_admin import CRUDAdmin
from crudadmin.admin_user.service import AdminUserService
from crudadmin.core.db import DatabaseConfig
from crudadmin.event.models import create_admin_audit_log, create_admin_event_log
from crudadmin.event.service import EventService
from crudadmin.session.manager import SessionManager
from crudadmin.session.schemas import SessionData
from crudadmin.session.storage import get_session_storage


class Base(DeclarativeBase):
    pass


class CategoryModel(Base):
    __tablename__ = "category"
    id = Column(Integer, primary_key=True)
    name = Column(String(32), unique=True)
    products = relationship("ProductModel", back_populates="category")


class ProductModel(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key=True)
    name = Column(String(32))
    price = Column(Integer)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=True)
    category = relationship("CategoryModel", back_populates="products")
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class UserModel(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True)
    email = Column(String(64), unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class CategoryRead(BaseModel):
    id: int
    name: str


class CategoryUpdate(BaseModel):
    name: str


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    price: int
    category_id: Optional[int] = None


class ProductRead(BaseModel):
    id: int
    name: str
    price: int
    category_id: Optional[int]


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    category_id: Optional[int] = None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    email: str
    is_active: bool = True


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


def is_docker_running() -> bool:
    try:
        DockerClient()
        return True
    except Exception:
        return False


@asynccontextmanager
async def _async_session(url: str) -> AsyncGenerator[AsyncSession]:
    async_engine = create_async_engine(url, echo=False, future=True)

    session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with session() as s:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield s

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await async_engine.dispose()


@asynccontextmanager
async def _admin_async_session(url: str) -> AsyncGenerator[AsyncSession]:
    async_engine = create_async_engine(url, echo=False, future=True)

    session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with session() as s:
        admin_base = create_admin_base()
        async with async_engine.begin() as conn:
            await conn.run_sync(admin_base.metadata.create_all)

        yield s

    async with async_engine.begin() as conn:
        await conn.run_sync(admin_base.metadata.drop_all)

    await async_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncSession]:
    dialect_marker = request.node.get_closest_marker("dialect")
    dialect = dialect_marker.args[0] if dialect_marker else "sqlite"

    if dialect == "postgresql":
        if not is_docker_running():
            pytest.skip("Docker is required, but not running")
        with PostgresContainer(driver="psycopg") as pg:
            async with _async_session(
                url=pg.get_connection_url(host=pg.get_container_host_ip())
            ) as session:
                yield session
    elif dialect == "sqlite":
        async with _async_session(url="sqlite+aiosqlite:///:memory:") as session:
            yield session
    elif dialect == "mysql":
        if not is_docker_running():
            pytest.skip("Docker is required, but not running")
        with MySqlContainer() as mysql:
            async with _async_session(
                url=make_url(name_or_url=mysql.get_connection_url())._replace(
                    drivername="mysql+aiomysql"
                )
            ) as session:
                yield session
    else:
        raise NotImplementedError(f"Unsupported dialect: {dialect}")


@pytest_asyncio.fixture(scope="function")
async def admin_async_session() -> AsyncGenerator[AsyncSession]:
    async with _admin_async_session(url="sqlite+aiosqlite:///:memory:") as session:
        yield session


@pytest.fixture(scope="function")
def test_data() -> list[dict]:
    return [
        {"id": 1, "name": "Laptop", "price": 1000, "category_id": 1},
        {"id": 2, "name": "Mouse", "price": 25, "category_id": 1},
        {"id": 3, "name": "Book", "price": 15, "category_id": 2},
        {"id": 4, "name": "Pen", "price": 2, "category_id": 2},
        {"id": 5, "name": "Monitor", "price": 300, "category_id": 1},
    ]


@pytest.fixture(scope="function")
def category_data() -> list[dict]:
    return [
        {"id": 1, "name": "Electronics"},
        {"id": 2, "name": "Office"},
    ]


@pytest.fixture(scope="function")
def user_data() -> list[dict]:
    return [
        {"id": 1, "username": "alice", "email": "alice@example.com", "is_active": True},
        {"id": 2, "username": "bob", "email": "bob@example.com", "is_active": True},
        {
            "id": 3,
            "username": "charlie",
            "email": "charlie@example.com",
            "is_active": False,
        },
    ]


@pytest.fixture(scope="function")
def admin_user_data() -> dict:
    return {
        "username": "admin",
        "password": "SecurePass123!",
        "is_superuser": True,
    }


@pytest.fixture
def product_model():
    return ProductModel


@pytest.fixture
def category_model():
    return CategoryModel


@pytest.fixture
def user_model():
    return UserModel


@pytest.fixture
def product_create_schema():
    return ProductCreate


@pytest.fixture
def product_read_schema():
    return ProductRead


@pytest.fixture
def product_update_schema():
    return ProductUpdate


@pytest.fixture
def category_create_schema():
    return CategoryCreate


@pytest.fixture
def category_read_schema():
    return CategoryRead


@pytest.fixture
def category_update_schema():
    return CategoryUpdate


@pytest.fixture
def user_create_schema():
    return UserCreate


@pytest.fixture
def user_read_schema():
    return UserRead


@pytest.fixture
def user_update_schema():
    return UserUpdate


@pytest_asyncio.fixture(scope="function")
async def db_config(admin_async_session) -> AsyncGenerator[DatabaseConfig, None]:
    """Create a DatabaseConfig instance for testing."""
    admin_base = create_admin_base()

    admin_event_log = create_admin_event_log(admin_base)
    admin_audit_log = create_admin_audit_log(admin_base)

    config = DatabaseConfig(
        base=admin_base,
        session=admin_async_session,
        admin_db_url="sqlite+aiosqlite:///:memory:",
        admin_event_log=admin_event_log,
        admin_audit_log=admin_audit_log,
    )

    await config.initialize_admin_db()

    yield config

    await config.admin_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def admin_user_service(db_config) -> AdminUserService:
    """Create an AdminUserService instance for testing."""
    return AdminUserService(db_config=db_config)


@pytest_asyncio.fixture(scope="function")
async def session_manager(db_config) -> SessionManager:
    """Create a SessionManager instance for testing."""
    # Use memory backend for testing
    storage = get_session_storage(
        backend="memory",
        model_type=SessionData,
        prefix="test_session:",
        expiration=30 * 60,  # 30 minutes in seconds
    )

    return SessionManager(
        session_storage=storage,
        session_timeout_minutes=30,
        max_sessions_per_user=5,
    )


@pytest_asyncio.fixture(scope="function")
async def event_service(db_config) -> EventService:
    """Create an EventService instance for testing."""
    return EventService(db_config=db_config)


@pytest_asyncio.fixture(scope="function")
async def crud_admin(async_session) -> CRUDAdmin:
    """Create a CRUDAdmin instance for testing."""
    admin = CRUDAdmin(
        session=async_session,
        admin_db_url="sqlite+aiosqlite:///:memory:",
        SECRET_KEY="test-secret-key-for-testing-only-min-32-chars",
        setup_on_initialization=False,
    )

    await admin.initialize()

    return admin


@pytest.fixture
def test_client(crud_admin):
    """Create a test client for the CRUDAdmin FastAPI app."""
    return TestClient(crud_admin.app)


@pytest.fixture
def mock_request():
    """Create a mock request object for testing."""
    request = Mock()
    request.client.host = "127.0.0.1"
    request.headers = {"user-agent": "test-agent"}
    return request


def create_admin_base() -> Type[DeclarativeBase]:
    """Create a unique AdminBase class for each test to avoid table conflicts."""

    class AdminBase(DeclarativeBase):
        pass

    return AdminBase


# Session-specific fixtures
@pytest.fixture
def mock_session_storage():
    """Create a mock session storage."""
    storage = AsyncMock()
    storage.create = AsyncMock()
    storage.get = AsyncMock()
    storage.update = AsyncMock()
    storage.delete = AsyncMock()
    storage.extend = AsyncMock()
    storage.exists = AsyncMock()
    storage.get_user_sessions = AsyncMock(return_value=[])
    storage._scan_iter = AsyncMock()
    return storage


@pytest.fixture
def mock_csrf_storage():
    """Create a mock CSRF token storage."""
    storage = AsyncMock()
    storage.create = AsyncMock()
    storage.get = AsyncMock()
    storage.delete = AsyncMock()
    return storage


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    session_manager = MagicMock(spec=SessionManager)
    session_manager.create_session = AsyncMock()
    session_manager.validate_session = AsyncMock()
    session_manager.validate_csrf_token = AsyncMock()
    session_manager.regenerate_csrf_token = AsyncMock()
    session_manager.terminate_session = AsyncMock()
    session_manager.set_session_cookies = MagicMock()
    session_manager.clear_session_cookies = MagicMock()
    session_manager.track_login_attempt = AsyncMock()
    session_manager.cleanup_expired_sessions = AsyncMock()
    session_manager.session_timeout = timedelta(minutes=30)
    return session_manager


@pytest.fixture
def mock_session_data():
    """Create mock session data for testing."""
    return SessionData(
        session_id="test-session-id",
        user_id=1,
        is_active=True,
        ip_address="127.0.0.1",
        user_agent="test-agent",
        device_info={},
        last_activity=datetime.now(UTC),
        metadata={},
    )


@pytest.fixture
def mock_session_request():
    """Create a mock request for session testing."""
    request = MagicMock(spec=Request)
    request.client.host = "127.0.0.1"
    request.headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
        "x-forwarded-for": "192.168.1.1",
        "X-CSRF-Token": "test-csrf-token",
    }
    request.cookies = {"session_id": "test-session-id"}
    request.method = "POST"
    return request


@pytest.fixture
def mock_session_response():
    """Create a mock response for session testing."""
    response = MagicMock(spec=Response)
    response.set_cookie = MagicMock()
    response.delete_cookie = MagicMock()
    return response
