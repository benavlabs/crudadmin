import logging
from typing import Any, Union, cast

from crudauth import get_password_hash_async
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..admin_user.schemas import AdminUserCreate, AdminUserCreateInternal
from ..core.db import DatabaseConfig

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
