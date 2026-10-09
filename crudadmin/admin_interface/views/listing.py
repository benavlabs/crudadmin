"""The model list page: paginated, sorted and searched."""

import logging
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..typing import EndpointCallable
from .list_query import ListQuery, table_columns

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


def list_page(
    view: "ModelView", template: str = "admin/model/list.html"
) -> EndpointCallable:
    """
    Create endpoint for model list view with filtering and pagination.

    Args:
        template: Path to Jinja2 template for rendering list view

    Returns:
        FastAPI route handler for model list page

    Example:
        ```python
        first_page = await client.get("/?page=1&rows-per-page-select=25")

        sorted_and_searched = await client.get(
            "/?sort_by=username&sort_order=desc&column-to-search=email&search-input=example.com"
        )
        ```
    """

    async def get_model_admin_page_inner(
        request: Request,
        admin_db: AsyncSession = Depends(view.db_config.get_admin_db),
        app_db: AsyncSession = Depends(
            cast(
                Callable[..., AsyncGenerator[AsyncSession, None]],
                view.db_config.get_app_session(),
            )
        ),
    ) -> Response:
        """Display the model list page, allowing pagination, sorting, and searching."""
        if view._model_is_admin_model(view.model):
            db = admin_db
        else:
            db = app_db

        query = ListQuery.from_request(request, view.model)
        filter_criteria = query.filters(view.model)
        total_items = await view.crud.count(db=db, **cast(Any, filter_criteria))
        page = min(query.page, query.last_page(total_items))

        items_result = await view.crud.get_multi(
            db=db,
            offset=(page - 1) * query.rows_per_page,
            limit=query.rows_per_page,
            schema_to_select=view.select_schema,
            **cast(Any, query.sorting()),
            **cast(Any, filter_criteria),
        )

        items: dict[str, Any] = {
            "data": items_result.get("data", []),
            "total_count": items_result.get("total_count", 0),
        }

        primary_key_info = view.db_config.get_primary_key_info(view.model)

        success_messages = {
            "created": f"{view.model_key} created successfully.",
            "updated": f"{view.model_key} updated successfully.",
            "deleted": f"{view.model_key} deleted successfully.",
        }
        success_message = success_messages.get(request.query_params.get("success", ""))

        context: dict[str, Any] = {
            "model_items": items["data"],
            "model_name": view.model_key,
            "table_columns": table_columns(view.model, view.select_schema),
            "total_items": items["total_count"],
            "current_page": page,
            "rows_per_page": query.rows_per_page,
            "selected_column": query.search_column,
            "primary_key_info": primary_key_info,
            "url_prefix": view.get_url_prefix(),
            "sort_column": query.sort_column,
            "sort_order": query.sort_order,
            "allowed_actions": view.allowed_actions,
            "relationships": view.relationships,
            "success_message": success_message,
        }

        if "HX-Request" in request.headers:
            return view.templates.TemplateResponse(
                name="admin/model/components/list_content.html",
                request=request,
                context=context,
            )

        if view.admin_site is not None:
            base_context = view.admin_site.get_base_context(request)
            context.update(base_context)
            context["include_sidebar_and_header"] = True

        return view.templates.TemplateResponse(
            name=template, request=request, context=context
        )

    return cast(EndpointCallable, get_model_admin_page_inner)
