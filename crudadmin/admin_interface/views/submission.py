"""Handling a submitted create or update form.

A submission is written through the model's schemas, and when it is refused the
form is shown again with the reason and the values the admin entered.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .forms import field_errors as read_field_errors

if TYPE_CHECKING:
    from ..model_view import ModelView

logger = logging.getLogger(__name__)

T = TypeVar("T")

VALIDATION_FAILED = "Please correct the errors below."
CONFLICT = (
    "The database refused this record: a value must be unique, or a required "
    "value or related record is missing."
)
WRITE_FAILED = "The record could not be saved. Try again, or check the server logs."


@dataclass
class Refusal:
    """Why a submission wasn't written: a message, and the message for each field."""

    message: str
    field_errors: dict[str, str] = field(default_factory=dict)


async def attempt_write(
    db: AsyncSession, write: Callable[[], Awaitable[T]]
) -> tuple[T | None, Refusal | None]:
    """Run ``write``, and say why when it is refused.

    - Invalid input refuses it with each field's message.
    - A ``ValueError`` is a refusal the admin can act on (a required field, the
      last superuser), shown as it is.
    - A constraint the database enforces refuses it with ``CONFLICT``; any other
      database error is logged and refuses it with ``WRITE_FAILED``. The
      database's own message, with its SQL, isn't shown.

    Each refusal after the write started rolls the session back. Any other
    exception is a bug, and propagates.
    """
    try:
        return await write(), None
    except ValidationError as error:
        return None, Refusal(VALIDATION_FAILED, read_field_errors(error))
    except ValueError as error:
        await db.rollback()
        return None, Refusal(str(error))
    except IntegrityError:
        await db.rollback()
        return None, Refusal(CONFLICT)
    except SQLAlchemyError:
        logger.exception("Could not write the record")
        await db.rollback()
        return None, Refusal(WRITE_FAILED)


def internal_object(
    view: "ModelView", data: dict[str, Any], admin_schema: type[BaseModel]
) -> BaseModel:
    """The object a view with a password transformer writes.

    For admins, ``admin_schema``; for other models, their internal update schema,
    or a schema that takes the data as it is.
    """
    if view.model.__name__ == "AdminUser":
        return admin_schema(**data)
    if view.update_internal_schema:
        return view.update_internal_schema(**data)
    schema_taking_the_data_as_it_is: type[BaseModel] = type(
        "InternalSchema", (BaseModel,), {}
    )
    return schema_taking_the_data_as_it_is(**data)


async def form_page(
    view: "ModelView",
    request: Request,
    db: AsyncSession,
    *,
    template: str,
    form_fields: list[dict[str, Any]],
    field_values: dict[str, Any],
    refusal: Refusal | None,
    refused_status: int,
    extra_context: dict[str, Any] | None = None,
) -> Response:
    """The form again, with the refusal and the values the admin entered."""
    await view._apply_relationship_form_fields(form_fields, db)
    context: dict[str, Any] = {
        "model_name": view.model_key,
        "form_fields": form_fields,
        "error": refusal.message if refusal else None,
        "field_errors": refusal.field_errors if refusal else {},
        "field_values": field_values,
        "url_prefix": view.get_url_prefix(),
        **(extra_context or {}),
    }
    return view.templates.TemplateResponse(
        name=template,
        request=request,
        context=context,
        status_code=refused_status if refusal else 200,
    )
