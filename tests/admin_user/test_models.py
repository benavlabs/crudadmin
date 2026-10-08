"""Regression tests for AdminUser timestamp defaults.

``default=datetime.now(UTC)`` is evaluated once, when the model is built, so
every admin row got the same ``created_at`` (and every update the same
``updated_at``): the moment the process started.
"""

import time
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from crudadmin.admin_user.models import create_admin_user


@pytest.mark.asyncio
async def test_timestamps_are_taken_when_each_row_is_written():
    class Base(DeclarativeBase):
        pass

    AdminUser: Any = create_admin_user(Base)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    model_built_at = datetime.now(timezone.utc)
    time.sleep(0.01)

    async with session_factory() as session:
        first = AdminUser(username="first", hashed_password="x")
        session.add(first)
        await session.commit()

        time.sleep(0.01)
        second = AdminUser(username="second", hashed_password="x")
        session.add(second)
        await session.commit()

        time.sleep(0.01)
        await session.execute(
            update(AdminUser).where(AdminUser.id == first.id).values(username="renamed")
        )
        await session.commit()
        await session.refresh(first)

    def aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    assert aware(first.created_at) > model_built_at
    assert aware(second.created_at) > aware(first.created_at)
    assert aware(first.updated_at) > aware(second.created_at)

    await engine.dispose()
