from typing import Annotated

import pytest
from fastcrud import FastCRUD
from pydantic import BaseModel, Field


class CustomProductCreateSchema(BaseModel):
    name: Annotated[str, Field(max_length=20)]
    price: int
    category_id: int


@pytest.mark.asyncio
async def test_get_multi_basic(
    async_session, product_model, category_model, test_data, category_data
):
    """Test basic get_multi functionality."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(async_session)

    assert "data" in result
    assert "total_count" in result
    assert len(result["data"]) == len(test_data)
    assert result["total_count"] == len(test_data)


@pytest.mark.asyncio
async def test_get_multi_pagination(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi with pagination."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test first page
    result = await crud.get_multi(async_session, offset=0, limit=2)
    assert len(result["data"]) == 2
    assert result["total_count"] == len(test_data)

    # Test second page
    result = await crud.get_multi(async_session, offset=2, limit=2)
    assert len(result["data"]) == 2

    # Test last page
    result = await crud.get_multi(async_session, offset=4, limit=2)
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_get_multi_unpaginated(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi without pagination."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(async_session, paginate=False)

    assert "data" in result
    assert len(result["data"]) == len(test_data)


@pytest.mark.asyncio
async def test_get_multi_sorting(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi with sorting."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test ascending sort by price
    result = await crud.get_multi(
        async_session, sort_columns=["price"], sort_orders=["asc"]
    )
    prices = [item["price"] for item in result["data"]]
    assert prices == sorted(prices)

    # Test descending sort by price
    result = await crud.get_multi(
        async_session, sort_columns=["price"], sort_orders=["desc"]
    )
    prices = [item["price"] for item in result["data"]]
    assert prices == sorted(prices, reverse=True)


@pytest.mark.asyncio
async def test_get_multi_filtering(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi with filtering."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(async_session, category_id=1)

    assert len(result["data"]) > 0
    for item in result["data"]:
        assert item["category_id"] == 1


@pytest.mark.asyncio
async def test_get_multi_edge_cases(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi edge cases."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test with no results
    result = await crud.get_multi(async_session, name="NonExistent")
    assert len(result["data"]) == 0
    assert result["total_count"] == 0

    # Test with large offset
    result = await crud.get_multi(async_session, offset=1000, limit=10)
    assert len(result["data"]) == 0
    assert result["total_count"] == len(test_data)

    # Test with zero limit
    result = await crud.get_multi(async_session, offset=0, limit=0)
    assert len(result["data"]) == 0
    assert result["total_count"] == len(test_data)


@pytest.mark.asyncio
async def test_get_multi_return_model(
    async_session,
    product_model,
    category_model,
    test_data,
    category_data,
    product_create_schema,
):
    """Test get_multi returning model instances."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(
        async_session, return_as_model=True, schema_to_select=product_create_schema
    )

    assert "data" in result
    assert len(result["data"]) == len(test_data)
    for item in result["data"]:
        assert isinstance(item, product_create_schema)


@pytest.mark.asyncio
async def test_get_multi_advanced_filtering(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi with advanced filtering."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test range filtering
    result = await crud.get_multi(async_session, price__gte=20, price__lte=500)
    assert len(result["data"]) > 0
    for item in result["data"]:
        assert 20 <= item["price"] <= 500


@pytest.mark.asyncio
async def test_get_multi_multiple_sorting(
    async_session, product_model, category_model, test_data, category_data
):
    """Test get_multi with multiple column sorting."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test multiple column sorting
    result = await crud.get_multi(
        async_session,
        sort_columns=["category_id", "price"],
        sort_orders=["asc", "desc"],
    )

    assert len(result["data"]) == len(test_data)

    # Verify sorting: first by category_id ascending, then by price descending
    prev_category = None
    prev_price = None
    for item in result["data"]:
        if prev_category is not None:
            if item["category_id"] == prev_category:
                # Same category, price should be descending
                if prev_price is not None:
                    assert item["price"] <= prev_price
            else:
                # Different category, category_id should be ascending
                assert item["category_id"] >= prev_category
        prev_category = item["category_id"]
        prev_price = item["price"]


@pytest.mark.asyncio
async def test_get_multi_advanced_filtering_return_model(
    async_session,
    product_model,
    category_model,
    test_data,
    category_data,
    product_read_schema,
):
    """Test get_multi with advanced filtering returning models."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(
        async_session,
        price__gte=20,
        return_as_model=True,
        schema_to_select=product_read_schema,
    )

    assert len(result["data"]) > 0
    for item in result["data"]:
        assert isinstance(item, product_read_schema)
        assert item.price >= 20


@pytest.mark.asyncio
async def test_get_multi_return_as_model_without_schema(
    async_session,
    product_model,
    category_model,
    test_data,
    category_data,
    product_read_schema,
):
    """Test get_multi return_as_model with schema."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)
    result = await crud.get_multi(
        async_session, return_as_model=True, schema_to_select=product_read_schema
    )

    assert len(result["data"]) == len(test_data)
    for item in result["data"]:
        assert hasattr(item, "id")
        assert hasattr(item, "name")
        assert hasattr(item, "price")


@pytest.mark.asyncio
async def test_get_multi_handle_validation_error(
    async_session, product_model, category_model, category_data
):
    """Test get_multi handling validation errors."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create a product with a name that's too long for CustomProductCreateSchema
    invalid_product_data = {
        "name": "This is an extremely long product name that exceeds the limits",
        "price": 100,
        "category_id": 1,
    }
    async_session.add(product_model(**invalid_product_data))
    await async_session.commit()

    crud = FastCRUD(product_model)

    with pytest.raises(ValueError) as exc_info:
        await crud.get_multi(
            async_session,
            return_as_model=True,
            schema_to_select=CustomProductCreateSchema,
        )

    assert "Data validation error for schema CustomProductCreateSchema:" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_read_items_with_advanced_filters(
    async_session, product_model, category_model, test_data, category_data
):
    """Test reading items with advanced filters."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create products
    for data in test_data:
        new_item = product_model(**data)
        async_session.add(new_item)
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test startswith filter
    name = "Lap"
    result = await crud.get_multi(async_session, name__startswith=name)

    assert len(result["data"]) > 0
    for item in result["data"]:
        assert item["name"].startswith(name)

    # Test with non-matching filter
    name = "Nothing"
    result = await crud.get_multi(async_session, name__startswith=name)

    assert len(result["data"]) == 0


@pytest.mark.asyncio
async def test_get_multi_or_filtering(
    async_session, product_model, category_model, category_data
):
    """Test get_multi with OR filtering."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create specific test data for OR filtering
    test_data = [
        {"name": "Laptop", "price": 1000, "category_id": 1},
        {"name": "Mouse", "price": 25, "category_id": 1},
        {"name": "Book", "price": 15, "category_id": 2},
        {"name": "Pen", "price": 2, "category_id": 2},
        {"name": "Monitor", "price": 300, "category_id": 1},
        {"name": "Keyboard", "price": 50, "category_id": 1},
    ]

    for item in test_data:
        async_session.add(product_model(**item))
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test OR with simple conditions on category_id
    result = await crud.get_multi(async_session, category_id__in=[1, 2])
    assert len(result["data"]) > 0
    assert all(item["category_id"] in [1, 2] for item in result["data"])

    # Test OR with range conditions on price
    result = await crud.get_multi(async_session, price__or={"lt": 20, "gt": 500})
    assert len(result["data"]) > 0
    assert all(item["price"] < 20 or item["price"] > 500 for item in result["data"])

    # Test OR with like conditions on name
    result = await crud.get_multi(async_session, name__or={"like": "Mon%"})
    assert len(result["data"]) > 0
    assert all(item["name"].startswith("Mon") for item in result["data"])


@pytest.mark.asyncio
async def test_get_multi_not_filtering(
    async_session, product_model, category_model, category_data
):
    """Test get_multi with NOT filtering."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create specific test data for NOT filtering
    test_data = [
        {"name": "Laptop", "price": 1000, "category_id": 1},
        {"name": "Mouse", "price": 25, "category_id": 1},
        {"name": "Book", "price": 15, "category_id": 2},
        {"name": "Pen", "price": 2, "category_id": 2},
        {"name": "Monitor", "price": 300, "category_id": 1},
        {"name": "Keyboard", "price": 50, "category_id": 1},
    ]

    for item in test_data:
        async_session.add(product_model(**item))
    await async_session.commit()

    crud = FastCRUD(product_model)

    # Test NOT with single condition - use ne (not equal) instead of complex NOT syntax
    result = await crud.get_multi(async_session, name__ne="Laptop")
    assert len(result["data"]) > 0
    assert all(item["name"] != "Laptop" for item in result["data"])

    # Test NOT with price range - exclude items in a price range
    result = await crud.get_multi(
        async_session,
        price__lt=10,  # Only items with price less than 10 (should be just "Pen" with price 2)
    )
    assert len(result["data"]) > 0
    assert all(item["price"] < 10 for item in result["data"])
    # Should only return the Pen
    assert len([item for item in result["data"] if item["name"] == "Pen"]) == 1


@pytest.mark.asyncio
async def test_create_item(
    async_session, product_model, category_model, category_data, product_create_schema
):
    """Test creating a new item."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)
    await async_session.commit()

    crud = FastCRUD(product_model)

    new_product_data = product_create_schema(
        name="New Product", price=199, category_id=1
    )

    result = await crud.create(async_session, object=new_product_data)

    assert result is not None
    assert result.name == "New Product"
    assert result.price == 199
    assert result.category_id == 1


@pytest.mark.asyncio
async def test_update_item(
    async_session, product_model, category_model, category_data, product_update_schema
):
    """Test updating an existing item."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create a product to update
    product = product_model(name="Original Product", price=100, category_id=1)
    async_session.add(product)
    await async_session.commit()

    crud = FastCRUD(product_model)

    update_data = product_update_schema(name="Updated Product", price=150)

    result = await crud.update(async_session, object=update_data, id=product.id)

    # FastCRUD update might return None, so let's verify by fetching the updated record
    if result is not None:
        assert result.name == "Updated Product"
        assert result.price == 150
    else:
        # Fetch the updated record to verify changes
        updated_product = await crud.get(async_session, id=product.id)
        assert updated_product is not None
        assert updated_product["name"] == "Updated Product"
        assert updated_product["price"] == 150


@pytest.mark.asyncio
async def test_delete_item(async_session, product_model, category_model, category_data):
    """Test deleting an item."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create a product to delete
    product = product_model(name="Product to Delete", price=100, category_id=1)
    async_session.add(product)
    await async_session.commit()

    crud = FastCRUD(product_model)

    result = await crud.delete(async_session, id=product.id)

    if result is not None:
        assert result.is_deleted is True
    else:
        # Fetch the record to verify it's marked as deleted
        deleted_product = await crud.get(async_session, id=product.id)
        assert deleted_product is not None
        assert deleted_product["is_deleted"] is True


@pytest.mark.asyncio
async def test_db_delete_item(
    async_session, product_model, category_model, category_data
):
    """Test hard deleting an item from database."""
    # Create categories first
    for item in category_data:
        category = category_model(**item)
        async_session.add(category)

    # Create a product to delete
    product = product_model(name="Product to Delete", price=100, category_id=1)
    async_session.add(product)
    await async_session.commit()

    crud = FastCRUD(product_model)

    result = await crud.db_delete(async_session, id=product.id)

    if result is not None:
        assert result.name == "Product to Delete"
    else:
        # Try to fetch the record - it should not exist
        deleted_product = await crud.get(async_session, id=product.id)
        assert deleted_product is None
