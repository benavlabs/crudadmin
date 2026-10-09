"""Every admin response carries a Content-Security-Policy that admits only the admin's own scripts.

The templates have no inline script and no event handler attribute, so the
policy needs no ``'unsafe-inline'`` for scripts: markup that reaches a page
through a stored value can't run.
"""

import re
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.admin_interface.middleware import SecurityHeadersMiddleware

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
EVENT_HANDLER_ATTRIBUTE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "csp_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(50))


class NoteSchema(BaseModel):
    text: str


class NoteUpdate(BaseModel):
    text: Optional[str] = None


@pytest.fixture
def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        sessions=SessionConfig(secure_cookies=False),
        track_events=True,
        initial_admin=CREDENTIALS,
    )
    admin.add_view(model=Note, create_schema=NoteSchema, update_schema=NoteUpdate)

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            session.add(Note(id=1, text="<b>hello</b>"))
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(seed)
        yield client


def _login(client) -> None:
    assert client.post("/admin/login", data=CREDENTIALS).status_code == 303


def _directives(response) -> dict[str, str]:
    policy = response.headers["Content-Security-Policy"]
    return {
        part.strip().split(" ", 1)[0]: part.strip()
        for part in policy.split(";")
        if part.strip()
    }


ADMIN_PAGES = [
    "/admin/",
    "/admin/dashboard-content",
    "/admin/Note/",
    "/admin/Note/get_model_list",
    "/admin/Note/create_page",
    "/admin/Note/update/1",
    "/admin/management/sessions",
    "/admin/management/sessions/content",
    "/admin/management/health",
    "/admin/management/health/content",
    "/admin/management/events",
    "/admin/management/events/content",
]


def test_the_login_page_has_the_policy_and_no_inline_script(client):
    response = client.get("/admin/login")

    assert response.status_code == 200
    assert _directives(response)["script-src"] == "script-src 'self'"
    assert INLINE_SCRIPT.search(response.text) is None
    assert EVENT_HANDLER_ATTRIBUTE.search(response.text) is None


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_an_admin_page_has_the_policy_and_no_inline_script(client, path):
    _login(client)

    response = client.get(path)

    assert response.status_code == 200, path
    directives = _directives(response)
    assert directives["script-src"] == "script-src 'self'"
    assert directives["frame-ancestors"] == "frame-ancestors 'none'"
    assert directives["object-src"] == "object-src 'none'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert INLINE_SCRIPT.search(response.text) is None, path
    assert EVENT_HANDLER_ATTRIBUTE.search(response.text) is None, path


def test_the_admin_script_is_served_with_the_headers(client):
    response = client.get("/admin/static/admin.js")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "data-action" in response.text


def test_a_policy_a_route_sets_itself_is_kept():
    async def own_policy() -> HTMLResponse:
        return HTMLResponse(
            "ok", headers={"Content-Security-Policy": "default-src 'none'"}
        )

    app = FastAPI()
    app.add_api_route("/own-policy", own_policy, methods=["GET"])
    app.add_middleware(SecurityHeadersMiddleware)

    response = TestClient(app).get("/own-policy")

    assert response.headers["Content-Security-Policy"] == "default-src 'none'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
