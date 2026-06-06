"""Tests for relationship detection and display (built on native fastcrud)."""

from dataclasses import replace

import pytest
import pytest_asyncio
from fastcrud import FastCRUD
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from crudadmin.admin_interface.relationships import (
    RelationshipType,
    detect_relationships,
    get_relationship_summary,
    load_related_data,
    load_relationship_options,
    resolve_display_field,
)


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "rel_authors"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    books = relationship("Book", back_populates="author")


class Book(Base):
    __tablename__ = "rel_books"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    author_id = Column(Integer, ForeignKey("rel_authors.id"))
    author = relationship("Author", back_populates="books")


class Standalone(Base):
    __tablename__ = "rel_standalone"

    id = Column(Integer, primary_key=True)
    value = Column(String)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as db:
        db.add(Author(id=1, name="Tolkien"))
        db.add(Author(id=2, name="Nobody"))
        db.add(Book(id=1, title="LOTR", author_id=1))
        db.add(Book(id=2, title="Hobbit", author_id=1))
        await db.commit()
        yield db
    await engine.dispose()


def test_detect_has_many():
    rels = detect_relationships(Author)
    assert "books" in rels
    info = rels["books"]
    assert info.relationship_type == RelationshipType.HAS_MANY
    assert info.related_model_name == "Book"
    # No guessing: the label defaults to the related model's primary key.
    assert info.display_field == "id"
    assert info.uselist is True


def test_detect_belongs_to():
    rels = detect_relationships(Book)
    assert "author" in rels
    info = rels["author"]
    assert info.relationship_type == RelationshipType.BELONGS_TO
    assert info.related_model_name == "Author"
    assert info.display_field == "id"
    assert info.foreign_key == "author_id"


def test_detect_no_relationships():
    assert detect_relationships(Standalone) == {}


def test_resolve_display_field_uses_configured():
    assert resolve_display_field(Author, "name") == "name"


def test_resolve_display_field_falls_back_to_pk_when_unset():
    assert resolve_display_field(Author, None) == "id"


def test_resolve_display_field_falls_back_when_not_a_column():
    # A configured field that isn't a real column falls back to the PK.
    assert resolve_display_field(Author, "does_not_exist") == "id"


@pytest.mark.asyncio
async def test_load_related_data_has_many(session):
    rels = detect_relationships(Author)
    crud = FastCRUD(Author)
    books = await load_related_data(crud, session, "id", 1, rels["books"])
    assert len(books) == 2
    assert {b["title"] for b in books} == {"LOTR", "Hobbit"}


@pytest.mark.asyncio
async def test_load_related_data_belongs_to(session):
    rels = detect_relationships(Book)
    crud = FastCRUD(Book)
    author = await load_related_data(crud, session, "id", 1, rels["author"])
    assert len(author) == 1
    assert author[0]["name"] == "Tolkien"


@pytest.mark.asyncio
async def test_load_related_data_empty(session):
    """An author with no books returns an empty list."""
    rels = detect_relationships(Author)
    crud = FastCRUD(Author)
    books = await load_related_data(crud, session, "id", 2, rels["books"])
    assert books == []


@pytest.mark.asyncio
async def test_load_related_data_respects_limit(session):
    rels = detect_relationships(Author)
    crud = FastCRUD(Author)
    books = await load_related_data(crud, session, "id", 1, rels["books"], limit=1)
    assert len(books) == 1


@pytest.mark.asyncio
async def test_load_relationship_options(session):
    rels = detect_relationships(Book)
    # Label resolved to a configured column -> options use it.
    author_rel = replace(
        rels["author"], display_field=resolve_display_field(Author, "name")
    )
    options = await load_relationship_options(session, author_rel)
    assert {o["display_name"] for o in options} == {"Tolkien", "Nobody"}
    assert all("id" in o for o in options)


@pytest.mark.asyncio
async def test_load_relationship_options_pk_fallback(session):
    """With no configured label, options fall back to the primary key."""
    rels = detect_relationships(Book)
    options = await load_relationship_options(session, rels["author"])
    assert {o["display_name"] for o in options} == {"1", "2"}


def test_summary_belongs_to():
    rels = detect_relationships(Book)
    author_rel = replace(rels["author"], display_field="name")
    summary = get_relationship_summary({}, author_rel, [{"id": 1, "name": "Tolkien"}])
    assert summary["count"] == 1
    assert summary["display_value"] == "Tolkien"


def test_summary_has_many():
    rels = detect_relationships(Author)
    data = [{"id": i, "title": f"Book {i}"} for i in range(1, 6)]
    summary = get_relationship_summary({}, rels["books"], data)
    assert summary["count"] == 5
    assert summary["display_value"] == "5 items"
    assert summary["preview"].endswith("...")


def test_summary_empty():
    rels = detect_relationships(Author)
    summary = get_relationship_summary({}, rels["books"], [])
    assert summary["count"] == 0
    assert summary["items"] == []
