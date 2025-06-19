from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from crudadmin import CRUDAdmin
from crudadmin.admin_interface.middleware.auth import AdminAuthMiddleware
from tests.crud.test_admin import create_test_db_config


@pytest.mark.asyncio
async def test_root_mount_path_middleware_behavior(async_session):
    """Test that middleware correctly handles root mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Create middleware instance
    middleware = AdminAuthMiddleware(Mock(), admin)

    # Test that root path requests are processed by middleware
    mock_request = Mock(spec=Request)
    mock_request.url.path = "/"
    mock_call_next = AsyncMock()

    # Mock session validation to fail (no session)
    mock_request.cookies.get.return_value = None

    # Mock admin database session
    async def mock_get_admin_db():
        yield Mock()

    admin.db_config.get_admin_db = mock_get_admin_db

    result = await middleware.dispatch(mock_request, mock_call_next)

    # Should redirect to login for unauthenticated requests
    assert isinstance(result, RedirectResponse)
    assert (
        result.headers["location"] == "/login?error=Please+log+in+to+access+this+page"
    )


@pytest.mark.asyncio
async def test_root_mount_path_login_page_redirect(async_session):
    """Test that login page redirects correctly for root mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Mock the admin site
    admin.setup()

    # Test redirect URL generation for login success
    admin_site = admin.admin_site
    dashboard_url = f"{admin_site.get_url_prefix()}/" if admin_site.mount_path else "/"

    assert dashboard_url == "/"


@pytest.mark.asyncio
async def test_root_mount_path_model_view_urls(async_session):
    """Test that model view URLs are generated correctly for root mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Create a mock model view
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel
    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import declarative_base

    from crudadmin.admin_interface.model_view import ModelView

    Base = declarative_base()

    class TestModel(Base):
        __tablename__ = "test_model"
        id = Column(Integer, primary_key=True)
        name = Column(String)

    class TestCreateSchema(BaseModel):
        name: str

    class TestUpdateSchema(BaseModel):
        name: str

    # Mock admin site
    admin.setup()

    model_view = ModelView(
        database_config=db_config,
        templates=Jinja2Templates(directory="templates"),
        model=TestModel,
        allowed_actions={"view", "create", "update", "delete"},
        create_schema=TestCreateSchema,
        update_schema=TestUpdateSchema,
        admin_site=admin.admin_site,
    )

    # Test URL prefix generation
    assert model_view.get_url_prefix() == ""

    # Test model list URL would be /TestModel/ (not //TestModel/)
    expected_url = f"{model_view.get_url_prefix()}/TestModel/"
    assert expected_url == "/TestModel/"


@pytest.mark.asyncio
async def test_root_mount_path_vs_admin_mount_path_comparison(async_session):
    """Test the difference between root mount path and regular admin mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config_root = create_test_db_config(async_session)
    db_config_admin = create_test_db_config(async_session)

    # Root mount path admin
    admin_root = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config_root,
        setup_on_initialization=False,
    )

    # Regular admin mount path
    admin_regular = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/admin",
        db_config=db_config_admin,
        setup_on_initialization=False,
    )

    # Compare mount paths
    assert admin_root.mount_path == ""
    assert admin_regular.mount_path == "admin"

    # Compare URL prefixes
    assert admin_root.get_url_prefix() == ""
    assert admin_regular.get_url_prefix() == "/admin"

    # Compare OAuth token URLs
    assert admin_root.oauth2_scheme.model.flows.password.tokenUrl == "/login"
    assert admin_regular.oauth2_scheme.model.flows.password.tokenUrl == "/admin/login"


@pytest.mark.asyncio
async def test_root_mount_path_middleware_static_files(async_session):
    """Test that middleware correctly handles static files for root mount path."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        mount_path="/",
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Create middleware instance
    middleware = AdminAuthMiddleware(Mock(), admin)

    # Test that static file requests bypass auth
    mock_request = Mock(spec=Request)
    mock_request.url.path = "/static/favicon.png"
    mock_call_next = AsyncMock()
    mock_call_next.return_value = Mock(spec=Response)

    await middleware.dispatch(mock_request, mock_call_next)

    # Should call next without authentication check
    mock_call_next.assert_called_once()
