import logging
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from crudauth import get_password_hash_async
from fastapi import Request
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..admin_user.schemas import (
    AdminUserCreate,
    AdminUserCreateInternal,
    AdminUserUpdateInternal,
)
from ..core.db import DatabaseConfig

if TYPE_CHECKING:
    from .auth import AdminAuthentication

logger = logging.getLogger("crudadmin")


async def create_initial_admin(
    db_config: DatabaseConfig, admin_data: Union[dict, BaseModel]
) -> None:
    """Create the initial admin, as a superuser, if no admin exists yet.

    Several workers may start at once; if another one created the admin first,
    the unique username makes this insert fail and it is skipped.

    Raises:
        ValueError: If admin_data is neither a dict nor a Pydantic model.
    """
    if isinstance(admin_data, AdminUserCreate):
        create_data = admin_data
    elif isinstance(admin_data, dict):
        create_data = AdminUserCreate(**admin_data)
    elif isinstance(admin_data, BaseModel):
        create_data = AdminUserCreate(**admin_data.model_dump())
    else:
        raise ValueError("Initial admin data must be either a dict or Pydantic model")

    async with db_config.admin_session_maker() as admin_session:
        if await db_config.crud_users.count(admin_session) > 0:
            return
        internal_data = AdminUserCreateInternal(
            username=create_data.username,
            hashed_password=await get_password_hash_async(create_data.password),
            is_superuser=True,
        )
        try:
            await db_config.crud_users.create(
                admin_session, object=cast(Any, internal_data)
            )
            await admin_session.commit()
        except IntegrityError:
            await admin_session.rollback()
            logger.info("Initial admin already created by another worker")
            return
        logger.info("Created initial admin user - username: %s", create_data.username)


async def last_superuser_guard(
    crud: FastCRUD, db: AsyncSession, user_id: Any, change: AdminUserUpdateInternal
) -> Optional[str]:
    """Refuse a change that would leave no active superuser to manage admins.

    Returns the reason to show the admin, or None when the change is allowed.
    """
    removes_superuser_access = change.is_superuser is False or change.is_active is False
    if not removes_superuser_access:
        return None
    target = await crud.get(db=db, id=user_id)
    if not target or not target.get("is_superuser") or not target.get("is_active"):
        return None
    others = await crud.count(db=db, is_superuser=True, is_active=True, id__ne=user_id)
    if others == 0:
        return "At least one active superuser must remain."
    return None


async def end_sessions_after_admin_change(
    authentication: "AdminAuthentication",
    request: Request,
    user_id: Any,
    change: AdminUserUpdateInternal,
) -> None:
    """End an admin's sessions when their password or access changes.

    A new password ends every session except the one making the change; losing
    access (deactivated, or demoted from superuser) ends them all, so the
    change applies at once rather than when the sessions expire.
    """
    manager = authentication.auth.sessions
    lost_access = change.is_active is False or change.is_superuser is False
    password_changed = change.hashed_password is not None
    if not (lost_access or password_changed):
        return
    current_session = request.cookies.get(authentication.session_cookie_name)
    is_changing_own_account = request.state.user.get("id") == user_id
    keep_current_session = is_changing_own_account and not lost_access
    await manager.revoke_all(
        user_id, exclude=current_session if keep_current_session else None
    )
