"""Regression tests for the IP allowlist and HTTPS redirect middlewares.

Both used to act only on paths starting with the literal ``/admin``, so an
admin mounted anywhere else had no IP restriction and no HTTPS redirect.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import DeclarativeBase

from crudadmin import AccessConfig, CRUDAdmin, SessionConfig
from crudadmin.core.db import DatabaseConfig

ALLOWED_IP = "10.9.9.9"
FOREIGN_IP = "1.2.3.4"

# (mount_path given to CRUDAdmin, path the app is mounted at, login URL)
MOUNTS = [
    ("/admin", "/admin", "/admin/login"),
    ("/backoffice", "/backoffice", "/backoffice/login"),
    ("/", "", "/login"),
]


async def _get_session():
    yield None


def _build_app(tmp_path, mount_path, mount_at, **admin_kwargs):
    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        mount_path=mount_path,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        sessions=SessionConfig(secure_cookies=False),
        **admin_kwargs,
    )
    app = FastAPI()
    app.mount(mount_at or "/", admin.app)
    return app


@pytest.mark.parametrize("mount_path, mount_at, login_url", MOUNTS)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_allowlist_rejects_a_foreign_ip_on_every_mount(
    tmp_path, mount_path, mount_at, login_url, method
):
    app = _build_app(
        tmp_path, mount_path, mount_at, access=AccessConfig(allowed_ips=[ALLOWED_IP])
    )
    client = TestClient(app, follow_redirects=False, client=(FOREIGN_IP, 50000))

    response = client.request(
        method, login_url, data={"username": "a", "password": "b"}
    )

    assert response.status_code == 403, (response.status_code, response.text)
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("mount_path, mount_at, login_url", MOUNTS)
def test_allowlist_admits_an_allowed_ip(tmp_path, mount_path, mount_at, login_url):
    app = _build_app(
        tmp_path, mount_path, mount_at, access=AccessConfig(allowed_ips=[ALLOWED_IP])
    )
    client = TestClient(app, follow_redirects=False, client=(ALLOWED_IP, 50000))

    response = client.get(login_url)

    assert response.status_code == 200


@pytest.mark.parametrize("mount_path, mount_at, login_url", MOUNTS)
def test_allowlist_admits_an_allowed_network(tmp_path, mount_path, mount_at, login_url):
    app = _build_app(
        tmp_path,
        mount_path,
        mount_at,
        access=AccessConfig(allowed_networks=["10.9.0.0/16"]),
    )
    client = TestClient(app, follow_redirects=False, client=(ALLOWED_IP, 50000))

    assert client.get(login_url).status_code == 200


@pytest.mark.parametrize("mount_path, mount_at, login_url", MOUNTS)
def test_https_redirect_applies_on_every_mount(
    tmp_path, mount_path, mount_at, login_url
):
    app = _build_app(
        tmp_path, mount_path, mount_at, access=AccessConfig(enforce_https=True)
    )
    client = TestClient(app, base_url="http://example.com", follow_redirects=False)

    response = client.get(login_url, params={"next": "1"})

    assert response.status_code == 301
    assert response.headers["location"] == f"https://example.com{login_url}?next=1"


@pytest.mark.parametrize("https_port", [8443, 9000])
def test_https_redirect_uses_the_configured_port(tmp_path, https_port):
    app = _build_app(
        tmp_path,
        "/admin",
        "/admin",
        access=AccessConfig(enforce_https=True, https_port=https_port),
    )
    client = TestClient(app, base_url="http://example.com:8000", follow_redirects=False)

    response = client.get("/admin/login")

    assert response.status_code == 301
    assert (
        response.headers["location"] == f"https://example.com:{https_port}/admin/login"
    )


def test_https_redirect_drops_the_http_port_for_443(tmp_path):
    app = _build_app(
        tmp_path, "/admin", "/admin", access=AccessConfig(enforce_https=True)
    )
    client = TestClient(app, base_url="http://example.com:8000", follow_redirects=False)

    response = client.get("/admin/login")

    assert response.headers["location"] == "https://example.com/admin/login"


def test_https_requests_are_not_redirected(tmp_path):
    app = _build_app(
        tmp_path, "/admin", "/admin", access=AccessConfig(enforce_https=True)
    )
    client = TestClient(app, base_url="https://example.com", follow_redirects=False)

    assert client.get("/admin/login").status_code == 200
