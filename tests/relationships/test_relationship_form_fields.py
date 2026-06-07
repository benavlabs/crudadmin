"""Foreign-key form fields render as relationship dropdowns (issue #53)."""

from unittest.mock import Mock

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from crudadmin.admin_interface.helper import _get_form_fields_from_schema
from crudadmin.admin_interface.model_view import ModelView
from crudadmin.core.db import DatabaseConfig


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "fkf_authors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    books = relationship("Book", back_populates="author")


class Book(Base):
    __tablename__ = "fkf_books"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    author_id = Column(Integer, ForeignKey("fkf_authors.id"))
    author = relationship("Author", back_populates="books")


class BookCreate(BaseModel):
    title: str
    author_id: int


class BookUpdate(BaseModel):
    title: str
    author_id: int


def _fresh_admin_base() -> type:
    """A unique admin base per DatabaseConfig to avoid table-redefinition clashes."""

    class AdminBase(DeclarativeBase):
        pass

    return AdminBase


def _admin_site_stub() -> Mock:
    """Minimal admin_site stand-in for building a ModelView.

    Provides the attributes setup_routes touches; empty ``models`` so the
    display-field resolver falls back to the primary key.
    """
    site = Mock()
    site.models = {}
    site.admin_authentication.get_current_user.return_value = lambda: None
    return site


@pytest_asyncio.fixture
async def seeded_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as db:
        db.add_all([Author(id=1, name="Tolkien"), Author(id=2, name="Rowling")])
        await db.commit()
        yield db
    await engine.dispose()


def _make_book_view() -> ModelView:
    async def _dummy_session():  # pragma: no cover - never invoked in this test
        yield None

    db_config = DatabaseConfig(
        base=_fresh_admin_base(),
        session=_dummy_session,
        admin_db_url="sqlite+aiosqlite:///:memory:",
    )
    return ModelView(
        database_config=db_config,
        templates=Mock(),
        model=Book,
        create_schema=BookCreate,
        update_schema=BookUpdate,
        admin_site=_admin_site_stub(),
        allowed_actions={"view", "create", "update", "delete"},
    )


@pytest.mark.asyncio
async def test_fk_field_becomes_relationship_select(seeded_db):
    view = _make_book_view()
    form_fields = _get_form_fields_from_schema(BookCreate)

    await view._apply_relationship_form_fields(form_fields, seeded_db)

    by_name = {f["name"]: f for f in form_fields}
    author_field = by_name["author_id"]
    assert author_field["type"] == "relationship_select"
    assert author_field["related_model_name"] == "Author"
    assert len(author_field["options"]) == 2
    assert all("id" in o and "display_name" in o for o in author_field["options"])

    # A non-FK field is left untouched.
    assert by_name["title"]["type"] != "relationship_select"


@pytest.mark.asyncio
async def test_no_fk_fields_leaves_form_unchanged(seeded_db):
    """A model with no foreign keys gets no relationship selects."""

    async def _dummy_session():  # pragma: no cover
        yield None

    db_config = DatabaseConfig(
        base=_fresh_admin_base(),
        session=_dummy_session,
        admin_db_url="sqlite+aiosqlite:///:memory:",
    )
    view = ModelView(
        database_config=db_config,
        templates=Mock(),
        model=Author,
        create_schema=type(
            "AuthorCreate", (BaseModel,), {"__annotations__": {"name": str}}
        ),
        update_schema=type(
            "AuthorUpdate", (BaseModel,), {"__annotations__": {"name": str}}
        ),
        admin_site=_admin_site_stub(),
        allowed_actions={"view", "create", "update", "delete"},
    )
    form_fields = _get_form_fields_from_schema(view.create_schema)
    await view._apply_relationship_form_fields(form_fields, seeded_db)

    assert all(f["type"] != "relationship_select" for f in form_fields)
