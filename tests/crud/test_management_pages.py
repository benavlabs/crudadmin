"""The health and event log pages, rendered for a logged-in superuser."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crudadmin import CRUDAdmin

CREDENTIALS = {"username": "root", "password": "correct-horse-battery"}


@pytest.fixture
def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        secure_cookies=False,
        track_events=True,
        initial_admin=CREDENTIALS,
    )
    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        yield client


def test_the_health_page_reports_the_database_and_the_session_store(client):
    assert client.get("/admin/management/health").status_code == 200

    content = client.get("/admin/management/health/content")

    assert content.status_code == 200
    assert "Connected successfully" in content.text
    assert "Session store: memory" in content.text
    assert "unhealthy" not in content.text


def test_the_event_log_page_offers_the_admins_to_filter_by(client):
    page = client.get("/admin/management/events")

    assert page.status_code == 200
    assert "root" in page.text


def test_the_event_log_lists_the_login_with_its_admin(client):
    content = client.get("/admin/management/events/content")

    assert content.status_code == 200
    assert "login" in content.text.lower()
    assert "root" in content.text


@pytest.mark.parametrize(
    "query, shows_login",
    [
        ("event_type=login", True),
        ("event_type=create", False),
        ("username=root", True),
        ("start_date=2000-01-01&end_date=2000-01-02", False),
    ],
)
def test_the_event_log_filters(client, query, shows_login):
    content = client.get(f"/admin/management/events/content?{query}")

    assert content.status_code == 200
    assert ("127.0.0.1" in content.text) is shows_login
