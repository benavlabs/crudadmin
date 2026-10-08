from fastapi.responses import RedirectResponse
from starlette.datastructures import URL
from starlette.types import ASGIApp, Receive, Scope, Send


class HTTPSRedirectMiddleware:
    """Redirect plain-HTTP requests to HTTPS on the configured port.

    Every request is checked: the middleware is installed on the admin app, so it
    only ever sees admin requests, whatever the mount path. Other scopes, such as
    lifespan, pass through.
    """

    def __init__(self, app: ASGIApp, https_port: int = 443) -> None:
        self.app = app
        self.https_port = https_port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("scheme") == "http":
            port = None if self.https_port == 443 else self.https_port
            https_url = URL(scope=scope).replace(scheme="https", port=port)
            response = RedirectResponse(str(https_url), status_code=301)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
