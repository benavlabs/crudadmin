"""IPRestrictionMiddleware on configurations and clients it can't use."""

import logging

from starlette.types import Message, Receive, Scope, Send

from crudadmin.admin_interface.middleware import IPRestrictionMiddleware


async def _allowed(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"in"})


async def _call(middleware: IPRestrictionMiddleware, client) -> tuple[int, bytes]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": client,
    }
    await middleware(scope, receive, send)
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    return sent[0]["status"], body


def test_invalid_entries_are_logged_and_skipped(caplog):
    caplog.set_level(logging.ERROR)

    middleware = IPRestrictionMiddleware(
        _allowed,
        allowed_ips=["10.0.0.1", "not-an-ip"],
        allowed_networks=["10.1.0.0/16", "10.2.0.0/99"],
    )

    assert middleware.allowed_ips == {"10.0.0.1"}
    assert [str(network) for network in middleware.allowed_networks] == ["10.1.0.0/16"]
    assert "not-an-ip" in caplog.text
    assert "10.2.0.0/99" in caplog.text


async def test_allowed_addresses_and_networks_get_in():
    middleware = IPRestrictionMiddleware(
        _allowed, allowed_ips=["10.0.0.1"], allowed_networks=["10.1.0.0/16"]
    )

    assert await _call(middleware, ("10.0.0.1", 1)) == (200, b"in")
    assert await _call(middleware, ("10.1.4.4", 1)) == (200, b"in")
    assert (await _call(middleware, ("10.9.9.9", 1)))[0] == 403


async def test_a_request_without_a_client_is_refused():
    middleware = IPRestrictionMiddleware(_allowed, allowed_ips=["10.0.0.1"])

    status, body = await _call(middleware, None)

    assert status == 400
    assert b"Unable to determine client IP" in body


async def test_a_client_address_that_does_not_parse_is_refused():
    middleware = IPRestrictionMiddleware(_allowed, allowed_ips=["10.0.0.1"])

    status, body = await _call(middleware, ("testclient", 1))

    assert status == 400
    assert b"Invalid IP address" in body
