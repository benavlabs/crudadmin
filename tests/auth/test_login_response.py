"""Regression tests for the login response: cookie lifetime and error text."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin
from crudadmin.core.db import DatabaseConfig
from crudadmin.core.tokens import session_handle

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}


async def _get_session():
    yield None


@pytest.fixture
def client(tmp_path):
    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        secure_cookies=False,
        session_timeout_minutes=480,
        initial_admin=CREDENTIALS,
    )

    app = FastAPI()
    app.mount("/admin", admin.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        client.portal.call(admin.initialize)
        yield client


def test_session_cookie_has_no_fixed_lifetime(client):
    """The cookie used to expire after 30 minutes whatever the session timeout.

    Without Max-Age it lasts for the browser session, and the server-side
    timeout, which slides with activity, decides when the user is logged out.
    """
    response = client.post("/admin/login", data=CREDENTIALS)

    assert response.status_code == 303
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("session_id="))
    assert "max-age" not in session_cookie.lower()
    assert "expires" not in session_cookie.lower()


def test_login_failure_does_not_show_exception_text(client):
    """A failure while creating the session must not echo the exception."""
    response = client.post(
        "/admin/login",
        data=CREDENTIALS,
        headers={"X-Forwarded-For": "not-an-ip"},
    )

    assert response.status_code == 200
    assert "An error occurred during login" in response.text
    assert "validation error" not in response.text
    assert "not-an-ip" not in response.text


def test_session_id_never_reaches_the_logs(client, caplog):
    """A session id is a bearer credential; logs may only carry its handle."""
    caplog.set_level(logging.DEBUG)

    response = client.post("/admin/login", data=CREDENTIALS)
    session_id = response.cookies["session_id"]
    csrf_token = response.cookies["csrf_token"]
    client.get("/admin/")
    client.get("/admin/AdminSession/")

    assert session_id not in caplog.text
    assert csrf_token not in caplog.text
    assert session_handle(session_id) in caplog.text
