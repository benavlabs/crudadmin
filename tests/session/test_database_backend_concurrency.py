"""Regression test: the database session backend under concurrent requests.

Every storage operation used to share one ``AsyncSession``. Concurrent requests
then collided on it (``IllegalStateChangeError``), session validation failed,
and most of them were redirected to the login page.
"""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.core.db import DatabaseConfig


async def _get_session():
    yield None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend_kwargs",
    [
        {"sessions": SessionConfig(backend="database", secure_cookies=False)},
        {
            "sessions": SessionConfig(secure_cookies=False),
            "track_sessions_in_db": True,
        },
    ],
)
async def test_concurrent_requests_keep_their_session(tmp_path, backend_kwargs):
    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        initial_admin={"username": "admin", "password": "correct-horse-battery"},
        **backend_kwargs,
    )
    await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        login = await client.post(
            "/admin/login",
            data={"username": "admin", "password": "correct-horse-battery"},
        )
        assert login.status_code == 303, login.text

        responses = await asyncio.gather(*(client.get("/admin/") for _ in range(20)))

    assert [r.status_code for r in responses] == [200] * 20
