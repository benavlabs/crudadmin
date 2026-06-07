"""Tests for models whose primary key is not named ``id`` (issue #68).

CRUDAdmin must use the model's actual primary-key column name as the filter
key for get/update/delete, instead of hardcoding ``id``.
"""

import pytest
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from crudadmin.core.db import get_primary_key_name


class Base(DeclarativeBase):
    pass


class DeploymentJob(Base):
    __tablename__ = "deployment_jobs"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))


class JobCreate(BaseModel):
    name: str


class JobUpdate(BaseModel):
    name: str


def test_get_primary_key_name_non_id():
    assert get_primary_key_name(DeploymentJob) == "job_id"


def test_get_primary_key_name_rejects_non_model():
    """A non-mapped class raises rather than silently returning ``"id"``."""

    class NotAModel:
        pass

    with pytest.raises(NoInspectionAvailable):
        get_primary_key_name(NotAModel)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_update_delete_with_non_id_pk():
    """get/update/delete keyed on the real PK column works end to end.

    This mirrors what ModelView now does (filter by ``get_primary_key_name``
    instead of ``id``). Before the fix, ``id=`` was hardcoded and Postgres /
    fastcrud rejected it with "Invalid column 'id'".
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    crud: FastCRUD = FastCRUD(DeploymentJob)
    pk_name = get_primary_key_name(DeploymentJob)

    async with AsyncSession(engine) as db:
        await crud.create(db=db, object=JobCreate(name="build"))
        await db.commit()

        # get by the real PK column
        job = await crud.get(db=db, **{pk_name: 1})
        assert job is not None
        assert job["name"] == "build"

        # update by the real PK column
        await crud.update(db=db, object=JobUpdate(name="deploy"), **{pk_name: 1})
        await db.commit()
        job = await crud.get(db=db, **{pk_name: 1})
        assert job["name"] == "deploy"

        # delete by the real PK column
        await crud.delete(db=db, allow_multiple=False, **{pk_name: 1})
        await db.commit()
        assert await crud.get(db=db, **{pk_name: 1}) is None

    await engine.dispose()
