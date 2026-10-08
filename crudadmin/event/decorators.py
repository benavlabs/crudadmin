import functools
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type

from fastapi import Request
from fastcrud import FastCRUD
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from crudadmin.core.db import (
    DatabaseConfig,
    convert_id_to_pk_type,
    get_primary_key_name,
)

from .models import EventType

UTC = timezone.utc

logger = logging.getLogger(__name__)


def get_model_changes(model_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format model changes for logging"""
    changes = {}
    for key, value in model_dict.items():
        if isinstance(value, datetime):
            changes[key] = value.isoformat()
        else:
            changes[key] = value
    return changes


def compare_states(
    old_state: Optional[Dict[str, Any]], new_state: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare old and new states to identify changes."""
    changes: dict = {}
    if not old_state or not new_state:
        return changes

    for key in set(old_state.keys()) | set(new_state.keys()):
        old_val = old_state.get(key)
        new_val = new_state.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


def convert_user_to_dict(user: Any) -> Dict[str, Any]:
    """Convert user object to dictionary, handling both dict and Pydantic-like objects."""
    if isinstance(user, dict):
        return user
    elif hasattr(user, "model_dump"):
        user_dict: dict = user.model_dump()
        return user_dict
    elif hasattr(user, "dict"):
        legacy_dict: dict = user.dict()
        return legacy_dict
    elif hasattr(user, "__dict__"):
        return {k: v for k, v in user.__dict__.items() if not k.startswith("_")}
    else:
        return {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
        }


def _primary_key_name_or_id(model: Optional[Type[DeclarativeBase]]) -> str:
    """The model's primary key column name, or ``"id"`` for a model SQLAlchemy can't map."""
    if model is None:
        return "id"
    try:
        return get_primary_key_name(model)
    except NoInspectionAvailable:
        return "id"


def _response_succeeded(result: Any) -> bool:
    """Whether the endpoint's response reports success (any status below 400)."""
    return getattr(result, "status_code", 200) < 400


def log_admin_action(
    event_type: EventType,
    model: Optional[Type[DeclarativeBase]] = None,
    db_config: Optional[DatabaseConfig] = None,
):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(
            *args,
            request: Request,
            db: AsyncSession,
            admin_db: AsyncSession,
            current_user: Any,
            event_integration=None,
            **kwargs,
        ):
            user_dict = convert_user_to_dict(current_user) if current_user else None

            previous_state = None
            crud: Optional[FastCRUD] = None

            if event_type in [EventType.UPDATE, EventType.DELETE]:
                if model is not None:
                    crud = FastCRUD(model)
                else:
                    logger.error("Model is None. Cannot initialize FastCRUD.")
                    raise ValueError("Model must not be None.")

                if "id" in kwargs:
                    assert crud is not None, "CRUD instance should be initialized."
                    assert model is not None
                    request_id = kwargs["id"]
                    if db_config:
                        request_id = convert_id_to_pk_type(request_id, db_config, model)

                    pk_name = get_primary_key_name(model)
                    item = await crud.get(db=db, **{pk_name: request_id})
                    if item:
                        previous_state = {
                            k: v for k, v in item.items() if not k.startswith("_")
                        }
            result = await func(
                *args,
                request=request,
                db=db,
                admin_db=admin_db,
                current_user=current_user,
                **kwargs,
            )

            try:
                if event_integration and user_dict:
                    session_id = getattr(request.state, "session_handle", "unknown")
                    succeeded = _response_succeeded(result)
                    primary_key_name = _primary_key_name_or_id(model)

                    new_state = None
                    resource_id = kwargs.get("id")

                    if event_type == EventType.UPDATE:
                        try:
                            if model is not None:
                                crud = FastCRUD(model)
                            assert crud is not None, (
                                "CRUD instance should be initialized."
                            )
                            assert model is not None
                            request_id = kwargs["id"]
                            if db_config:
                                request_id = convert_id_to_pk_type(
                                    request_id, db_config, model
                                )
                            pk_name = get_primary_key_name(model)
                            updated_item = await crud.get(
                                db=db, **{pk_name: request_id}
                            )
                            if updated_item:
                                new_state = {
                                    k: v
                                    for k, v in updated_item.items()
                                    if not k.startswith("_")
                                }
                                new_state = get_model_changes(new_state)
                        except Exception:
                            logger.exception("Could not read the updated record")

                    elif hasattr(request.state, "crud_result"):
                        crud_result = request.state.crud_result
                        if hasattr(crud_result, "__dict__"):
                            model_dict = {
                                k: v
                                for k, v in crud_result.__dict__.items()
                                if not k.startswith("_")
                            }
                        else:
                            model_dict = dict(crud_result)

                        resource_id = str(model_dict.get(primary_key_name, resource_id))
                        new_state = get_model_changes(model_dict)

                    if event_type == EventType.DELETE:
                        try:
                            body = await request.json()
                            ids = body.get("ids", [])
                            logger.info("Delete request received for ids: %s", ids)

                            deleted_records = []
                            if hasattr(request.state, "deleted_records"):
                                deleted_records = [
                                    {
                                        k: v
                                        for k, v in record.items()
                                        if not k.startswith("_")
                                    }
                                    for record in request.state.deleted_records
                                ]

                            new_state = {
                                "action": "delete",
                                "deleted_at": datetime.now(UTC).isoformat(),
                                "deleted_records": deleted_records,
                                "deletion_details": {
                                    "deleted_by": user_dict.get("username"),
                                    "trigger_path": request.url.path,
                                    "deletion_type": "bulk"
                                    if "bulk-delete" in request.url.path
                                    else "single",
                                    "records_count": len(deleted_records),
                                    "requested_ids": ids,
                                },
                            }
                        except Exception:
                            logger.exception("Could not describe the deleted records")

                    elif event_type == EventType.UPDATE:
                        changes = compare_states(previous_state, new_state)
                        new_state = {
                            "action": "update",
                            "updated_at": datetime.now(UTC).isoformat(),
                            "previous_state": previous_state,
                            "new_state": new_state,
                            "changes": changes,
                            "update_details": {
                                "updated_by": user_dict.get("username"),
                                "update_path": request.url.path,
                                "modified_fields": list(changes.keys()),
                            },
                        }

                    details = {
                        "resource_details": {
                            "model": model.__name__ if model else None,
                            "id": resource_id,
                            "changes": new_state
                            if event_type in [EventType.UPDATE, EventType.DELETE]
                            else new_state,
                        },
                        "request_details": {
                            "method": request.method,
                            "path": str(request.url.path),
                            "user_agent": request.headers.get("user-agent"),
                        },
                    }

                    await event_integration.log_model_event(
                        db=admin_db,
                        event_type=event_type,
                        model=model,
                        user_id=user_dict["id"],
                        session_id=session_id,
                        request=request,
                        resource_id=resource_id,
                        previous_state=previous_state,
                        new_state=new_state,
                        details=details,
                        succeeded=succeeded,
                        deleted_records=getattr(request.state, "deleted_records", None),
                        primary_key_name=primary_key_name,
                    )

            except Exception:
                logger.exception(
                    "Could not record the %s event; the change itself stands",
                    event_type.value,
                )
                await admin_db.rollback()

            return result

        return wrapper

    return decorator
