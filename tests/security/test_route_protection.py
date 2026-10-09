"""Every admin route requires a logged-in admin, except login, logout and static files.

Routes reach the app through one method that attaches the authentication
dependency, so a new route is protected without declaring it. These tests send
a request to every route of the admin app with the login-redirect middleware
switched off, so the route dependency is the only thing standing in the way,
and check each request is refused. The routes are read from the app itself
rather than from the routers crudadmin mounted, so a route added to the app any
other way is caught too, as is a dependency registered uncalled
(``Depends(factory)`` instead of ``Depends(factory())``).
"""

import re
from typing import Any, Iterable, Iterator, Optional

import pytest
from crudauth import get_password_hash
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.routing import Mount

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.admin_interface.middleware.auth import AdminAuthMiddleware
from crudadmin.core.db import DatabaseConfig

STAFF = {"username": "staff", "password": "staff-password-123"}


class Base(DeclarativeBase):
    pass


class Widget(Base):
    __tablename__ = "protection_widgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class WidgetCreate(BaseModel):
    name: str


class WidgetUpdate(BaseModel):
    name: Optional[str] = None


async def _get_session():
    yield None


def _admin(tmp_path, **kwargs) -> CRUDAdmin:
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
        sessions=SessionConfig(secure_cookies=False),
        track_events=True,
        **kwargs,
    )
    admin.add_view(model=Widget, create_schema=WidgetCreate, update_schema=WidgetUpdate)
    return admin


def _without_login_redirect(admin: CRUDAdmin) -> None:
    admin.app.user_middleware = [
        middleware
        for middleware in admin.app.user_middleware
        if middleware.cls is not AdminAuthMiddleware
    ]


def _methods_and_paths(routes: Iterable[Any]) -> Iterator[tuple[str, str]]:
    """Yield the method and full path of every route, including those of included routers.

    FastAPI 0.142 and later keep an included router as one entry whose
    ``effective_route_contexts()`` lists its routes with their full paths;
    earlier versions copy each route onto the app.
    """
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from _methods_and_paths(route.effective_route_contexts())
        elif isinstance(route, Mount):
            yield "GET", route.path + "/"
        else:
            path: str = route.path
            for method in sorted(getattr(route, "methods", None) or {"GET"}):
                yield method, path


def _public_requests(admin: CRUDAdmin) -> set[tuple[str, str]]:
    return set(_methods_and_paths(admin.admin_site.public_router.routes))


def _app_requests(admin: CRUDAdmin) -> list[tuple[str, str]]:
    """A request for every route of the admin app but the public ones and static files."""
    public = _public_requests(admin)
    static = "/static/"
    return [
        (method, admin.paths.prefix + re.sub(r"\{[^}]+\}", "1", path))
        for method, path in _methods_and_paths(admin.app.routes)
        if (method, path) not in public and path != static
    ]


def _admitted_requests(
    admin: CRUDAdmin, client: TestClient
) -> list[tuple[str, str, int]]:
    """Send every request from [_app_requests][] anonymously; return those not sent to login."""
    admitted = []
    for method, path in _app_requests(admin):
        response = client.request(method, path)
        refused = response.status_code == 303 and response.headers.get(
            "location", ""
        ).startswith(admin.paths.login)
        if not refused:
            admitted.append((method, path, response.status_code))
    return admitted


def _superuser_requests(admin: CRUDAdmin) -> list[tuple[str, str]]:
    return [
        (method, admin.paths.prefix + re.sub(r"\{[^}]+\}", "1", mounted.prefix + path))
        for mounted in admin.protected_routers
        if mounted.superuser
        for method, path in _methods_and_paths(mounted.router.routes)
    ]


@pytest.fixture
def app_client(tmp_path):
    admin = _admin(tmp_path)
    _without_login_redirect(admin)
    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(
        app,
        follow_redirects=False,
        raise_server_exceptions=False,
        client=("127.0.0.1", 50000),
    ) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)
        yield admin, client


def test_every_protected_route_refuses_an_anonymous_request(app_client):
    admin, client = app_client
    assert len(_app_requests(admin)) > 15

    assert _admitted_requests(admin, client) == []


def test_a_route_added_straight_to_the_app_is_reported(app_client):
    admin, client = app_client

    async def stray() -> dict[str, str]:
        return {"stray": "reachable"}

    admin.app.add_api_route("/stray/{item_id}", stray, methods=["GET"])

    assert _admitted_requests(admin, client) == [("GET", "/admin/stray/1", 200)]


def test_admin_accounts_refuse_a_non_superuser(app_client):
    admin, client = app_client
    user_model = admin.db_config.AdminUser

    async def add_staff():
        async with admin.db_config.admin_session_maker() as db:
            db.add(
                user_model(
                    username=STAFF["username"],
                    hashed_password=get_password_hash(STAFF["password"]),
                )
            )
            await db.commit()

    assert client.portal is not None
    client.portal.call(add_staff)
    assert client.post("/admin/login", data=STAFF).status_code == 303

    superuser_gets = [
        (method, path) for method, path in _superuser_requests(admin) if method == "GET"
    ]
    assert superuser_gets
    for method, path in superuser_gets:
        assert client.request(method, path).status_code == 403, path


def test_login_and_logout_are_the_only_public_routes(tmp_path):
    admin = _admin(tmp_path)

    public = _public_requests(admin)

    assert public == {("GET", "/login"), ("POST", "/login"), ("POST", "/logout")}


def test_routes_are_mounted_when_setup_runs_after_construction(tmp_path):
    """With setup_on_initialization=False, a later setup() mounts protected routes."""

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
        setup_on_initialization=False,
    )
    assert admin.protected_routers == []

    admin.setup()
    admin.add_view(model=Widget, create_schema=WidgetCreate, update_schema=WidgetUpdate)

    prefixes = {mounted.prefix for mounted in admin.protected_routers}
    assert {"", "/Widget", "/AdminUser"} <= prefixes
    client = TestClient(admin.app, follow_redirects=False)
    assert client.get("/").status_code == 303


def test_a_second_setup_mounts_nothing_again(tmp_path):
    admin = _admin(tmp_path)
    routers = list(admin.protected_routers)
    requests = _app_requests(admin)

    admin.setup()

    assert admin.protected_routers == routers
    assert _app_requests(admin) == requests


@pytest.mark.parametrize(
    "mount_path, mounted_at", [("/backoffice", "/backoffice"), ("/", "")]
)
def test_protection_does_not_depend_on_the_mount_path(tmp_path, mount_path, mounted_at):
    admin = _admin(tmp_path, mount_path=mount_path)
    _without_login_redirect(admin)
    app = FastAPI()
    app.mount(mounted_at or "/", admin.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 1)) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)
        assert len(_app_requests(admin)) > 15
        assert _admitted_requests(admin, client) == []
