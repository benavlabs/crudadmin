"""Several CRUDAdmin instances run side by side in one process.

Each instance that builds its own ``DatabaseConfig`` gets a declarative base of
its own, so the admin tables don't collide, and each keeps its own admins,
sessions and models. Instances that share one session store keep their keys
apart by secret key and mount path.
"""

from typing import Optional

import pytest
from crudauth.ratelimit import DatabaseRateLimiterBackend
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.admin_interface.auth import storage_key_prefix

SESSION_COOKIE = "crudadmin_session"


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "multi_articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50))


class Ticket(Base):
    __tablename__ = "multi_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject: Mapped[str] = mapped_column(String(50))


class ArticleCreate(BaseModel):
    title: str


class ArticleUpdate(BaseModel):
    title: Optional[str] = None


class TicketCreate(BaseModel):
    subject: str


class TicketUpdate(BaseModel):
    subject: Optional[str] = None


@pytest.fixture
def app_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    return get_session, create_tables


async def _no_session():
    yield None


def _admin(tmp_path, name: str, track_events: bool = True, session=_no_session):
    return CRUDAdmin(
        session=session,
        SECRET_KEY=name * 32,
        mount_path=f"/{name}",
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/{name}.db",
        sessions=SessionConfig(secure_cookies=False),
        track_events=track_events,
        initial_admin={"username": name, "password": f"{name}-password-123"},
    )


def _login(client: TestClient, name: str):
    return client.post(
        f"/{name}/login",
        data={"username": name, "password": f"{name}-password-123"},
    )


def test_two_admins_built_without_a_db_config_get_their_own_tables(tmp_path):
    content = _admin(tmp_path, "content")
    support = _admin(tmp_path, "support")

    for model_name in ("AdminUser", "AdminEventLog", "AdminAuditLog"):
        assert getattr(content.db_config, model_name) is not getattr(
            support.db_config, model_name
        )
    assert content.db_config.base is not support.db_config.base


def test_two_admins_serve_their_own_models_and_admins(tmp_path, app_database):
    get_session, create_tables = app_database
    content = _admin(tmp_path, "content", session=get_session)
    content.add_view(
        model=Article, create_schema=ArticleCreate, update_schema=ArticleUpdate
    )
    support = _admin(tmp_path, "support", track_events=False, session=get_session)
    support.add_view(
        model=Ticket, create_schema=TicketCreate, update_schema=TicketUpdate
    )

    app = FastAPI()
    app.mount("/content", content.app)
    app.mount("/support", support.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(create_tables)
        client.portal.call(content.initialize)
        client.portal.call(support.initialize)

        assert (
            client.post(
                "/support/login",
                data={"username": "content", "password": "content-password-123"},
            ).status_code
            == 401
        )
        assert _login(client, "content").status_code == 303
        assert _login(client, "support").status_code == 303

        assert client.get("/content/Article/").status_code == 200
        assert client.get("/content/Ticket/").status_code == 404
        assert client.get("/support/Ticket/").status_code == 200
        assert client.get("/support/Article/").status_code == 404


def test_a_session_from_one_admin_is_refused_by_the_other(tmp_path):
    content = _admin(tmp_path, "content")
    support = _admin(tmp_path, "support")
    app = FastAPI()
    app.mount("/content", content.app)
    app.mount("/support", support.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(content.initialize)
        client.portal.call(support.initialize)
        assert _login(client, "content").status_code == 303
        content_session = client.cookies[SESSION_COOKIE]
        client.cookies.clear()

        response = client.get(
            "/support/", headers={"Cookie": f"{SESSION_COOKIE}={content_session}"}
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/support/login")


def _admin_on_shared_store(tmp_path, mount_path: str) -> CRUDAdmin:
    return CRUDAdmin(
        session=_no_session,
        SECRET_KEY="s" * 32,
        mount_path=mount_path,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/shared.db",
        sessions=SessionConfig(backend="database", secure_cookies=False),
        initial_admin={"username": "admin", "password": "admin-password-123"},
    )


def test_admins_sharing_a_session_store_keep_their_sessions_apart(tmp_path):
    content = _admin_on_shared_store(tmp_path, "/content")
    support = _admin_on_shared_store(tmp_path, "/support")
    app = FastAPI()
    app.mount("/content", content.app)
    app.mount("/support", support.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(content.initialize)
        client.portal.call(support.initialize)
        login = client.post(
            "/content/login",
            data={"username": "admin", "password": "admin-password-123"},
        )
        assert login.status_code == 303
        content_session = client.cookies[SESSION_COOKIE]
        client.cookies.clear()

        response = client.get(
            "/support/", headers={"Cookie": f"{SESSION_COOKIE}={content_session}"}
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/support/login")


def test_stored_keys_are_namespaced_by_secret_key_and_mount_path():
    prefix = storage_key_prefix("a" * 32, "/admin")

    assert prefix.startswith("crudadmin:") and prefix.endswith("/admin:")
    assert "a" * 12 not in prefix
    assert storage_key_prefix("a" * 32, "/admin") == prefix
    assert storage_key_prefix("b" * 32, "/admin") != prefix
    assert storage_key_prefix("a" * 32, "/other") != prefix
    assert storage_key_prefix("a" * 32, "") != prefix


def test_every_store_uses_the_admin_key_prefix(tmp_path):
    admin = CRUDAdmin(
        session=_no_session,
        SECRET_KEY="k" * 32,
        mount_path="/backoffice",
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        sessions=SessionConfig(backend="database"),
    )
    authentication = admin.admin_authentication
    expected = storage_key_prefix("k" * 32, "/backoffice")
    limiter = authentication.auth.runtime.rate_limiter
    assert isinstance(limiter, DatabaseRateLimiterBackend)

    assert authentication.key_prefix == expected
    assert authentication.session_transport.storage_prefix == f"{expected}session:"
    assert authentication.session_transport.csrf_storage_prefix == f"{expected}csrf:"
    assert limiter.prefix == f"{expected}rl:"
