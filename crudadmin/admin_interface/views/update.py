"""Updating a record: the form filled with the record, and the form submission."""

import datetime
import logging
from datetime import datetime as dt
from typing import TYPE_CHECKING, Any, Dict, Optional, Union, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...admin_user.schemas import AdminUserUpdateInternal
from ...event import EventType, log_admin_action
from ..admin_accounts import end_sessions_after_admin_change, last_superuser_guard
from ..helper import _get_form_fields_from_schema
from ..typing import EndpointCallable
from .forms import clearable_column_names, read_update_form, schema_input
from .submission import Refusal, attempt_write, form_page, internal_object

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


def update_endpoint(view: "ModelView") -> EndpointCallable:
    """
    Create endpoint for handling form submissions to update existing records.

    Returns:
        FastAPI route handler for update form submission

    Notes:
        - Uses @log_admin_action decorator for event tracking
        - Only updates provided fields
        - Handles password hashing for AdminUser model
        - Supports automatic updated_at timestamp
    """

    @log_admin_action(EventType.UPDATE, model=view.model, db_config=view.db_config)
    async def form_update_endpoint_inner(
        request: Request,
        db: AsyncSession = Depends(view.session),
        admin_db: AsyncSession = Depends(view.db_config.get_admin_db),
        current_user: dict = Depends(
            cast(Any, view.admin_site).admin_authentication.get_current_user()
        ),
        event_integration=Depends(lambda: view.event_integration),
        id: Optional[Union[int, str]] = None,
    ) -> Response:
        """Handle POST form submission to update an existing record."""
        assert view.admin_site is not None

        if id is None:
            return JSONResponse(
                status_code=422, content={"message": "No id parameter provided"}
            )

        converted_id = view._convert_id_to_pk_type(id)

        item = await view.crud.get(
            db=db,
            schema_to_select=view.select_schema,
            **view._pk_filter(converted_id),
        )
        if not item:
            return JSONResponse(
                status_code=404, content={"message": f"Item with id {id} not found"}
            )

        form_fields = _get_form_fields_from_schema(view.update_schema)
        field_values: Dict[str, Any] = {}
        refusal: Optional[Refusal] = None
        try:
            submitted = read_update_form(
                await request.form(), form_fields, clearable_column_names(view.model)
            )
            field_values = submitted.field_values
            if not submitted.data:
                refusal = Refusal("No changes were provided for update")
            else:
                _stamp_updated_at(view, submitted.data)
                _, refusal = await attempt_write(
                    db,
                    lambda: _update_record(
                        view, db, request, converted_id, submitted.data
                    ),
                )
                if refusal is None:
                    model_list_url = f"{view._model_list_url()}?success=updated"
                    return RedirectResponse(url=model_list_url, status_code=303)
        except Exception as error:
            refusal = Refusal(str(error))

        for form_field in form_fields:
            field_name = form_field["name"]
            if field_name not in field_values and field_name in item:
                field_values[field_name] = item[field_name]

        return await form_page(
            view,
            request,
            db,
            template="admin/model/update.html",
            form_fields=form_fields,
            field_values=field_values,
            refusal=refusal,
            refused_status=400,
            extra_context={"id": id, "include_sidebar_and_header": False},
        )

    return cast(EndpointCallable, form_update_endpoint_inner)


def _stamp_updated_at(view: "ModelView", update_data: Dict[str, Any]) -> None:
    """Set ``updated_at`` to now when the internal update schema has the field."""
    internal_schema = view.update_internal_schema
    if internal_schema is not None and "updated_at" in internal_schema.model_fields:
        update_data["updated_at"] = dt.now(datetime.timezone.utc)


async def _update_record(
    view: "ModelView",
    db: AsyncSession,
    request: Request,
    record_id: Any,
    update_data: Dict[str, Any],
) -> None:
    """Validate the changes with the update schema, write them and commit.

    With a password transformer, a new password is hashed into the internal
    object first; an admin account goes through ``_update_admin_account``.
    """
    validated = view.update_schema(**schema_input(view.update_schema, update_data))
    transformer = view.password_transformer
    if transformer is None:
        changes: BaseModel = validated
    else:
        transformed = transformer.transform_update_data(update_data, validated)
        if view.model.__name__ == "AdminUser":
            await _update_admin_account(
                view, db, request, record_id, AdminUserUpdateInternal(**transformed)
            )
            return
        changes = internal_object(view, transformed, AdminUserUpdateInternal)

    await view.crud.update(db=db, object=changes, **view._pk_filter(record_id))
    await db.commit()


async def _update_admin_account(
    view: "ModelView",
    db: AsyncSession,
    request: Request,
    admin_id: Any,
    change: AdminUserUpdateInternal,
) -> None:
    """Update an admin, unless no active superuser would remain.

    The sessions the change revokes are ended once it is committed.
    """
    assert view.admin_site is not None
    blocked = await last_superuser_guard(view.crud, db, admin_id, change)
    if blocked:
        raise ValueError(blocked)
    await view.crud.update(db=db, object=change, **view._pk_filter(admin_id))
    await db.commit()
    await end_sessions_after_admin_change(
        view.admin_site.admin_authentication, request, admin_id, change
    )


def update_page(view: "ModelView", template: str) -> EndpointCallable:
    """
    Create endpoint for displaying record update form.

    Args:
        template: Path to Jinja2 template for rendering update form

    Returns:
        FastAPI route handler for update form page

    Example:
        ```python
        endpoint = view.get_model_update_page("admin/model/update.html")
        router.add_api_route("/update/{id}", endpoint, methods=["GET"])
        ```
    """

    async def get_model_update_page_inner(
        request: Request,
        id: Union[int, str],
        db: AsyncSession = Depends(view.session),
    ) -> Response:
        """Show a form to update an existing record by `id`."""
        converted_id = view._convert_id_to_pk_type(id)

        item = await view.crud.get(
            db=db,
            schema_to_select=view.select_schema,
            **view._pk_filter(converted_id),
        )
        if not item:
            return JSONResponse(
                status_code=404, content={"message": f"Item with id {id} not found"}
            )

        form_fields = _get_form_fields_from_schema(view.update_schema)
        await view._apply_relationship_form_fields(form_fields, db)
        field_values: Dict[str, Any] = {}
        for field in form_fields:
            field_name = field["name"]
            if field_name in item:
                field["value"] = item[field_name]
                field_values[field_name] = item[field_name]

        return view.templates.TemplateResponse(
            name=template,
            request=request,
            context={
                "model_name": view.model_key,
                "form_fields": form_fields,
                "field_values": field_values,
                "url_prefix": view.get_url_prefix(),
                "id": id,
            },
        )

    return cast(EndpointCallable, get_model_update_page_inner)
