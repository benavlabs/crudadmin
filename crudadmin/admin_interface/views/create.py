"""Creating a record: the blank form, and the form submission."""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...admin_user.schemas import AdminUserCreateInternal
from ...event import EventType, log_admin_action
from ..helper import _get_form_fields_from_schema
from ..typing import EndpointCallable
from .forms import read_create_form
from .submission import Refusal, attempt_write, form_page, internal_object

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


def create_endpoint(view: "ModelView", template: str) -> EndpointCallable:
    """
    Create endpoint for handling form submissions to create new model records.

    Args:
        template: Path to Jinja2 template for rendering form

    Returns:
        FastAPI route handler for create form submission

    Features:
        - Form data validation using create_schema
        - Special handling for AdminUser model
        - File upload support
        - Field error collection
        - Event logging integration
        - HTMX support for dynamic updates

    Notes:
        - Uses @log_admin_action decorator for event tracking
        - Handles both single and multi-value form fields
        - Supports password hashing for AdminUser model

    Example:
        ```python
        endpoint = view.form_create_endpoint("admin/model/create.html")
        router.add_api_route("/create", endpoint, methods=["POST"])
        ```
    """

    @log_admin_action(EventType.CREATE, model=view.model, db_config=view.db_config)
    async def form_create_endpoint_inner(
        request: Request,
        db: AsyncSession = Depends(view.session),
        admin_db: AsyncSession = Depends(view.db_config.get_admin_db),
        current_user: dict = Depends(
            cast(Any, view.admin_site).admin_authentication.get_current_user()
        ),
        event_integration=Depends(lambda: view.event_integration),
    ) -> Response:
        """Handle POST form submission to create a model record."""
        assert view.admin_site is not None

        form_fields = _get_form_fields_from_schema(view.create_schema)
        field_values: Dict[str, Any] = {}
        refusal: Optional[Refusal] = None
        submitted = read_create_form(await request.form(), form_fields)
        field_values = submitted.field_values
        result, refusal = await attempt_write(
            db, lambda: _create_record(view, db, submitted.data)
        )
        if result:
            view._forget_record_count()
            request.state.crud_result = result
            return _redirect_to_list(view, request)

        return await form_page(
            view,
            request,
            db,
            template=template,
            form_fields=form_fields,
            field_values=field_values,
            refusal=refusal,
            refused_status=422,
        )

    return cast(EndpointCallable, form_create_endpoint_inner)


async def _create_record(
    view: "ModelView", db: AsyncSession, form_data: Dict[str, Any]
) -> Any:
    """Validate the form data with the create schema, write the record and commit.

    With a password transformer, the password is hashed into the internal object
    first, and the transformer's required fields must be filled.
    """
    item_data = view.create_schema(**form_data)
    record: BaseModel = item_data
    transformer = view.password_transformer
    if transformer is not None:
        transformed = transformer.transform_create_data(form_data, item_data)
        for required_field in transformer.required_fields:
            if not transformed.get(required_field):
                raise ValueError(f"{view.model.__name__} requires a {required_field}.")
        record = internal_object(view, transformed, AdminUserCreateInternal)

    result = await view.crud.create(
        db=db,
        object=record,
        schema_to_select=view.select_schema or view.create_schema,
        return_as_model=False,
    )
    await db.commit()
    return result


def _redirect_to_list(view: "ModelView", request: Request) -> Response:
    """Back to the list with a success message; htmx follows ``HX-Redirect``."""
    model_list_url = f"{view._model_list_url()}?success=created"
    if "HX-Request" in request.headers:
        return RedirectResponse(
            url=model_list_url, headers={"HX-Redirect": model_list_url}
        )
    return RedirectResponse(url=model_list_url, status_code=303)


def create_page(
    view: "ModelView", template: str = "admin/model/create.html"
) -> EndpointCallable:
    """
    Create endpoint for displaying new record creation form.

    Args:
        template: Path to Jinja2 template for rendering create form

    Returns:
        FastAPI route handler for create form page

    Example:
        ```python
        endpoint = view.get_model_create_page("admin/model/create.html")
        router.add_api_route("/create", endpoint, methods=["GET"])
        ```
    """

    async def model_create_page(
        request: Request,
        db: AsyncSession = Depends(view.session),
    ) -> Response:
        """Show a blank form for creating a new record."""
        form_fields = _get_form_fields_from_schema(view.create_schema)
        await view._apply_relationship_form_fields(form_fields, db)
        return view.templates.TemplateResponse(
            name=template,
            request=request,
            context={
                "model_name": view.model_key,
                "form_fields": form_fields,
                "url_prefix": view.get_url_prefix(),
            },
        )

    return cast(EndpointCallable, model_create_page)
