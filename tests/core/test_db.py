import os
import tempfile
from typing import Type

import pytest
import sqlalchemy.exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from crudadmin.admin_user.models import create_admin_user
from crudadmin.core.db import DatabaseConfig, get_default_db_path


def create_admin_base() -> Type[DeclarativeBase]:
    """Create a unique AdminBase class for each test to avoid table conflicts."""

    class AdminBase(DeclarativeBase):
        pass

    return AdminBase


@pytest.mark.asyncio
async def test_database_config_initialization(async_session):
    """Test DatabaseConfig initialization with default settings."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        admin_db_path = tmp_file.name

    config = None
    try:
        admin_base = create_admin_base()
        config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_path=admin_db_path,
        )

        assert config.base == admin_base
        assert config.session == async_session
        assert config.AdminUser is not None
        assert config.crud_users is not None

        # Test that admin database URL is correctly set
        assert f"sqlite+aiosqlite:///{admin_db_path}" in str(config.admin_engine.url)

    finally:
        if config and hasattr(config, "admin_engine") and config.admin_engine:
            await config.admin_engine.dispose()
        if os.path.exists(admin_db_path):
            os.unlink(admin_db_path)


@pytest.mark.asyncio
async def test_database_config_with_custom_models(async_session):
    """Test DatabaseConfig with custom admin user and session models."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        admin_db_path = tmp_file.name

    config = None
    try:
        admin_base = create_admin_base()
        custom_admin_user = create_admin_user(admin_base)

        config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_path=admin_db_path,
            admin_user=custom_admin_user,
        )

        assert config.AdminUser == custom_admin_user

    finally:
        if config and hasattr(config, "admin_engine") and config.admin_engine:
            await config.admin_engine.dispose()
        if os.path.exists(admin_db_path):
            os.unlink(admin_db_path)


@pytest.mark.asyncio
async def test_database_config_with_admin_db_url(async_session):
    """Test DatabaseConfig with explicit admin database URL."""
    admin_db_url = "sqlite+aiosqlite:///:memory:"
    admin_base = create_admin_base()

    config = None
    try:
        config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_url=admin_db_url,
        )

        assert str(config.admin_engine.url) == admin_db_url
    finally:
        if config and hasattr(config, "admin_engine") and config.admin_engine:
            await config.admin_engine.dispose()


@pytest.mark.asyncio
async def test_initialize_admin_db(async_session):
    """Test admin database initialization."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        admin_db_path = tmp_file.name

    config = None
    try:
        admin_base = create_admin_base()
        config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_path=admin_db_path,
        )

        await config.initialize_admin_db()

        # Verify that tables were created by checking if we can query them
        admin_session = config.get_admin_session()

        # Test that we can create a simple query without errors
        from sqlalchemy import text

        result = await admin_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = [row[0] for row in result.fetchall()]

        assert "admin_user" in tables
        # Note: admin_session table is no longer created as sessions use storage backends

        await admin_session.close()  # Close the session used for querying

    finally:
        if config and hasattr(config, "admin_engine") and config.admin_engine:
            await config.admin_engine.dispose()
        if os.path.exists(admin_db_path):
            os.unlink(admin_db_path)


@pytest.mark.asyncio
async def test_get_admin_session(db_config):
    """Test getting admin session."""
    admin_session = db_config.get_admin_session()
    assert isinstance(admin_session, AsyncSession)
    await admin_session.close()


@pytest.mark.asyncio
async def test_get_app_session(db_config):
    """Test getting app session."""
    app_session = db_config.get_app_session()
    assert isinstance(app_session, AsyncSession)


@pytest.mark.asyncio
async def test_get_primary_key(db_config, product_model):
    """Test getting primary key of a model."""
    pk = db_config.get_primary_key(product_model)
    assert pk == "id"


@pytest.mark.asyncio
async def test_get_primary_key_info(db_config, product_model):
    """Test getting primary key information of a model."""
    pk_info = db_config.get_primary_key_info(product_model)
    assert pk_info is not None
    assert "name" in pk_info
    assert "type" in pk_info
    assert pk_info["name"] == "id"


def test_get_default_db_path():
    """Test default database path generation."""
    path = get_default_db_path()
    assert path.endswith("admin.db")
    assert "crudadmin_data" in path

    import os

    data_dir = os.path.dirname(path)
    assert os.path.exists(data_dir)


@pytest.mark.asyncio
async def test_database_config_admin_db_dependency(db_config):
    """Test the admin database dependency function."""
    async for session in db_config.get_admin_db():
        assert isinstance(session, AsyncSession)
        break  # Only test the first yield


@pytest.mark.asyncio
async def test_database_config_error_handling():
    """Test error handling in database configuration."""
    # Test with invalid database URL
    config = None
    with pytest.raises(sqlalchemy.exc.ArgumentError):
        try:
            admin_base = create_admin_base()
            config = DatabaseConfig(
                base=admin_base,
                session=None,  # Invalid session
                admin_db_url="invalid://url",
            )
            await config.initialize_admin_db()
        finally:
            if config and hasattr(config, "admin_engine") and config.admin_engine:
                await config.admin_engine.dispose()


@pytest.mark.asyncio
async def test_database_config_cleanup(async_session):
    """Test proper cleanup of database resources."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        admin_db_path = tmp_file.name

    config = None
    try:
        admin_base = create_admin_base()
        config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_path=admin_db_path,
        )

        # Initialize and use the database
        await config.initialize_admin_db()
        admin_session = config.get_admin_session()

        # Close the admin session
        await admin_session.close()

        # Verify cleanup was successful - check if pool exists and has checkedout method
        # We need to ensure the engine is disposed before this check
        if hasattr(config.admin_engine.pool, "checkedout"):
            assert config.admin_engine.pool.checkedout() == 0
        # # For NullPool, just verify the engine is disposed
        assert config.admin_engine.pool is not None

    finally:
        if config and hasattr(config, "admin_engine") and config.admin_engine:
            await config.admin_engine.dispose()
            # Now we can check the pool state after dispose
            if hasattr(config.admin_engine.pool, "checkedout"):
                assert config.admin_engine.pool.checkedout() == 0

        if os.path.exists(admin_db_path):
            os.unlink(admin_db_path)
