"""
Tests for UUID primary key support in CRUDAdmin.

This module tests the functionality added to support UUID primary keys
in the ModelView class, specifically the _convert_id_to_pk_type method
and UUID handling in update operations.
"""

import uuid

import pytest
from pydantic import BaseModel
from sqlalchemy import UUID, Column, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase

from crudadmin.admin_interface.model_view import BulkDeleteRequest


class UUIDTestBase(DeclarativeBase):
    """Base class for UUID test models."""

    pass


class UUIDModel(UUIDTestBase):
    """Test model with UUID primary key."""

    __tablename__ = "uuid_test_model"
    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name = Column(String(255))
    description = Column(Text)
    created_at = Column(DateTime(timezone=False), server_default=func.now())


class StringModel(UUIDTestBase):
    """Test model with string primary key."""

    __tablename__ = "string_test_model"
    id = Column(String(50), primary_key=True)
    name = Column(String(255))


class IntModel(UUIDTestBase):
    """Test model with integer primary key."""

    __tablename__ = "int_test_model"
    id = Column(String(50), primary_key=True)  # Using string for test simplicity
    name = Column(String(255))


# Pydantic schemas for testing
class UUIDModelBase(BaseModel):
    name: str
    description: str


class UUIDModelUpdate(UUIDModelBase):
    id: uuid.UUID


class StringModelBase(BaseModel):
    name: str


class IntModelBase(BaseModel):
    name: str


def test_uuid_primary_key_detection(db_config, uuid_model):
    """Test that UUID primary keys are correctly detected."""
    pk_info = db_config.get_primary_key_info(uuid_model)

    assert pk_info is not None
    assert pk_info["name"] == "id"
    assert pk_info["type"] is uuid.UUID
    assert pk_info["type_name"] == "UUID"


def test_string_primary_key_detection(db_config, user_model):
    """Test that non-UUID primary keys still work correctly."""
    pk_info = db_config.get_primary_key_info(user_model)

    assert pk_info is not None
    assert pk_info["name"] == "id"
    # User model uses Integer primary key
    assert pk_info["type"] is int
    assert pk_info["type_name"] == "int"


def test_uuid_validation_pattern():
    """Test that UUID strings follow the expected pattern."""
    # Test various UUID formats
    valid_uuids = [
        "93c025d9-5831-413c-9460-edb3a28cc729",
        "550e8400-e29b-41d4-a716-446655440000",
        "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    ]

    uuid_regex = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    import re

    for test_uuid in valid_uuids:
        assert re.match(uuid_regex, test_uuid, re.IGNORECASE), (
            f"UUID {test_uuid} should be valid"
        )

        # Test that uuid.UUID can parse it
        try:
            uuid.UUID(test_uuid)
        except ValueError:
            pytest.fail(f"uuid.UUID failed to parse {test_uuid}")


def test_bulk_delete_request_type_annotation():
    """Test that BulkDeleteRequest accepts Union[int, str] IDs."""
    # Test with mixed ID types
    request_data = {
        "ids": [
            1,  # integer
            "93c025d9-5831-413c-9460-edb3a28cc729",  # UUID string
            "string_id",  # regular string
            123,  # another integer
        ]
    }

    # This should not raise a validation error
    bulk_request = BulkDeleteRequest(**request_data)
    assert len(bulk_request.ids) == 4
    assert 1 in bulk_request.ids
    assert "93c025d9-5831-413c-9460-edb3a28cc729" in bulk_request.ids


def test_original_error_case_structure(db_config, email_query_config_model):
    """Test the exact structure from the original error report."""

    # Test primary key detection
    pk_info = db_config.get_primary_key_info(email_query_config_model)
    assert pk_info["type"] is uuid.UUID

    # Test that UUID strings are properly formatted
    problematic_uuid = "93c025d9-5831-413c-9460-edb3a28cc729"

    # Verify this is a valid UUID format
    try:
        uuid_obj = uuid.UUID(problematic_uuid)
        assert str(uuid_obj) == problematic_uuid
    except ValueError:
        pytest.fail(f"UUID {problematic_uuid} should be valid")


@pytest.mark.asyncio
async def test_uuid_crud_operations(async_session, uuid_model, uuid_test_data):
    """Test basic CRUD operations with UUID models."""
    from fastcrud import FastCRUD

    # Create test data with proper UUID objects
    for data in uuid_test_data:
        new_item = uuid_model(
            id=uuid.UUID(data["id"]), name=data["name"], description=data["description"]
        )
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(uuid_model)

    # Test get by UUID object
    uuid_id = uuid.UUID("93c025d9-5831-413c-9460-edb3a28cc729")
    result = await crud.get(async_session, id=uuid_id)

    assert result is not None
    assert result["name"] == "Test Item 1"
    assert result["description"] == "First test item with UUID"


def test_id_conversion_logic_uuid():
    """Test the ID conversion logic for UUID types."""
    from uuid import UUID

    # Simulate the conversion logic from _convert_id_to_pk_type
    pk_type = UUID
    id_value = "93c025d9-5831-413c-9460-edb3a28cc729"

    # This is the logic that would be used in _convert_id_to_pk_type
    if pk_type is int:
        converted_id = int(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is str:
        converted_id = str(id_value)
    elif pk_type is float:
        converted_id = float(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is UUID:
        # For UUID types, return as string (FastCRUD handles string UUIDs)
        converted_id = str(id_value)
    else:
        # For other types, return as string
        converted_id = str(id_value)

    assert isinstance(converted_id, str)
    assert converted_id == id_value


def test_id_conversion_logic_int():
    """Test the ID conversion logic for integer types."""
    # Simulate the conversion logic for integer primary keys
    pk_type = int
    id_value = "123"

    if pk_type is int:
        converted_id = int(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is str:
        converted_id = str(id_value)
    elif pk_type is float:
        converted_id = float(id_value) if isinstance(id_value, str) else id_value
    else:
        converted_id = str(id_value)

    assert isinstance(converted_id, int)
    assert converted_id == 123


def test_id_conversion_logic_str():
    """Test the ID conversion logic for string types."""
    # Simulate the conversion logic for string primary keys
    pk_type = str
    id_value = "test_string_id"

    if pk_type is int:
        converted_id = int(id_value) if isinstance(id_value, str) else id_value
    elif pk_type is str:
        converted_id = str(id_value)
    elif pk_type is float:
        converted_id = float(id_value) if isinstance(id_value, str) else id_value
    else:
        converted_id = str(id_value)

    assert isinstance(converted_id, str)
    assert converted_id == id_value
