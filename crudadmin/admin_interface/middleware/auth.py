import logging
from typing import TYPE_CHECKING

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

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


def redirect_for_fetch(request: Request, response: Response) -> Response:
    """Answer a redirect to an admin.js form submission with a 204 naming its target.

    admin.js submits plain forms with fetch. Were the redirect followed, fetch would
    load the target page and the browser would then load it again on navigation;
    with the target in a header, the browser navigates once. The response keeps
    its other headers, so cookies it sets or clears (a logout, say) still apply.
    """
    location = response.headers.get("location")
    if not request.headers.get(FORM_SUBMITTED_BY_FETCH_HEADER) or location is None:
        return response
    if not 300 <= response.status_code < 400:
        return response
    del response.headers["location"]
    response.headers[REDIRECT_TARGET_HEADER] = location
    response.status_code = 204
    return response


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Send anonymous visitors to the login page, and keep admin pages out of caches.

    It only redirects: every protected route also declares the admin's
    ``get_current_user`` dependency, which authenticates the request again (from
    crudauth's per-request cache) and enforces CSRF on POST, PUT, PATCH and DELETE.
    """

    def __init__(self, app: ASGIApp, admin_instance: "CRUDAdmin"):
        super().__init__(app)
        self.admin_instance = admin_instance

    def _add_no_cache_headers(self, response: Response) -> None:
        """Keep admin pages out of the browser cache, so they don't show after logout."""
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, private"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    def _should_add_cache_headers(self, response: Response) -> bool:
        """Leave redirects alone, so browser redirect handling and cookies are untouched."""
        return not (300 <= response.status_code < 400)

    async def dispatch(self, request: Request, call_next):
        url_prefix = self.admin_instance.get_url_prefix()

        is_login_path = request.url.path.rstrip("/") == f"{url_prefix}/login"
        is_static_path = request.url.path.startswith(f"{url_prefix}/static/")
        if is_login_path or is_static_path:
            return await call_next(request)

        authentication = self.admin_instance.admin_authentication
        try:
            principal = await authentication.auth.resolve_principal(
                request, update_activity=True
            )
        except Exception:
            logger.exception("Could not resolve the admin session")
            principal = None

        if principal is None:
            had_session = authentication.session_cookie_name in request.cookies
            reason = "session_ended" if had_session else "login_required"
            return login_redirect(request, f"{url_prefix}/login?error={reason}")

        response = await call_next(request)

        if self._should_add_cache_headers(response):
            self._add_no_cache_headers(response)

        return redirect_for_fetch(request, response)
