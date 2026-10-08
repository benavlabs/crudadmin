"""Regression tests for the AdminAuthMiddleware path allowlist.

The middleware used to skip authentication for any path *ending* in ``/login``
and any path *containing* ``/static/``, so URLs like
``/admin/Article/update/login`` or ``/admin/Author/related/static/books``
reached admin endpoints with no session at all.

Reported by Ubaid Ur Rehman, found with shadowaudit
(https://gitlab.com/theredhacker0345/shadowaudit).
"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from crudadmin import CRUDAdmin


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "bypass_articles"
    slug = Column(String, primary_key=True)
    body = Column(String)


class Author(Base):
    __tablename__ = "bypass_authors"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    books = relationship("BypassBook", back_populates="author", lazy="selectin")


class BypassBook(Base):
    __tablename__ = "bypass_books"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    author_id = Column(Integer, ForeignKey("bypass_authors.id"))
    author = relationship("Author", back_populates="books", lazy="selectin")


class ArticleCreate(BaseModel):
    slug: str
    body: str


class ArticleUpdate(BaseModel):
    body: str


class AuthorCreate(BaseModel):
    name: str


class AuthorUpdate(BaseModel):
    name: str


SECRET_BODY = "article-body-that-must-not-leak"


@pytest.fixture(scope="module")
def admin_client(tmp_path_factory):
    """A running admin app with a record whose primary key is literally 'login'.

    Module-scoped: CRUDAdmin registers its admin models on a shared declarative
    base, so only one instance can be built per process.
    """
    tmp_path = tmp_path_factory.mktemp("bypass")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_factory() as session:
            yield session

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        secure_cookies=False,
    )
    admin.add_view(
        model=Article, create_schema=ArticleCreate, update_schema=ArticleUpdate
    )
    admin.add_view(
        model=Author,
        create_schema=AuthorCreate,
        update_schema=AuthorUpdate,
        display_field="name",
    )

    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(Article(slug="login", body=SECRET_BODY))
            session.add(Author(id=1, name="author-name"))
            session.add(BypassBook(id=1, title="book-title", author_id=1))
            await session.commit()
        await admin.initialize()
        yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/admin", admin.app)
    # Mounted a second time at a path that does not match the configured mount_path.
    # The middleware's outer prefix check does not match here and lets the request
    # through, which leaves the per-route auth dependencies as the only defense.
    app.mount("/backoffice", admin.app)

    with TestClient(
        app, follow_redirects=False, raise_server_exceptions=False
    ) as client:
        yield client


@pytest.mark.parametrize(
    "path",
    [
        "/admin/Article/update/login",
        "/admin/Author/update/login",
        "/admin/Author/related/1/login",
        "/admin/Author/related/static/books",
        "/admin/Author/relationship-options/login",
    ],
)
def test_crafted_path_does_not_bypass_auth(admin_client, path):
    """A path that merely ends in /login or contains /static/ must still 401/redirect."""
    response = admin_client.get(path)

    assert response.status_code in (303, 401), response.status_code
    if response.status_code == 303:
        assert response.headers["location"].startswith("/admin/login")
    assert SECRET_BODY not in response.text


def test_crafted_login_path_leaks_no_record_data(admin_client):
    """The string-PK record keyed 'login' must not be rendered to an anonymous user."""
    response = admin_client.get("/admin/Article/update/login")

    assert SECRET_BODY not in response.text


def test_real_login_page_is_still_reachable(admin_client):
    """The genuine login page stays open to unauthenticated visitors."""
    response = admin_client.get("/admin/login")

    assert response.status_code == 200
    assert "<form" in response.text.lower()


def test_login_page_reachable_with_trailing_slash(admin_client):
    """A trailing slash on the login path must not force a redirect loop."""
    response = admin_client.get("/admin/login/")

    assert response.status_code != 303


@pytest.mark.parametrize(
    "path",
    [
        "/backoffice/",
        "/backoffice/Article/",
        "/backoffice/Article/update/login",
        "/backoffice/management/health",
    ],
)
def test_route_dependencies_hold_when_the_middleware_is_skipped(admin_client, path):
    """Mounting the admin somewhere other than its ``mount_path`` exposes nothing.

    The middleware used to skip requests whose path didn't start with the
    configured prefix, leaving the per-route dependencies as the only defense.
    It now authenticates every request it sees, and the route dependencies still
    back it up (see the structural test below).
    """
    response = admin_client.get(path)

    assert response.status_code in (303, 401), response.status_code
    if response.status_code == 303:
        assert "/login" in response.headers["location"]
    assert SECRET_BODY not in response.text
