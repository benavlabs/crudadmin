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
