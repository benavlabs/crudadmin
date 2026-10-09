"""Deleting records in bulk from the list."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Union, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...event import EventType
from ..typing import EndpointCallable
from .list_query import rows_per_page as parse_rows_per_page
from .list_query import table_columns

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operations containing IDs to delete."""

    ids: List[Union[int, str]] = Field(default_factory=list)


def bulk_delete_endpoint(view: "ModelView") -> EndpointCallable:
    """
    Create endpoint for bulk deletion of model records.

    Returns:
        FastAPI route handler for bulk delete operations

    Features:
        - Handles multiple record deletion in one request
        - Supports different primary key types (int, str, float)
        - Validates IDs before deletion
        - Handles pagination after deletion
        - Event logging integration
        - Transaction management

    Notes:
        - Expects JSON payload with "ids" list
        - Performs type conversion based on primary key type
        - Maintains pagination state after deletion
        - Rolls back transaction on error

    Example:
        ```python
        await client.delete("/bulk-delete", json={"ids": [1, 2, 3]})
        ```

    Response Formats:
        **Success:**
            - Returns updated list content template
            - Status: 200 OK

        **Errors:**
            - 400: No IDs provided
            - 422: Invalid ID format
            - 400: Database error during deletion
    """

    async def bulk_delete_endpoint_inner(
        request: Request,
        db: AsyncSession = Depends(view.session),
        admin_db: AsyncSession = Depends(view.db_config.get_admin_db),
    ) -> Response:
        """Handle bulk deletion of model instances using JSON list of IDs."""
        assert view.admin_site is not None

        async def refuse(status_code: int, message: str) -> Response:
            await view.events.record(
                request, admin_db, EventType.DELETE, view.model, succeeded=False
            )
            return JSONResponse(
                status_code=status_code, content={"detail": [{"message": message}]}
            )

        try:
            delete_request = BulkDeleteRequest.model_validate(await request.json())
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            return await refuse(422, "Invalid request.")
        rows_per_page = parse_rows_per_page(
            request.query_params.get("rows-per-page-select")
        )

        if not delete_request.ids:
            return await refuse(400, "No IDs provided for deletion")

        pk_name = view.primary_key_name

        valid_ids: List[Any] = []
        for id_value in delete_request.ids:
            try:
                valid_ids.append(view._convert_id_to_pk_type(id_value))
            except (ValueError, TypeError):
                return await refuse(422, f"Invalid ID value: {id_value}")

        filter_criteria: Dict[str, List[Any]] = {f"{pk_name}__in": valid_ids}
        records_to_delete = await view.crud.get_multi(
            db=db,
            limit=len(valid_ids),
            schema_to_select=view.select_schema,
            **cast(Any, filter_criteria),
        )
        deleted_records = records_to_delete.get("data", [])

        try:
            for id_value in valid_ids:
                await view.crud.delete(
                    db=db,
                    db_row=None,
                    commit=False,
                    allow_multiple=False,
                    **{pk_name: id_value},
                )
            await db.commit()
        except SQLAlchemyError:
            logger.exception("Could not delete %s records", view.model_key)
            await db.rollback()
            return await refuse(400, "Error during deletion.")
        view._forget_record_count()
        await view.events.record(
            request, admin_db, EventType.DELETE, view.model, deleted=deleted_records
        )

        total_count = await view.crud.count(db=db)
        max_page = (total_count + rows_per_page - 1) // rows_per_page
        adjusted_page = min(page, max(1, max_page))

        items_result = await view.crud.get_multi(
            db=db,
            offset=(adjusted_page - 1) * rows_per_page,
            limit=rows_per_page,
            schema_to_select=view.select_schema,
        )

        context: Dict[str, Any] = {
            "model_items": items_result.get("data", []),
            "model_name": view.model_key,
            "table_columns": table_columns(view.model, view.select_schema),
            "total_items": items_result.get("total_count", 0),
            "current_page": adjusted_page,
            "rows_per_page": rows_per_page,
            "primary_key_info": view.db_config.get_primary_key_info(view.model),
            "url_prefix": view.get_url_prefix(),
            "relationships": view.relationships,
        }

        return view.templates.TemplateResponse(
            name="admin/model/components/list_content.html",
            request=request,
            context=context,
        )

    return cast(EndpointCallable, bulk_delete_endpoint_inner)
