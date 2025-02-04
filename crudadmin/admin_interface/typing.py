from typing import Union

from fastapi import Response
from fastapi.responses import RedirectResponse
from starlette.templating import _TemplateResponse

RouteResponse = Union[Response, RedirectResponse, _TemplateResponse]
