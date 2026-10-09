"""create_initial_admin: the forms its input takes, and a worker that loses the race."""

import logging

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from crudadmin import CRUDAdmin
from crudadmin.admin_interface.admin_accounts import create_initial_admin
from crudadmin.admin_user.schemas import AdminUserCreate

PASSWORD = "initial-password-1"


class Credentials(BaseModel):
    username: str
    password: str


async def _no_session():
    yield None


@pytest.fixture
async def admin(tmp_path):
    admin = CRUDAdmin(
        session=_no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
    )
    await admin.db_config.initialize_admin_db()
    yield admin
    await admin.shutdown()


async def _admins(admin) -> list[tuple[str, bool]]:
    model = admin.db_config.AdminUser
    async with admin.db_config.admin_session_maker() as db:
        rows = await db.execute(select(model.username, model.is_superuser))
        return [tuple(row) for row in rows]


@pytest.mark.parametrize(
    "credentials",
    [
        AdminUserCreate(username="root", password=PASSWORD),
        Credentials(username="root", password=PASSWORD),
        {"username": "root", "password": PASSWORD},
    ],
    ids=["AdminUserCreate", "another model", "dict"],
)
async def test_each_form_creates_a_superuser(admin, credentials):
    await create_initial_admin(admin.db_config, credentials)

    assert await _admins(admin) == [("root", True)]


async def test_anything_else_is_refused(admin):
    with pytest.raises(ValueError, match="dict or Pydantic model"):
        await create_initial_admin(admin.db_config, ["root", PASSWORD])  # type: ignore[arg-type]


async def test_a_worker_that_loses_the_race_skips_quietly(admin, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    await create_initial_admin(
        admin.db_config, {"username": "root", "password": PASSWORD}
    )

    async def no_admin_yet(*args, **kwargs) -> int:
        return 0

    monkeypatch.setattr(admin.db_config.crud_users, "count", no_admin_yet)
    await create_initial_admin(
        admin.db_config, {"username": "root", "password": PASSWORD}
    )

    assert await _admins(admin) == [("root", True)]
    assert "already created by another worker" in caplog.text
