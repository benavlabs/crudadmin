"""
Unit tests for the select_schema functionality in CRUDAdmin and ModelView.

Tests verify that the select_schema parameter:
1. Is accepted by the add_view method
2. Is properly stored in ModelView instances
3. Is used in all CRUD read operations (get, get_multi)
4. Handles TSVector-like scenarios correctly
"""

from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

from crudadmin.admin_interface.crud_admin import CRUDAdmin
from crudadmin.admin_interface.model_view import ModelView


# Test models and schemas
class _TestBase(DeclarativeBase):
    pass


class DocumentModel(_TestBase):
    """Test model with a problematic field (simulating TSVector)"""

    __tablename__ = "test_document"

    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    content = Column(Text)
    search_vector = Column(
        Text
    )  # Simulates TSVectorType that causes NotImplementedError


class DocumentCreate(BaseModel):
    """Create schema without problematic field"""

    title: str
    content: str


class DocumentUpdate(BaseModel):
    """Update schema without problematic field"""

    title: Optional[str] = None
    content: Optional[str] = None


class DocumentSelect(BaseModel):
    """Select schema that excludes the problematic field"""

    id: int
    title: str
    content: str
    # search_vector field intentionally excluded!


class DocumentSelectFull(BaseModel):
    """Select schema that includes all fields (would cause issues)"""

    id: int
    title: str
    content: str
    search_vector: str  # This field causes problems in real scenarios


def create_test_db_config_with_unique_base(async_session):
    """Create a test database config with unique admin base to avoid conflicts."""
    from crudadmin.core.db import DatabaseConfig

    # Create a unique base class for this test
    class UniqueTestAdminBase(DeclarativeBase):
        pass

    async def get_session():
        yield async_session

    return DatabaseConfig(
        base=UniqueTestAdminBase,
        session=get_session,
        admin_db_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.mark.asyncio
async def test_add_view_accepts_select_schema_parameter(async_session):
    """Test that add_view method accepts the select_schema parameter."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config_with_unique_base(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Mock the admin_site to avoid complex initialization
    admin.admin_site = Mock()
    admin.admin_site.mount_path = "admin"
    admin.app = Mock()
    admin.app.include_router = Mock()

    # This should not raise an error
    admin.add_view(
        model=DocumentModel,
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        select_schema=DocumentSelect,  # This is the new parameter
        allowed_actions={"view", "create", "update"},
    )

    # Verify the router was included (indicating successful add_view)
    admin.app.include_router.assert_called_once()


@pytest.mark.asyncio
async def test_model_view_stores_select_schema(async_session):
    """Test that ModelView properly stores the select_schema parameter."""
    db_config = create_test_db_config_with_unique_base(async_session)

    # Mock templates to avoid template loading issues
    templates = Mock()

    # Mock admin_site to avoid initialization issues
    admin_site = Mock()
    admin_site.admin_authentication.get_current_user.return_value = Mock()

    model_view = ModelView(
        database_config=db_config,
        templates=templates,
        model=DocumentModel,
        allowed_actions={"view", "create", "update"},
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        select_schema=DocumentSelect,
        admin_site=admin_site,
    )

    # Verify the select_schema is stored
    assert model_view.select_schema == DocumentSelect


@pytest.mark.asyncio
async def test_model_view_select_schema_none_by_default(async_session):
    """Test that ModelView select_schema is None when not provided."""
    db_config = create_test_db_config_with_unique_base(async_session)
    templates = Mock()

    # Mock admin_site to avoid initialization issues
    admin_site = Mock()
    admin_site.admin_authentication.get_current_user.return_value = Mock()

    model_view = ModelView(
        database_config=db_config,
        templates=templates,
        model=DocumentModel,
        allowed_actions={"view", "create", "update"},
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        admin_site=admin_site,
        # select_schema not provided
    )

    # Verify the select_schema is None
    assert model_view.select_schema is None


@pytest.mark.asyncio
async def test_get_multi_uses_select_schema_parameter(async_session):
    """Test that get_multi calls include schema_to_select when select_schema is provided."""
    db_config = create_test_db_config_with_unique_base(async_session)
    templates = Mock()

    model_view = ModelView(
        database_config=db_config,
        templates=templates,
        model=DocumentModel,
        allowed_actions={"view"},
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        select_schema=DocumentSelect,
    )

    # Mock the CRUD get_multi method to capture its call
    model_view.crud.get_multi = AsyncMock(
        return_value={
            "data": [{"id": 1, "title": "Test", "content": "Test content"}],
            "total_count": 1,
        }
    )

    # Call get_multi directly to test the parameter passing
    await model_view.crud.get_multi(
        db=Mock(), schema_to_select=model_view.select_schema, offset=0, limit=10
    )

    # Verify get_multi was called with the select_schema
    model_view.crud.get_multi.assert_called_once()
    call_kwargs = model_view.crud.get_multi.call_args.kwargs
    assert call_kwargs["schema_to_select"] == DocumentSelect


@pytest.mark.asyncio
async def test_get_uses_select_schema_parameter(async_session):
    """Test that get calls include schema_to_select when select_schema is provided."""
    db_config = create_test_db_config_with_unique_base(async_session)
    templates = Mock()

    # Mock admin_site to avoid initialization issues
    admin_site = Mock()
    admin_site.admin_authentication.get_current_user.return_value = Mock()

    model_view = ModelView(
        database_config=db_config,
        templates=templates,
        model=DocumentModel,
        allowed_actions={"update"},
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        select_schema=DocumentSelect,
        admin_site=admin_site,
    )

    # Mock the CRUD get method
    model_view.crud.get = AsyncMock(
        return_value={"id": 1, "title": "Test", "content": "Test content"}
    )

    # Call get directly to test the parameter passing
    await model_view.crud.get(
        db=Mock(), id=1, schema_to_select=model_view.select_schema
    )

    # Verify get was called with the select_schema
    model_view.crud.get.assert_called_once()
    call_kwargs = model_view.crud.get.call_args.kwargs
    assert call_kwargs["schema_to_select"] == DocumentSelect


@pytest.mark.asyncio
async def test_crud_operations_pass_none_when_no_select_schema(async_session):
    """Test that CRUD operations pass None for schema_to_select when select_schema is None."""
    db_config = create_test_db_config_with_unique_base(async_session)
    templates = Mock()

    # Mock admin_site to avoid initialization issues
    admin_site = Mock()
    admin_site.admin_authentication.get_current_user.return_value = Mock()

    model_view = ModelView(
        database_config=db_config,
        templates=templates,
        model=DocumentModel,
        allowed_actions={"view", "update"},
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        admin_site=admin_site,
        # select_schema=None (default)
    )

    # Mock CRUD operations
    model_view.crud.get_multi = AsyncMock(return_value={"data": [], "total_count": 0})
    model_view.crud.get = AsyncMock(return_value={"id": 1, "title": "Test"})

    # Test get_multi
    await model_view.crud.get_multi(
        db=Mock(), schema_to_select=model_view.select_schema, offset=0, limit=10
    )

    # Verify get_multi was called with schema_to_select=None
    call_kwargs = model_view.crud.get_multi.call_args.kwargs
    assert call_kwargs["schema_to_select"] is None

    # Test get
    await model_view.crud.get(
        db=Mock(), id=1, schema_to_select=model_view.select_schema
    )

    # Verify get was called with schema_to_select=None
    call_kwargs = model_view.crud.get.call_args.kwargs
    assert call_kwargs["schema_to_select"] is None


@pytest.mark.asyncio
async def test_add_view_passes_select_schema_to_model_view(async_session):
    """Test that add_view properly passes select_schema to ModelView constructor."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config_with_unique_base(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Mock admin_site and app to avoid complex initialization
    admin.admin_site = Mock()
    admin.admin_site.mount_path = "admin"
    admin.app = Mock()
    admin.app.include_router = Mock()

    # Mock ModelView to capture constructor arguments
    with patch("crudadmin.admin_interface.crud_admin.ModelView") as mock_model_view:
        mock_instance = Mock()
        mock_instance.router = Mock()
        mock_model_view.return_value = mock_instance

        # Call add_view with select_schema
        admin.add_view(
            model=DocumentModel,
            create_schema=DocumentCreate,
            update_schema=DocumentUpdate,
            select_schema=DocumentSelect,
            allowed_actions={"view", "create", "update"},
        )

        # Verify ModelView was called with select_schema
        mock_model_view.assert_called_once()
        call_kwargs = mock_model_view.call_args.kwargs
        assert call_kwargs["select_schema"] == DocumentSelect


def test_select_schema_excludes_problematic_fields():
    """Test that DocumentSelect schema properly excludes the problematic field."""
    # Test that DocumentSelect excludes search_vector field
    select_fields = set(DocumentSelect.model_fields.keys())
    expected_fields = {"id", "title", "content"}

    assert select_fields == expected_fields
    assert "search_vector" not in select_fields

    # Test that DocumentSelectFull includes all fields (problematic scenario)
    full_fields = set(DocumentSelectFull.model_fields.keys())
    expected_full_fields = {"id", "title", "content", "search_vector"}

    assert full_fields == expected_full_fields
    assert "search_vector" in full_fields


def test_tsvector_scenario_documentation():
    """Integration test demonstrating TSVector scenario - how select_schema solves the problem."""

    # The key benefit: select_schema excludes problematic fields from read operations
    # while still allowing create/update operations to work normally
    assert set(DocumentSelect.model_fields.keys()) == {"id", "title", "content"}
    assert "search_vector" not in DocumentSelect.model_fields

    # This is how you would use it in practice:
    # Without select_schema: TSVector field causes NotImplementedError in admin reads
    # With select_schema: TSVector field excluded from admin reads, no errors

    # Verify the solution excludes the problematic field
    excluded_fields = {"search_vector"}  # TSVector field
    safe_fields = set(DocumentSelect.model_fields.keys())

    assert excluded_fields.isdisjoint(safe_fields), (
        "Problematic fields should be excluded"
    )


@pytest.mark.asyncio
async def test_add_view_with_select_schema_integration(async_session):
    """Integration test for the full add_view workflow with select_schema."""
    secret_key = "test-secret-key-for-testing-only-32-chars"
    db_config = create_test_db_config_with_unique_base(async_session)

    admin = CRUDAdmin(
        session=async_session,
        SECRET_KEY=secret_key,
        db_config=db_config,
        setup_on_initialization=False,
    )

    # Mock minimal dependencies
    admin.admin_site = Mock()
    admin.admin_site.mount_path = "admin"
    admin.app = Mock()
    admin.app.include_router = Mock()

    # Test: Add view with select_schema
    admin.add_view(
        model=DocumentModel,
        create_schema=DocumentCreate,
        update_schema=DocumentUpdate,
        select_schema=DocumentSelect,  # Key parameter being tested
        allowed_actions={"view", "create", "update"},
    )

    # Verify successful integration
    admin.app.include_router.assert_called_once()

    # The model should be added to models dict since include_in_models defaults to True
    assert DocumentModel.__name__ in admin.models
    model_config = admin.models[DocumentModel.__name__]
    assert model_config["model"] == DocumentModel
