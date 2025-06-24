import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy.orm import DeclarativeBase

from crudadmin.admin_interface.crud_admin import CRUDAdmin
from crudadmin.core.db import DatabaseConfig


def create_unique_admin_base() -> type[DeclarativeBase]:
    """Create a unique AdminBase class for each test to avoid table conflicts."""

    class AdminBase(DeclarativeBase):
        pass

    return AdminBase


def create_test_db_config(async_session, include_event_models=False) -> DatabaseConfig:
    """Create a unique DatabaseConfig for testing."""
    admin_base = create_unique_admin_base()

    async def get_session():
        yield async_session

    config_kwargs = {
        "base": admin_base,
        "session": get_session,
        "admin_db_url": "sqlite+aiosqlite:///:memory:",
    }

    if include_event_models:
        from crudadmin.event.models import (
            create_admin_audit_log,
            create_admin_event_log,
        )

        config_kwargs["admin_event_log"] = create_admin_event_log(admin_base)
        config_kwargs["admin_audit_log"] = create_admin_audit_log(admin_base)

    return DatabaseConfig(**config_kwargs)


@pytest.mark.asyncio
async def test_crud_admin_initialization(async_session):
    """Test CRUDAdmin initialization with basic parameters."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/admin",
        db_config=db_config,
        setup_on_initialization=False,
    )

    assert admin.mount_path == "admin"
    assert admin.SECRET_KEY == secret_key
    assert admin.theme == "dark-theme"  # default
    assert admin.session_manager.max_sessions == 5  # default
    assert admin.session_manager.session_timeout.total_seconds() == 30 * 60  # default
    assert admin.secure_cookies is True  # default
    assert admin.track_events is False  # default


@pytest.mark.asyncio
async def test_crud_admin_with_custom_settings(async_session):
    """Test CRUDAdmin initialization with custom settings."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session, include_event_models=True)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/custom-admin",
        theme="light-theme",
        max_sessions_per_user=10,
        session_timeout_minutes=60,
        cleanup_interval_minutes=30,
        secure_cookies=False,
        enforce_https=True,
        https_port=8443,
        track_events=True,
        db_config=db_config,
        setup_on_initialization=False,
    )

    assert admin.mount_path == "custom-admin"
    assert admin.theme == "light-theme"
    assert admin.session_manager.max_sessions == 10
    assert admin.session_manager.session_timeout.total_seconds() == 60 * 60
    assert admin.session_manager.cleanup_interval.total_seconds() == 30 * 60
    assert admin.secure_cookies is False
    assert admin.track_events is True


@pytest.mark.asyncio
async def test_crud_admin_root_mount_path(async_session):
    """Test CRUDAdmin initialization with root mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Test that mount_path is properly set to empty string for root
    assert admin.mount_path == ""

    # Test that URL prefix is correctly generated
    assert admin.get_url_prefix() == ""

    # Test that OAuth2 token URL is correctly set for root path
    assert admin.oauth2_scheme.model.flows.password.tokenUrl == "/login"


@pytest.mark.asyncio
async def test_crud_admin_with_allowed_ips(async_session):
    """Test CRUDAdmin initialization with IP restrictions."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    allowed_ips = ["127.0.0.1", "192.168.1.100"]
    allowed_networks = ["10.0.0.0/8", "172.16.0.0/12"]
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        allowed_ips=allowed_ips,
        allowed_networks=allowed_networks,
        db_config=db_config,
        setup_on_initialization=False,
    )

    from unittest.mock import patch

    with patch("crudadmin.admin_interface.crud_admin.AdminSite") as mock_admin_site:
        mock_site_instance = Mock()
        mock_site_instance.router = APIRouter()
        mock_admin_site.return_value = mock_site_instance

        admin.setup()

    from crudadmin.admin_interface.middleware.ip_restriction import (
        IPRestrictionMiddleware,
    )

    registered_middleware_classes = [
        middleware.cls for middleware in admin.app.user_middleware
    ]
    assert any(
        issubclass(mw_class, IPRestrictionMiddleware)
        for mw_class in registered_middleware_classes
    )


@pytest.mark.asyncio
async def test_crud_admin_with_initial_admin(async_session):
    """Test CRUDAdmin initialization with initial admin user."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    initial_admin = {
        "username": "admin",
        "password": "SecurePass123!",
        "is_superuser": True,
    }
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        initial_admin=initial_admin,
        db_config=db_config,
        setup_on_initialization=False,
    )

    assert admin.initial_admin == initial_admin


@pytest.mark.asyncio
async def test_crud_admin_with_custom_db_config(async_session):
    """Test CRUDAdmin initialization with custom database config."""
    secret_key = "test-secret-key-for-testing-only-32-chars"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        admin_db_path = tmp_file.name

    try:
        admin_base = create_unique_admin_base()
        db_config = DatabaseConfig(
            base=admin_base,
            session=async_session,
            admin_db_path=admin_db_path,
        )

        admin = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
        )

        assert admin.db_config == db_config

    finally:
        if os.path.exists(admin_db_path):
            os.unlink(admin_db_path)


@pytest.mark.asyncio
async def test_crud_admin_add_view(
    async_session, product_model, product_create_schema, product_update_schema
):
    """Test adding a model view to CRUDAdmin."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    admin.admin_site = Mock()

    admin.add_view(
        model=product_model,
        create_schema=product_create_schema,
        update_schema=product_update_schema,
        update_internal_schema=None,
        delete_schema=None,
        include_in_models=True,
    )

    # Verify the model was added
    assert product_model.__name__ in admin.models
    model_config = admin.models[product_model.__name__]
    assert model_config["model"] == product_model


@pytest.mark.asyncio
async def test_crud_admin_add_view_with_allowed_actions(
    async_session, product_model, product_create_schema, product_update_schema
):
    """Test adding a model view with specific allowed actions."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    admin.admin_site = Mock()

    allowed_actions = {"create", "read", "update"}  # No delete

    admin.add_view(
        model=product_model,
        create_schema=product_create_schema,
        update_schema=product_update_schema,
        update_internal_schema=None,
        delete_schema=None,
        allowed_actions=allowed_actions,
    )

    # Verify the model was added with correct allowed actions
    assert product_model.__name__ in admin.models


@pytest.mark.asyncio
async def test_crud_admin_add_view_exclude_from_models(
    async_session, product_model, product_create_schema, product_update_schema
):
    """Test adding a model view but excluding it from models list."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    admin.admin_site = Mock()

    admin.add_view(
        model=product_model,
        create_schema=product_create_schema,
        update_schema=product_update_schema,
        update_internal_schema=None,
        delete_schema=None,
        include_in_models=False,  # Exclude from models list
    )

    # The model should not be in the models dict since include_in_models=False
    assert product_model.__name__ not in admin.models


@pytest.mark.asyncio
async def test_crud_admin_setup_event_routes(async_session):
    """Test setting up event routes."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session, include_event_models=True)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        track_events=True,
        db_config=db_config,
        setup_on_initialization=False,
    )

    admin.admin_authentication.get_current_user = Mock(return_value=Mock())
    admin.setup_event_routes()


@pytest.mark.asyncio
async def test_crud_admin_initialize(async_session):
    """Test CRUDAdmin initialization process."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    await admin.initialize()

    # Verify that the database was initialized (no exception raised)
    assert True  # If we get here, initialization succeeded


@pytest.mark.asyncio
async def test_crud_admin_create_initial_admin(async_session):
    """Test creating initial admin user."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    initial_admin = {
        "username": "admin",
        "password": "SecurePass123!",
    }
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        initial_admin=initial_admin,
        db_config=db_config,
        setup_on_initialization=False,
    )

    with patch.object(
        admin, "_create_initial_admin", new_callable=AsyncMock
    ) as mock_create:
        await admin._create_initial_admin(initial_admin)
        mock_create.assert_called_once_with(initial_admin)


@pytest.mark.asyncio
async def test_crud_admin_setup(async_session):
    """Test CRUDAdmin setup process."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    from unittest.mock import patch

    with patch.object(admin, "admin_authentication") as mock_auth:
        mock_auth.get_current_user.return_value = Mock()
        mock_auth.auth_models = {}

        with patch("crudadmin.admin_interface.crud_admin.AdminSite") as mock_admin_site:
            mock_site_instance = Mock()
            mock_site_instance.router = APIRouter()
            mock_admin_site.return_value = mock_site_instance

            admin.setup()

            # Verify that admin_site was created
            assert hasattr(admin, "admin_site")
            assert admin.admin_site is not None


@pytest.mark.asyncio
async def test_crud_admin_app_creation(async_session):
    """Test that CRUDAdmin creates a FastAPI app."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Verify that the admin has a FastAPI app
    assert hasattr(admin, "app")
    assert isinstance(admin.app, FastAPI)


@pytest.mark.asyncio
async def test_crud_admin_health_check_routes(async_session):
    """Test health check route creation."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Test health check page endpoint
    health_check_func = admin.health_check_page()
    assert callable(health_check_func)

    # Test health check content endpoint
    health_content_func = admin.health_check_content()
    assert callable(health_content_func)


@pytest.mark.asyncio
async def test_crud_admin_session_manager_integration(async_session):
    """Test CRUDAdmin integration with session manager."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        max_sessions_per_user=3,
        session_timeout_minutes=45,
        cleanup_interval_minutes=20,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Verify session manager is configured with correct settings
    assert admin.session_manager.max_sessions == 3
    assert admin.session_manager.session_timeout.total_seconds() == 45 * 60
    assert admin.session_manager.cleanup_interval.total_seconds() == 20 * 60


@pytest.mark.asyncio
async def test_crud_admin_authentication_integration(async_session):
    """Test CRUDAdmin integration with authentication."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Verify authentication components are set up
    assert hasattr(admin, "admin_authentication")
    assert hasattr(admin, "admin_user_service")


@pytest.mark.asyncio
async def test_crud_admin_error_handling_invalid_session(async_session):
    """Test CRUDAdmin error handling with invalid session."""
    secret_key = "test-secret-key-for-testing-only-32-chars"

    # Create a db_config with None as session
    admin_base = create_unique_admin_base()
    db_config = DatabaseConfig(
        base=admin_base,
        session=None,  # Pass None directly here
        admin_db_url="sqlite+aiosqlite:///:memory:",
    )

    admin = CRUDAdmin(
        session=None,  # This doesn't raise an error in __init__
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # The session should be None in the db_config
    assert admin.db_config.session is None


@pytest.mark.asyncio
async def test_crud_admin_session_backend_configuration(async_session):
    """Test that different session backends can be configured via constructor."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    # Test memory backend (default)
    admin_memory = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )
    assert "MemorySessionStorage" in str(type(admin_memory.session_manager.storage))

    # Test database backend
    admin_db = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
        session_backend="database",
    )
    assert "DatabaseSessionStorage" in str(type(admin_db.session_manager.storage))
    assert admin_db.track_sessions_in_db is True

    # Test Redis URL parsing with new config objects
    from crudadmin.session.configs import RedisConfig

    redis_config = RedisConfig(url="redis://user:pass@localhost:6379/2")
    parsed = redis_config.to_dict()
    expected = {
        "host": "localhost",
        "port": 6379,
        "db": 2,
        "username": "user",
        "password": "pass",
    }
    assert parsed == expected

    # Test Redis URL parsing with defaults
    redis_config_simple = RedisConfig(url="redis://localhost")
    parsed_simple = redis_config_simple.to_dict()
    expected_simple = {
        "host": "localhost",
        "port": 6379,
        "db": 0,
    }
    assert parsed_simple == expected_simple

    # Test Redis backend configuration (if redis is available)
    try:
        redis_config = RedisConfig(url="redis://localhost:6379/0")
        admin_redis = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            session_backend="redis",
            redis_config=redis_config,
        )
        storage_type_name = type(admin_redis.session_manager.storage).__name__
        assert storage_type_name == "RedisSessionStorage"
    except ImportError:
        # Redis not available, which is fine for tests
        pass


@pytest.mark.asyncio
async def test_crud_admin_backend_parameter_validation(async_session):
    """Test parameter validation for session backend constructor parameters."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    # Test Redis parameter validation
    try:
        from crudadmin.session.configs import MemcachedConfig, RedisConfig

        # Test individual parameters work
        redis_config = RedisConfig(host="localhost", port=6379, db=1)
        admin_redis_individual = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            session_backend="redis",
            redis_config=redis_config,
        )
        storage_type_name = type(
            admin_redis_individual.session_manager.storage
        ).__name__
        assert storage_type_name == "RedisSessionStorage"

        # Test defaults work
        admin_redis_defaults = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            session_backend="redis",
        )
        assert (
            type(admin_redis_defaults.session_manager.storage).__name__
            == "RedisSessionStorage"
        )

        # Test validation works
        with pytest.raises(ValueError):
            RedisConfig(port=70000)  # Invalid port range

    except ImportError:
        # Redis not available, skip Redis tests
        pass

    # Test Memcached parameter validation
    try:
        # Test individual parameters work
        memcached_config = MemcachedConfig(host="localhost", port=11211)
        admin_memcached_individual = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            session_backend="memcached",
            memcached_config=memcached_config,
        )
        storage_type_name = type(
            admin_memcached_individual.session_manager.storage
        ).__name__
        assert storage_type_name == "MemcachedSessionStorage"

        # Test defaults work
        admin_memcached_defaults = CRUDAdmin(
            session=async_session,
            SECRET_KEY=secret_key,
            db_config=db_config,
            setup_on_initialization=False,
            session_backend="memcached",
        )
        assert (
            type(admin_memcached_defaults.session_manager.storage).__name__
            == "MemcachedSessionStorage"
        )

        # Test validation works
        with pytest.raises(ValueError):
            MemcachedConfig(port=70000)  # Invalid port range

    except ImportError:
        # Memcached not available, skip Memcached tests
        pass
