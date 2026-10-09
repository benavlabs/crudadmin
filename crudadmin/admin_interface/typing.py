from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Response
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse

RouteResponse = Response | RedirectResponse | _TemplateResponse

EndpointCallable = Callable[..., Coroutine[Any, Any, Response]]
