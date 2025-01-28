from typing import Union

from starlette.templating import _TemplateResponse
from fastapi import Response
from fastapi.responses import RedirectResponse


RouteResponse = Union[Response, RedirectResponse, _TemplateResponse]
