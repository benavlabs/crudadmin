"""Deleting records in bulk from the list."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...event import EventType, log_admin_action
from ..typing import EndpointCallable
from .list_query import rows_per_page as parse_rows_per_page
from .list_query import table_columns

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


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

    @log_admin_action(EventType.DELETE, model=view.model, db_config=view.db_config)
    async def bulk_delete_endpoint_inner(
        request: Request,
        db: AsyncSession = Depends(view.session),
        admin_db: AsyncSession = Depends(view.db_config.get_admin_db),
        current_user: dict = Depends(
            cast(Any, view.admin_site).admin_authentication.get_current_user()
        ),
        event_integration=Depends(lambda: view.event_integration),
    ) -> Response:
        """Handle bulk deletion of model instances using JSON list of IDs."""
        assert view.admin_site is not None
        try:
            body = await request.json()

            page_str = request.query_params.get("page", "1")
            page = int(page_str)
            rows_per_page = parse_rows_per_page(
                request.query_params.get("rows-per-page-select")
            )

            ids = body.get("ids", [])
            if not ids:
                return JSONResponse(
                    status_code=400,
                    content={"detail": [{"message": "No IDs provided for deletion"}]},
                )

            pk_name = view.primary_key_name

            valid_ids: List[Any] = []
            for id_value in ids:
                try:
                    valid_ids.append(view._convert_id_to_pk_type(id_value))
                except (ValueError, TypeError):
                    return JSONResponse(
                        status_code=422,
                        content={
                            "detail": [{"message": f"Invalid ID value: {id_value}"}]
                        },
                    )

            filter_criteria: Dict[str, List[Any]] = {f"{pk_name}__in": valid_ids}
            records_to_delete = await view.crud.get_multi(
                db=db,
                limit=len(valid_ids),
                schema_to_select=view.select_schema,
                **cast(Any, filter_criteria),
            )

            request.state.deleted_records = records_to_delete.get("data", [])

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
                view._forget_record_count()
            except Exception as e:
                await db.rollback()
                logger.error("Error during bulk delete: %s", str(e))
                return JSONResponse(
                    status_code=400,
                    content={"detail": [{"message": "Error during deletion."}]},
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

            items: Dict[str, Any] = {
                "data": items_result.get("data", []),
                "total_count": items_result.get("total_count", 0),
            }

            primary_key_info = view.db_config.get_primary_key_info(view.model)

            context: Dict[str, Any] = {
                "model_items": items["data"],
                "model_name": view.model_key,
                "table_columns": table_columns(view.model, view.select_schema),
                "total_items": items["total_count"],
                "current_page": adjusted_page,
                "rows_per_page": rows_per_page,
                "primary_key_info": primary_key_info,
                "url_prefix": view.get_url_prefix(),
                "relationships": view.relationships,
            }

            return view.templates.TemplateResponse(
                name="admin/model/components/list_content.html",
                request=request,
                context=context,
            )

        except ValueError as e:
            logger.error("Invalid bulk-delete request: %s", str(e))
            return JSONResponse(
                status_code=422,
                content={"detail": [{"message": "Invalid request."}]},
            )
        except Exception as e:
            logger.error("Error processing bulk-delete request: %s", str(e))
            return JSONResponse(
                status_code=422,
                content={"detail": [{"message": "Error processing request."}]},
            )

    return cast(EndpointCallable, bulk_delete_endpoint_inner)
