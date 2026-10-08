"""Updating a record: the form filled with the record, and the form submission."""

import datetime
import logging
from datetime import datetime as dt
from typing import TYPE_CHECKING, Any, Dict, Optional, Union, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...admin_user.schemas import AdminUserUpdateInternal
from ...event import EventType, log_admin_action
from ..admin_accounts import end_sessions_after_admin_change, last_superuser_guard
from ..helper import _get_form_fields_from_schema
from ..typing import EndpointCallable
from .forms import (
    clearable_column_names,
    read_update_form,
    schema_input,
)
from .forms import field_errors as read_field_errors

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
        error_message: Optional[str] = None
        field_errors: Dict[str, str] = {}
        field_values: Dict[str, Any] = {}

        try:
            submitted = read_update_form(
                await request.form(),
                form_fields,
                clearable_column_names(view.model),
            )
            update_data = submitted.data
            field_values = submitted.field_values
            if not update_data:
                error_message = "No changes were provided for update"
            else:
                if view.update_internal_schema is not None and hasattr(
                    view.update_internal_schema, "model_fields"
                ):
                    fields_dict = cast(
                        Dict[str, Any], view.update_internal_schema.model_fields
                    )
                    if "updated_at" in fields_dict:
                        update_data["updated_at"] = dt.now(datetime.timezone.utc)

                try:
                    if view.password_transformer is not None:
                        update_schema_instance = view.update_schema(
                            **schema_input(view.update_schema, update_data)
                        )

                        transformed_data = (
                            view.password_transformer.transform_update_data(
                                update_data, update_schema_instance
                            )
                        )

                        if view.model.__name__ == "AdminUser":
                            admin_update_schema: AdminUserUpdateInternal = (
                                AdminUserUpdateInternal(**transformed_data)
                            )
                            blocked = await last_superuser_guard(
                                view.crud, db, converted_id, admin_update_schema
                            )
                            if blocked:
                                raise ValueError(blocked)
                            await view.crud.update(
                                db=db,
                                object=admin_update_schema,
                                **view._pk_filter(converted_id),
                            )
                            await db.commit()
                            await end_sessions_after_admin_change(
                                view.admin_site.admin_authentication,
                                request,
                                converted_id,
                                admin_update_schema,
                            )
                        else:
                            if view.update_internal_schema:
                                generic_update_schema = view.update_internal_schema(
                                    **transformed_data
                                )
                                await view.crud.update(
                                    db=db,
                                    object=generic_update_schema,
                                    **view._pk_filter(converted_id),
                                )
                            else:
                                dynamic_update_schema = type(
                                    "InternalSchema", (BaseModel,), {}
                                )(**transformed_data)
                                await view.crud.update(
                                    db=db,
                                    object=dynamic_update_schema,
                                    **view._pk_filter(converted_id),
                                )

                        await db.commit()
                    else:
                        update_schema_instance = view.update_schema(
                            **schema_input(view.update_schema, update_data)
                        )
                        await view.crud.update(
                            db=db,
                            object=update_schema_instance,
                            **view._pk_filter(converted_id),
                        )
                        await db.commit()

                    model_list_url = f"{view._model_list_url()}?success=updated"
                    return RedirectResponse(
                        url=model_list_url,
                        status_code=303,
                    )

                except ValidationError as e:
                    field_errors = read_field_errors(e)
                    error_message = "Please correct the errors below."
                except Exception as e:
                    await db.rollback()
                    error_message = str(e)

        except Exception as e:
            error_message = str(e)

        for field in form_fields:
            field_name = field["name"]
            if field_name not in field_values and field_name in item:
                field_values[field_name] = item[field_name]

        await view._apply_relationship_form_fields(form_fields, db)

        context: Dict[str, Any] = {
            "model_name": view.model_key,
            "form_fields": form_fields,
            "error": error_message,
            "field_errors": field_errors,
            "field_values": field_values,
            "url_prefix": view.get_url_prefix(),
            "id": id,
            "include_sidebar_and_header": False,
        }

        return view.templates.TemplateResponse(
            name="admin/model/update.html",
            request=request,
            context=context,
            status_code=400 if error_message else 200,
        )

    return cast(EndpointCallable, form_update_endpoint_inner)


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
