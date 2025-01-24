from datetime import datetime, timezone
import functools
import logging
from typing import Callable, Optional, Type, Dict, Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from fastcrud import FastCRUD

from .models import EventType

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
    changes = {}
    if not old_state or not new_state:
        return changes

    for key in set(old_state.keys()) | set(new_state.keys()):
        old_val = old_state.get(key)
        new_val = new_state.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


def log_admin_action(
    event_type: EventType, model: Optional[Type[DeclarativeBase]] = None
):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(
            *args,
            request: Request,
            db: AsyncSession,
            admin_db: AsyncSession,
            current_user: dict,
            event_integration=None,
            **kwargs,
        ):
            previous_state = None
            crud = None

            if event_type in [EventType.UPDATE, EventType.DELETE]:
                try:
                    if not crud:
                        crud = FastCRUD(model)

                    if "id" in kwargs:
                        item = await crud.get(db=db, id=kwargs["id"])
                        if item:
                            previous_state = {
                                k: v for k, v in item.items() if not k.startswith("_")
                            }
                except Exception as e:
                    logger.error(f"Error fetching previous state: {str(e)}")

            result = await func(
                *args,
                request=request,
                db=db,
                admin_db=admin_db,
                current_user=current_user,
                **kwargs,
            )

            try:
                if event_integration and current_user:
                    session_id = request.cookies.get("session_id", "unknown")

                    new_state = None
                    resource_id = kwargs.get("id")

                    if event_type == EventType.UPDATE:
                        try:
                            if not crud:
                                crud = FastCRUD(model)
                            updated_item = await crud.get(db=db, id=kwargs["id"])
                            if updated_item:
                                new_state = {
                                    k: v
                                    for k, v in updated_item.items()
                                    if not k.startswith("_")
                                }
                                new_state = get_model_changes(new_state)
                        except Exception as e:
                            logger.error(f"Error fetching updated state: {str(e)}")
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

                        resource_id = str(model_dict.get("id", resource_id))
                        new_state = get_model_changes(model_dict)

                    if event_type == EventType.DELETE:
                        timestamp = datetime.now(timezone.utc)
                        deleted_records = []

                        try:
                            body = await request.json()
                            ids = body.get("ids", [])
                            logger.info(f"Delete request received for ids: {ids}")

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
                                "deleted_at": timestamp.isoformat(),
                                "deleted_records": deleted_records,
                                "deletion_details": {
                                    "deleted_by": current_user.get("username"),
                                    "trigger_path": request.url.path,
                                    "deletion_type": "bulk"
                                    if "bulk-delete" in request.url.path
                                    else "single",
                                    "records_count": len(deleted_records),
                                    "requested_ids": ids,
                                },
                            }
                        except Exception as e:
                            logger.error(f"Error in bulk delete process: {str(e)}")

                    elif event_type == EventType.UPDATE:
                        timestamp = datetime.now(timezone.utc)
                        changes = compare_states(previous_state, new_state)
                        new_state = {
                            "action": "update",
                            "updated_at": timestamp.isoformat(),
                            "previous_state": previous_state,
                            "new_state": new_state,
                            "changes": changes,
                            "update_details": {
                                "updated_by": current_user.get("username"),
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
                        user_id=current_user["id"],
                        session_id=session_id,
                        request=request,
                        resource_id=resource_id,
                        previous_state=previous_state,
                        new_state=new_state,
                        details=details,
                    )
                    await admin_db.commit()

            except Exception as e:
                logger.error(f"Error logging event: {str(e)}")

            return result

        return wrapper

    return decorator


def log_auth_action(event_type: EventType) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(
            *args, request: Request, db: AsyncSession, event_integration=None, **kwargs
        ):
            if event_integration:
                try:
                    form_data = kwargs.get("form_data")
                    result = await func(*args, request=request, db=db, **kwargs)

                    user_id = None
                    username = None
                    session_id = None
                    success = False

                    if event_type == EventType.LOGIN:
                        if hasattr(request.state, "user"):
                            user_id = request.state.user.get("id")
                            username = request.state.user.get("username")
                            success = True
                            if hasattr(result, "headers"):
                                for header in result.raw_headers:
                                    if (
                                        header[0].decode() == "set-cookie"
                                        and b"session_id=" in header[1]
                                    ):
                                        session_id = (
                                            header[1]
                                            .decode()
                                            .split("session_id=")[1]
                                            .split(";")[0]
                                        )
                                        break
                    elif event_type == EventType.LOGOUT:
                        session_id = request.cookies.get("session_id", "unknown")
                        if hasattr(request.state, "user"):
                            user_id = request.state.user.get("id")
                            username = request.state.user.get("username")
                            success = True

                    if not session_id:
                        session_id = "unknown"

                    details = {
                        "auth_details": {
                            "event_type": event_type.value,
                            "username": username or form_data.username
                            if form_data
                            else "unknown",
                            "success": success,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                        "request_details": {
                            "method": request.method,
                            "path": str(request.url.path),
                            "ip_address": request.client.host,
                            "user_agent": request.headers.get("user-agent", "Unknown"),
                        },
                        "session_details": {
                            "session_id": session_id,
                            "browser": request.headers.get("user-agent", "Unknown"),
                        },
                    }

                    await event_integration.log_auth_event(
                        db=db,
                        event_type=event_type,
                        user_id=user_id or 0,
                        session_id=session_id,
                        request=request,
                        success=success,
                        details=details,
                    )

                    return result

                except Exception as e:
                    logger.error(f"Error logging auth event: {str(e)}")
                    raise

            return await func(*args, request=request, db=db, **kwargs)

        return wrapper

    return decorator
