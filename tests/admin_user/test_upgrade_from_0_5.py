"""An admin database made by crudadmin 0.5 keeps working after the upgrade.

0.6 added ``is_active`` and ``token_version`` to ``admin_user``. ``initialize()``
adds them in place, so an existing deployment needs no manual migration, and its
admins (whose password hashes 0.5 wrote) can still log in.
"""

import asyncio

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.core.db import DatabaseConfig

OLD_SCHEMA = """
CREATE TABLE admin_user (
    id INTEGER NOT NULL PRIMARY KEY,
    username VARCHAR(20) NOT NULL UNIQUE,
    hashed_password VARCHAR NOT NULL,
    created_at DATETIME,
    updated_at DATETIME,
    is_superuser BOOLEAN NOT NULL
)
"""


async def _get_session():
    yield None


def test_a_0_5_admin_database_is_upgraded_in_place(tmp_path):
    path = tmp_path / "admin.db"
    engine = create_engine(f"sqlite:///{path}")
    legacy_hash = bcrypt.hashpw(b"old-admin-password", bcrypt.gensalt()).decode()
    with engine.begin() as conn:
        conn.execute(text(OLD_SCHEMA))
        conn.execute(
            text(
                "INSERT INTO admin_user (username, hashed_password, is_superuser) "
                "VALUES ('veteran', :h, 1)"
            ),
            {"h": legacy_hash},
        )

    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{path}",
        ),
        sessions=SessionConfig(secure_cookies=False),
    )
    app = FastAPI()
    app.mount("/admin", admin.app)

    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 1)) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)

        columns = {c["name"] for c in inspect(engine).get_columns("admin_user")}
        assert {"is_active", "token_version"} <= columns
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT is_active, token_version, is_superuser FROM admin_user")
            ).one()
        assert tuple(row) == (1, 0, 1)

        login = client.post(
            "/admin/login",
            data={"username": "veteran", "password": "old-admin-password"},
        )
        assert login.status_code == 303
        assert client.get("/admin/AdminUser/").status_code == 200

        assert client.portal is not None
        client.portal.call(admin.initialize)
        columns_after_restart = {
            c["name"] for c in inspect(engine).get_columns("admin_user")
        }
        assert columns_after_restart == columns

    engine.dispose()


def _create_0_5_admin_database(path) -> None:
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text(OLD_SCHEMA))
    engine.dispose()


def _admin_db_config(path) -> DatabaseConfig:
    class AdminBase(DeclarativeBase):
        pass

    return DatabaseConfig(
        base=AdminBase,
        session=_get_session,
        admin_db_url=f"sqlite+aiosqlite:///{path}",
    )


def _admin_user_columns(path) -> set[str]:
    engine = create_engine(f"sqlite:///{path}")
    columns = {c["name"] for c in inspect(engine).get_columns("admin_user")}
    engine.dispose()
    return columns


@pytest.mark.asyncio
async def test_workers_starting_together_both_upgrade_successfully(tmp_path):
    path = tmp_path / "admin.db"
    _create_0_5_admin_database(path)
    workers = [_admin_db_config(path), _admin_db_config(path)]

    await asyncio.gather(*(worker.initialize_admin_db() for worker in workers))

    assert {"is_active", "token_version"} <= _admin_user_columns(path)
    for worker in workers:
        await worker.admin_engine.dispose()


@pytest.mark.asyncio
async def test_a_worker_that_loses_the_race_carries_on(tmp_path):
    """The losing worker saw the column missing, but another worker added it first."""
    path = tmp_path / "admin.db"
    _create_0_5_admin_database(path)
    winner = _admin_db_config(path)
    await winner.initialize_admin_db()

    loser = _admin_db_config(path)
    real_column_names = loser._admin_user_column_names
    calls = 0

    async def column_names_seen_before_the_winner_committed() -> set[str]:
        nonlocal calls
        calls += 1
        columns = await real_column_names()
        is_check_before_alter = calls == 1
        return columns - {"is_active"} if is_check_before_alter else columns

    loser._admin_user_column_names = column_names_seen_before_the_winner_committed  # type: ignore[method-assign]

    await loser.initialize_admin_db()

    assert {"is_active", "token_version"} <= _admin_user_columns(path)
    await winner.admin_engine.dispose()
    await loser.admin_engine.dispose()
