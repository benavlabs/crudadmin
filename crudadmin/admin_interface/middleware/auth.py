import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

if TYPE_CHECKING:
    from crudadmin import CRUDAdmin

logger = logging.getLogger(__name__)

FORM_SUBMITTED_BY_FETCH_HEADER = "X-CRUDAdmin-Fetch"
REDIRECT_TARGET_HEADER = "X-CRUDAdmin-Location"


def login_redirect(request: Request, login_url: str) -> Response:
    """Send the browser to the login page; an htmx request gets ``HX-Redirect``.

    A plain redirect answering an htmx request would swap the login page into
    whatever element made the request, instead of navigating to it.
    """
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": login_url})
    if request.headers.get(FORM_SUBMITTED_BY_FETCH_HEADER):
        return Response(status_code=204, headers={REDIRECT_TARGET_HEADER: login_url})
    return RedirectResponse(url=login_url, status_code=303)


NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


class AdminResponseHeaders:
    """Adjust the headers of an admin response as it is sent.

    - A response that isn't a redirect gets ``NO_CACHE_HEADERS``, so admin pages
      don't show from the browser cache after logout. Redirects are left alone, so
      browser redirect handling and cookies are untouched.
    - A redirect answering an admin.js form submission becomes a 204 naming its
      target in ``X-CRUDAdmin-Location``, and its body is dropped. admin.js submits
      plain forms with fetch; were the redirect followed, fetch would load the
      target page and the browser would then load it again on navigation. The
      response keeps its other headers, so cookies it sets or clears (a logout,
      say) still apply.
    """

    def __init__(self, send: Send, submitted_by_fetch: bool) -> None:
        self.send = send
        self.submitted_by_fetch = submitted_by_fetch
        self.drop_body = False

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            message = self._adjust_start(message)
        elif message["type"] == "http.response.body" and self.drop_body:
            message = {**message, "body": b""}
        await self.send(message)

    def _adjust_start(self, message: Message) -> Message:
        status = message["status"]
        headers = MutableHeaders(scope=message)
        if not 300 <= status < 400:
            headers.update(NO_CACHE_HEADERS)
            return message
        location = headers.get("location")
        if not self.submitted_by_fetch or location is None:
            return message
        del headers["location"]
        if "content-length" in headers:
            del headers["content-length"]
        headers[REDIRECT_TARGET_HEADER] = location
        self.drop_body = True
        return {**message, "status": 204}


class AdminAuthMiddleware:
    """Send anonymous visitors to the login page, and keep admin pages out of caches.

    It only redirects: every protected route also declares the admin's
    ``get_current_user`` dependency, which authenticates the request again (from
    crudauth's per-request cache) and enforces CSRF on POST, PUT, PATCH and DELETE.
    Other scopes, such as lifespan, pass through.
    """

    def __init__(self, app: ASGIApp, admin_instance: "CRUDAdmin") -> None:
        self.app = app
        self.admin_instance = admin_instance

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        paths = self.admin_instance.paths
        if paths.is_public(request.url.path):
            await self.app(scope, receive, send)
            return

        if await self._resolve_principal(request) is None:
            authentication = self.admin_instance.admin_authentication
            had_session = authentication.session_cookie_name in request.cookies
            reason = "session_ended" if had_session else "login_required"
            response = login_redirect(request, paths.login_with_error(reason))
            await response(scope, receive, send)
            return

        submitted_by_fetch = bool(request.headers.get(FORM_SUBMITTED_BY_FETCH_HEADER))
        await self.app(scope, receive, AdminResponseHeaders(send, submitted_by_fetch))

    async def _resolve_principal(self, request: Request) -> Optional[Any]:
        """The logged-in admin's principal, or None when the session is missing or invalid."""
        authentication = self.admin_instance.admin_authentication
        try:
            return await authentication.auth.resolve_principal(
                request, update_activity=True
            )
        except Exception:
            logger.exception("Could not resolve the admin session")
            return None
