from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, https_port: int = 443):
        super().__init__(app)
        self.https_port = https_port

    async def dispatch(self, request: Request, call_next):
        """Redirect plain-HTTP requests to HTTPS on the configured port.

        Every request is checked: the middleware is installed on the admin app,
        so it only ever sees admin requests, whatever the mount path.
        """
        if request.url.scheme == "http":
            port = None if self.https_port == 443 else self.https_port
            https_url = request.url.replace(scheme="https", port=port)
            return RedirectResponse(str(https_url), status_code=301)

        return await call_next(request)
