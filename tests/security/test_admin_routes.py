"""Regression tests for authenticated admin routes.

Covers routes that must not exist, and list-page output that must not let
request or record data reach a JavaScript context.
"""

import re
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.core.db import DatabaseConfig


class Base(DeclarativeBase):
    pass


class RoutesAdminBase(DeclarativeBase):
    """Its own admin base, so this admin can coexist with others in the test run."""


class Note(Base):
    __tablename__ = "routes_notes"
    id = Column(Integer, primary_key=True)
    text = Column(String)


class Tag(Base):
    __tablename__ = "routes_tags"
    slug = Column(String, primary_key=True)
    label = Column(String)
    links = relationship("TagLink", back_populates="tag", lazy="selectin")


class TagLink(Base):
    __tablename__ = "routes_tag_links"
    id = Column(Integer, primary_key=True)
    tag_slug = Column(String, ForeignKey("routes_tags.slug"))
    tag = relationship("Tag", back_populates="links", lazy="selectin")


class NoteCreate(BaseModel):
    text: str


class NoteUpdate(BaseModel):
    text: str


class TagCreate(BaseModel):
    slug: str
    label: str


class TagUpdate(BaseModel):
    label: str


QUOTED_SLUG = "it's-a-trap"
NOTE_COUNT = 12
XSS_SORT_ORDER = 'x"+alert(document.cookie)+"'


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A logged-in client for an admin with a view-only model and a string-PK model."""
    tmp_path = tmp_path_factory.mktemp("routes")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_factory() as session:
            yield session

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=RoutesAdminBase,
            session=get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        sessions=SessionConfig(secure_cookies=False),
        initial_admin={"username": "admin", "password": "correct-horse-battery"},
    )
    admin.add_view(
        model=Note,
        create_schema=NoteCreate,
        update_schema=NoteUpdate,
        allowed_actions={"view"},
    )
    admin.add_view(model=Tag, create_schema=TagCreate, update_schema=TagUpdate)

    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(Note(id=1, text="keep me"))
            for i in range(2, NOTE_COUNT + 1):
                session.add(Note(id=i, text=f"note {i:02d}"))
            session.add(Tag(slug=QUOTED_SLUG, label="quoted"))
            await session.commit()
        await admin.initialize()
        yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/admin", admin.app)

    with TestClient(
        app,
        follow_redirects=False,
        raise_server_exceptions=False,
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.post(
            "/admin/login",
            data={"username": "admin", "password": "correct-horse-battery"},
        )
        assert response.status_code == 303, response.text
        yield client


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/admin/AdminUser/crud/1"),
        ("GET", "/admin/AdminUser/crud"),
        ("POST", "/admin/AdminUser/crud"),
        ("PATCH", "/admin/AdminUser/crud/1"),
        ("DELETE", "/admin/AdminUser/crud/1"),
        ("GET", "/admin/Note/crud/1"),
        ("PATCH", "/admin/Note/crud/1"),
        ("DELETE", "/admin/Note/crud/1"),
    ],
)
def test_generic_crud_api_is_not_exposed(client, method, path):
    """No REST API is mounted beside the admin views.

    It used to be generated for every view, ignoring ``allowed_actions`` and
    returning every column, including ``hashed_password``.
    """
    response = client.request(method, path, json={})

    assert response.status_code in (404, 405), (response.status_code, response.text)
    assert "hashed_password" not in response.text


def test_view_only_model_was_not_modified(client):
    """The view-only record survives the attempted PATCH and DELETE above."""
    response = client.get("/admin/Note/get_model_list")

    assert response.status_code == 200
    assert "keep me" in response.text


def test_list_page_sends_no_javascript_hx_vals(client):
    """``hx-vals`` must be plain JSON: a ``js:`` prefix makes htmx evaluate it."""
    for path in ("/admin/Note/", "/admin/Tag/", "/admin/Note/get_model_list"):
        response = client.get(path, params={"sort_by": "text"})

        assert response.status_code == 200, path
        assert "js:" not in response.text, path


def test_sort_order_from_the_query_string_never_reaches_the_page(client):
    """A crafted ``sort_order`` is normalised to asc/desc on the server."""
    response = client.get(
        "/admin/Note/", params={"sort_by": "text", "sort_order": XSS_SORT_ORDER}
    )

    assert response.status_code == 200
    assert "alert(document.cookie)" not in response.text


def test_unknown_sort_column_is_ignored(client):
    response = client.get(
        "/admin/Note/get_model_list", params={"sort_by": 'x"onmouseover="alert(1)'}
    )

    assert response.status_code == 200
    assert "onmouseover" not in response.text
    assert "keep me" in response.text


def test_valid_sort_still_applies(client):
    response = client.get(
        "/admin/Note/get_model_list",
        params={"sort_by": "text", "sort_order": "desc", "rows-per-page-select": "20"},
    )

    assert response.status_code == 200
    assert response.text.index("note 12") < response.text.index("note 02")


def test_string_primary_key_is_not_written_into_javascript(client):
    """The list has no inline script: the row id is only an escaped attribute."""
    response = client.get("/admin/Tag/get_model_list")

    assert response.status_code == 200
    assert 'data-action="toggle-row"' in response.text
    assert re.search(r"\son[a-z]+=", response.text) is None
    assert "<script" not in response.text
    assert QUOTED_SLUG not in response.text
    assert 'data-row-id="it&#39;s-a-trap"' in response.text


@pytest.mark.parametrize("rows", ["100000", "0", "-5", "abc"])
def test_rows_per_page_is_limited_to_the_offered_sizes(client, rows):
    response = client.get(
        "/admin/Note/get_model_list", params={"rows-per-page-select": rows}
    )

    assert response.status_code == 200
    assert f"Showing 1 to 10 of {NOTE_COUNT} entries" in response.text


def test_offered_rows_per_page_is_respected(client):
    response = client.get(
        "/admin/Note/get_model_list", params={"rows-per-page-select": "20"}
    )

    assert f"Showing 1 to {NOTE_COUNT} of {NOTE_COUNT} entries" in response.text


def test_session_list_does_not_show_session_ids(client):
    session_id = client.cookies.get("crudadmin_session")
    assert session_id

    response = client.get("/admin/management/sessions/content")

    assert response.status_code == 200
    assert "This session" in response.text
    assert session_id not in response.text


def test_the_old_admin_session_table_view_is_gone(client):
    for path in ("/admin/AdminSession/", "/admin/AdminSession/get_model_list"):
        assert client.get(path).status_code == 404, path


def test_admin_user_list_does_not_show_password_hashes(client):
    for path in ("/admin/AdminUser/", "/admin/AdminUser/get_model_list"):
        response = client.get(path)

        assert response.status_code == 200, path
        assert "hashed_password" not in response.text, path
        assert "$2b$" not in response.text, path
        assert "admin" in response.text, path


@pytest.mark.parametrize(
    "method, path, kwargs",
    [
        ("POST", "/admin/Tag/form_create", {"data": {"slug": "x", "label": "y"}}),
        ("POST", "/admin/Tag/form_update/it's-a-trap", {"data": {"label": "z"}}),
        ("DELETE", "/admin/Tag/bulk-delete", {"json": {"ids": ["it's-a-trap"]}}),
    ],
)
def test_model_writes_need_the_csrf_header(client, method, path, kwargs):
    response = client.request(method, path, **kwargs)

    assert response.status_code == 403, (response.status_code, response.text)

    listing = client.get("/admin/Tag/get_model_list")
    assert "quoted" in listing.text
