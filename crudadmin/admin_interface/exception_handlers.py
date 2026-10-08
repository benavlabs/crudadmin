from typing import Any

from crudauth.exceptions import CSRFException, ForbiddenException
from crudauth.exceptions import UnauthorizedException as AuthUnauthorizedException
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .auth import ReauthenticationRequired
from .middleware.auth import login_redirect
from .paths import AdminPaths


def add_auth_exception_handlers(app: FastAPI, paths: AdminPaths) -> None:
    """Turn authentication failures into pages and redirects a browser can follow.

    - An ended session goes to the login page.
    - A route that needs a recent password confirmation goes to the sudo page,
      which sends the admin back once confirmed.
    - A refused permission or a missing CSRF token gets a short 403 page.
    """

    async def unauthorized(request: Request, exc: Exception) -> Any:
        return login_redirect(request, paths.login_with_error("session_ended"))

    async def reauthenticate(request: Request, exc: Exception) -> Any:
        assert isinstance(exc, ReauthenticationRequired)
        target = paths.sudo(exc.next_path)
        if request.headers.get("HX-Request"):
            return HTMLResponse(status_code=204, headers={"HX-Redirect": target})
        return RedirectResponse(url=target, status_code=303)

    async def forbidden(request: Request, exc: Exception) -> Any:
        message = (
            "This request is missing its security token. Reload the page and try again."
            if isinstance(exc, CSRFException)
            else "You don't have permission to do that."
        )
        return HTMLResponse(message, status_code=403)

    app.add_exception_handler(AuthUnauthorizedException, unauthorized)
    app.add_exception_handler(ReauthenticationRequired, reauthenticate)
    app.add_exception_handler(ForbiddenException, forbidden)
    app.add_exception_handler(CSRFException, forbidden)
