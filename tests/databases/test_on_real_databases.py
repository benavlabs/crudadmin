"""The admin's main flows on PostgreSQL and MySQL.

Each test gets an app database and an admin database of its own, and runs the
admin with the ``database`` session backend, so sessions, CSRF tokens and the
login lockout are kept on the same server.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    inspect,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.event import EventStatus, EventType

from .conftest import Databases

pytestmark = pytest.mark.databases

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
TOKENS = [uuid.UUID(int=n) for n in range(1, 4)]


class Base(DeclarativeBase):
    pass


class Part(Base):
    __tablename__ = "parts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    stock: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)
    token: Mapped[uuid.UUID] = mapped_column(Uuid)


class PartCreate(BaseModel):
    name: str
    stock: int
    active: bool
    token: uuid.UUID


class PartUpdate(BaseModel):
    name: str | None = None
    stock: int | None = None


def _parts() -> list[Part]:
    return [
        Part(name="Bolt", stock=5, active=True, token=TOKENS[0]),
        Part(name="bracket", stock=7, active=False, token=TOKENS[1]),
        Part(name="Nut", stock=5, active=True, token=TOKENS[2]),
    ]


@dataclass
class Running:
    admin: CRUDAdmin
    client: TestClient

    def call(self, function):
        assert self.client.portal is not None
        return self.client.portal.call(function)

    def csrf(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.client.cookies["crudadmin_csrf"]}

    def login(self, credentials=CREDENTIALS) -> None:
        response = self.client.post("/admin/login", data=credentials)
        assert response.status_code == 303, response.text


def _admin(databases: Databases, get_session) -> CRUDAdmin:
    return CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        admin_db_url=databases.admin_url,
        sessions=SessionConfig(backend="database", secure_cookies=False),
        track_events=True,
        initial_admin=CREDENTIALS,
    )


@pytest.fixture
def running(databases: Databases) -> Iterator[Running]:
    engine = create_async_engine(databases.app_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    admin = _admin(databases, get_session)
    admin.add_view(model=Part, create_schema=PartCreate, update_schema=PartUpdate)

    async def start():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            for part in _parts():
                session.add(part)
                await session.flush()
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        running = Running(admin, client)
        running.call(start)
        yield running
        running.call(admin.shutdown)
        running.call(engine.dispose)


def _names(running: Running, **params) -> list[str]:
    response = running.client.get("/admin/Part/get_model_list", params=params)
    assert response.status_code == 200
    found = {
        response.text.find(f"<td>{part.name}</td>"): part.name for part in _parts()
    }
    return [name for position, name in sorted(found.items()) if position >= 0]


def test_the_admin_starts_twice_and_keeps_sessions_on_the_server(running):
    running.call(running.admin.initialize)
    running.login()

    dashboard = running.client.get("/admin/dashboard-content")
    sessions = running.client.get("/admin/management/sessions/content")

    assert dashboard.status_code == 200
    assert ">3<" in dashboard.text
    assert sessions.status_code == 200
    assert "admin" in sessions.text


def test_a_record_is_created_updated_and_deleted_with_its_audit_trail(running):
    running.login()

    created = running.client.post(
        "/admin/Part/form_create",
        data={
            "name": "Washer",
            "stock": "9",
            "active": "true",
            "token": str(uuid.uuid4()),
        },
        headers=running.csrf(),
    )
    updated = running.client.post(
        "/admin/Part/form_update/1", data={"stock": "50"}, headers=running.csrf()
    )
    deleted = running.client.request(
        "DELETE",
        "/admin/Part/bulk-delete",
        json={"ids": [2, 3]},
        headers=running.csrf(),
    )

    assert (created.status_code, updated.status_code, deleted.status_code) == (
        303,
        303,
        200,
    )
    assert _names(running) == ["Bolt"]

    async def trail():
        events_model = running.admin.db_config.AdminEventLog
        audits_model = running.admin.db_config.AdminAuditLog
        async with running.admin.db_config.admin_session_maker() as db:
            events = (await db.execute(select(events_model))).scalars().all()
            audits = (await db.execute(select(audits_model))).scalars().all()
            return (
                sorted(e.event_type.value for e in events if e.resource_type),
                sorted((a.action, a.resource_id) for a in audits),
                [a.changes for a in audits if a.action == "update"],
            )

    events, audits, update_changes = running.call(trail)
    assert events == ["create", "delete", "update"]
    assert ("delete", "2") in audits and ("delete", "3") in audits
    assert ("update", "1") in audits
    assert update_changes[0]["stock"] == {"old": 5, "new": 50}


@pytest.mark.parametrize(
    "column, value, expected",
    [
        ("name", "BR", ["bracket"]),
        ("stock", "5", ["Bolt", "Nut"]),
        ("active", "false", ["bracket"]),
        ("token", str(TOKENS[2]), ["Nut"]),
        ("stock", "many", ["Bolt", "bracket", "Nut"]),
    ],
)
def test_a_list_is_searched_by_each_column_type(running, column, value, expected):
    running.login()

    found = _names(running, **{"column-to-search": column, "search-input": value})

    assert found == expected


def test_a_list_is_sorted(running):
    running.login()

    assert _names(running, sort_by="stock", sort_order="desc")[0] == "bracket"


def test_a_taken_unique_value_is_refused_and_the_next_write_works(running):
    running.login()

    refused = running.client.post(
        "/admin/Part/form_create",
        data={
            "name": "Bolt",
            "stock": "1",
            "active": "true",
            "token": str(uuid.uuid4()),
        },
        headers=running.csrf(),
    )
    accepted = running.client.post(
        "/admin/Part/form_create",
        data={
            "name": "Spring",
            "stock": "1",
            "active": "true",
            "token": str(uuid.uuid4()),
        },
        headers=running.csrf(),
    )

    assert refused.status_code == 422
    assert "The database refused this record" in refused.text
    assert accepted.status_code == 303


def _admin_user_table_of_0_5(metadata: MetaData) -> Table:
    return Table(
        "admin_user",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(20), unique=True),
        Column("hashed_password", String(255)),
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        Column("is_superuser", Boolean),
    )


def test_an_admin_table_from_0_5_is_upgraded_in_place(databases):
    old_password = "password-from-0-5"
    engine = create_async_engine(databases.admin_url)
    table = _admin_user_table_of_0_5(MetaData())

    async def create_0_5_admin():
        async with engine.begin() as conn:
            await conn.run_sync(table.metadata.create_all)
            await conn.execute(
                table.insert().values(
                    id=1,
                    username="veteran",
                    hashed_password=bcrypt.hashpw(
                        old_password.encode(), bcrypt.gensalt()
                    ).decode(),
                    is_superuser=True,
                )
            )

    async def columns() -> set[str]:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync: {
                    c["name"] for c in inspect(sync).get_columns("admin_user")
                }
            )

    async def no_session():
        yield None

    admin = CRUDAdmin(
        session=no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=databases.admin_url,
        sessions=SessionConfig(backend="database", secure_cookies=False),
    )
    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        running = Running(admin, client)
        running.call(create_0_5_admin)
        running.call(admin.initialize)

        assert {"is_active", "token_version"} <= running.call(columns)
        running.login({"username": "veteran", "password": old_password})
        assert client.get("/admin/").status_code == 200
        running.call(admin.shutdown)
        running.call(engine.dispose)


def _event_log_table_of_0_6(metadata: MetaData) -> Table:
    return Table(
        "admin_event_log",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("timestamp", DateTime(timezone=True), nullable=False),
        Column(
            "event_type",
            Enum(EventType, name="eventtype"),
            nullable=False,
        ),
        Column(
            "status",
            Enum(EventStatus, name="eventstatus"),
            nullable=False,
        ),
        Column("user_id", Integer, nullable=False),
        Column("session_id", String(36), nullable=False, index=True),
        Column("ip_address", String(45), nullable=False),
        Column("user_agent", String(512), nullable=False),
        Column("resource_type", String(128)),
        Column("resource_id", String(128)),
        Column("details", JSON, nullable=False),
    )


def test_an_event_log_from_0_6_is_widened_and_records_logins(databases):
    engine = create_async_engine(databases.admin_url)
    table = _event_log_table_of_0_6(MetaData())

    async def create_0_6_event_log():
        async with engine.begin() as conn:
            await conn.run_sync(table.metadata.create_all)

    async def session_id_length() -> int:
        async with engine.connect() as conn:
            columns = await conn.run_sync(
                lambda sync: inspect(sync).get_columns("admin_event_log")
            )
        session_id = next(c for c in columns if c["name"] == "session_id")
        column_type = session_id["type"]
        assert isinstance(column_type, String) and column_type.length is not None
        return column_type.length

    async def logins() -> list[str]:
        async with engine.connect() as conn:
            rows = await conn.execute(select(table.c.session_id))
            return [row.session_id for row in rows]

    async def no_session():
        yield None

    admin = CRUDAdmin(
        session=no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=databases.admin_url,
        sessions=SessionConfig(backend="database", secure_cookies=False),
        track_events=True,
        initial_admin=CREDENTIALS,
    )
    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        running = Running(admin, client)
        running.call(create_0_6_event_log)
        running.call(admin.initialize)
        running.call(admin.initialize)

        assert running.call(session_id_length) == 128
        running.login()
        [handle] = running.call(logins)
        assert len(handle) == 64
        running.call(admin.shutdown)
        running.call(engine.dispose)


def test_a_long_user_agent_still_records_the_login(running):
    running.client.headers["user-agent"] = "x" * 2000
    running.login()

    async def user_agents() -> list[int]:
        events_model = running.admin.db_config.AdminEventLog
        async with running.admin.db_config.admin_session_maker() as db:
            rows = await db.execute(select(events_model.user_agent))
            return [len(row.user_agent) for row in rows]

    assert running.call(user_agents) == [512]
