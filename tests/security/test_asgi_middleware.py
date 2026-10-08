"""The admin's middleware is plain ASGI and adjusts responses as they are sent.

``BaseHTTPMiddleware`` runs the app in a separate task and wraps its response,
which breaks context variables and buffers streamed responses. The admin's
middleware calls the app directly and rewrites only the response's start
message: no-cache headers on pages, and a 204 naming the target for a redirect
answering an admin.js form submission.
"""

from typing import Any

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message, Receive, Scope, Send

from crudadmin import CRUDAdmin
from crudadmin.admin_interface.middleware import (
    AdminAuthMiddleware,
    HTTPSRedirectMiddleware,
    IPRestrictionMiddleware,
)

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
FETCH = {"X-CRUDAdmin-Fetch": "1"}


async def _no_session():
    yield None


def _admin(tmp_path, **kwargs) -> CRUDAdmin:
    return CRUDAdmin(
        session=_no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        secure_cookies=False,
        initial_admin=CREDENTIALS,
        **kwargs,
    )


@pytest.fixture
def logged_in(tmp_path):
    admin = _admin(tmp_path)

    async def moved() -> Response:
        return Response(
            content=b"moved elsewhere",
            status_code=302,
            headers={"location": "/elsewhere"},
        )

    async def streamed() -> StreamingResponse:
        async def chunks():
            for number in range(3):
                yield f"chunk-{number};".encode()

        return StreamingResponse(chunks(), media_type="text/plain")

    admin.app.add_api_route("/moved", moved, methods=["GET"])
    admin.app.add_api_route("/streamed", streamed, methods=["GET"])
    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        yield client


def test_no_admin_middleware_is_a_base_http_middleware(tmp_path):
    admin = _admin(
        tmp_path, allowed_ips=["127.0.0.1"], enforce_https=True, https_port=8443
    )

    classes = [middleware.cls for middleware in admin.app.user_middleware]

    assert {
        AdminAuthMiddleware,
        IPRestrictionMiddleware,
        HTTPSRedirectMiddleware,
    } <= set(classes)
    assert not any(
        isinstance(cls, type) and issubclass(cls, BaseHTTPMiddleware) for cls in classes
    )


@pytest.mark.parametrize(
    "build",
    [
        lambda app, admin: AdminAuthMiddleware(app, admin_instance=admin),
        lambda app, admin: IPRestrictionMiddleware(app, allowed_ips=["10.0.0.1"]),
        lambda app, admin: HTTPSRedirectMiddleware(app),
    ],
    ids=["auth", "ip", "https"],
)
@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_a_scope_that_is_not_http_passes_through(tmp_path, build, scope_type):
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        raise AssertionError(f"the middleware answered itself: {message}")

    scope: dict[str, Any] = {"type": scope_type, "path": "/", "headers": []}
    await build(inner, _admin(tmp_path))(scope, receive, send)

    assert seen == [scope]


def test_a_redirect_answering_admin_js_becomes_a_204_without_a_body(logged_in):
    response = logged_in.get("/admin/moved", headers=FETCH)

    assert response.status_code == 204
    assert response.headers["X-CRUDAdmin-Location"] == "/elsewhere"
    assert "location" not in response.headers
    assert "content-length" not in response.headers
    assert response.content == b""


def test_a_redirect_answering_a_browser_is_left_alone(logged_in):
    response = logged_in.get("/admin/moved")

    assert response.status_code == 302
    assert response.headers["location"] == "/elsewhere"
    assert response.content == b"moved elsewhere"
    assert "Cache-Control" not in response.headers


def test_a_streamed_page_arrives_whole_and_uncached(logged_in):
    response = logged_in.get("/admin/streamed")

    assert response.status_code == 200
    assert response.text == "chunk-0;chunk-1;chunk-2;"
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
