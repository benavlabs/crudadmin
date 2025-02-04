from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, https_port: int = 443):
        super().__init__(app)
        self.https_port = https_port

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        if request.url.scheme == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            if self.https_port != 443:
                https_url = https_url.replace(f":{self.https_port}", "", 1)
            return RedirectResponse(https_url, status_code=301)

        return await call_next(request)
