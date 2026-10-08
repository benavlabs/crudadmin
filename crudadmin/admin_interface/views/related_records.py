"""Related records of a row, and the options of a relationship dropdown."""

import logging
from typing import TYPE_CHECKING, Union, cast

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..relationships import (
    RelationshipType,
    get_relationship_summary,
    load_related_data,
    load_relationship_options,
)
from ..typing import EndpointCallable

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)


def related_data_endpoint(view: "ModelView") -> EndpointCallable:
    """
    Create endpoint for fetching related data for a specific record.

    Returns:
        FastAPI route handler for related data retrieval

    URL Pattern:
        GET /related/{id}/{relationship_name}

    Returns HTML partial for HTMX to display related records in an
    expandable row or inline table.
    """

    async def get_related_data_inner(
        request: Request,
        id: Union[int, str],
        relationship_name: str,
        db: AsyncSession = Depends(view.session),
    ) -> Response:
        """Fetch and return related records as HTML partial."""
        if relationship_name not in view.relationships:
            return JSONResponse(
                status_code=404,
                content={"message": f"Relationship '{relationship_name}' not found"},
            )

        relationship = view._with_resolved_display_field(
            view.relationships[relationship_name]
        )
        converted_id = view._convert_id_to_pk_type(id)

        primary_key_info = view.db_config.get_primary_key_info(view.model)
        if not primary_key_info:
            return JSONResponse(
                status_code=400,
                content={"message": "Model has no primary key"},
            )

        try:
            related_data = await load_related_data(
                crud=view.crud,
                db=db,
                parent_pk_name=primary_key_info["name"],
                pk_value=converted_id,
                relationship=relationship,
            )

            summary = get_relationship_summary({}, relationship, related_data)

            if relationship.relationship_type in (
                RelationshipType.HAS_MANY,
                RelationshipType.MANY_TO_MANY,
            ):
                template = "admin/model/components/related_table.html"
            elif relationship.relationship_type == RelationshipType.HAS_ONE:
                template = "admin/model/components/related_single.html"
            else:
                template = "admin/model/components/related_link.html"

            context = {
                "relationship": relationship,
                "related_data": related_data,
                "summary": summary,
                "parent_id": id,
                "parent_model": view.model_key,
                "url_prefix": view.get_url_prefix(),
            }

            return view.templates.TemplateResponse(
                name=template, request=request, context=context
            )

        except SQLAlchemyError:
            logger.exception(
                "Could not load related data for %s.%s",
                view.model_key,
                relationship_name,
            )
            return JSONResponse(
                status_code=500,
                content={"message": "Error loading related data."},
            )

    return cast(EndpointCallable, get_related_data_inner)


def relationship_options_endpoint(view: "ModelView") -> EndpointCallable:
    """
    Create endpoint for fetching options for relationship dropdowns.

    Returns:
        FastAPI route handler for relationship options

    URL Pattern:
        GET /relationship-options/{relationship_name}

    Returns JSON list of options for select/dropdown fields.
    """

    async def get_relationship_options_inner(
        request: Request,
        relationship_name: str,
        db: AsyncSession = Depends(view.session),
    ) -> Response:
        """Fetch options for a relationship dropdown."""
        if relationship_name not in view.relationships:
            return JSONResponse(
                status_code=404,
                content={"message": f"Relationship '{relationship_name}' not found"},
            )

        relationship = view._with_resolved_display_field(
            view.relationships[relationship_name]
        )

        try:
            options = await load_relationship_options(
                db=db,
                relationship=relationship,
            )

            return JSONResponse(content=options)

        except SQLAlchemyError:
            logger.exception(
                "Could not load relationship options for %s.%s",
                view.model_key,
                relationship_name,
            )
            return JSONResponse(
                status_code=500,
                content={"message": "Error loading options."},
            )

    return cast(EndpointCallable, get_relationship_options_inner)
