"""The related-records and relationship-options endpoints, through real requests."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from crudadmin import CRUDAdmin, SessionConfig

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}


class Base(DeclarativeBase):
    pass


class Writer(Base):
    __tablename__ = "related_writers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    novels = relationship("Novel", back_populates="writer")


class Novel(Base):
    __tablename__ = "related_novels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50))
    writer_id: Mapped[int | None] = mapped_column(
        ForeignKey("related_writers.id"), nullable=True
    )
    writer = relationship("Writer", back_populates="novels")


class WriterSchema(BaseModel):
    name: str


class WriterUpdate(BaseModel):
    name: str | None = None


class NovelSchema(BaseModel):
    title: str
    writer_id: int | None = None


class NovelUpdate(BaseModel):
    title: str | None = None
    writer_id: int | None = None


@pytest.fixture
def started(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        sessions=SessionConfig(secure_cookies=False),
        initial_admin=CREDENTIALS,
    )
    admin.add_view(
        model=Writer,
        create_schema=WriterSchema,
        update_schema=WriterUpdate,
        display_field="name",
    )
    admin.add_view(model=Novel, create_schema=NovelSchema, update_schema=NovelUpdate)

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            session.add_all([Writer(id=1, name="Ursula"), Writer(id=2, name="Octavia")])
            session.add_all(
                [
                    Novel(id=1, title="The Dispossessed", writer_id=1),
                    Novel(id=2, title="The Lathe of Heaven", writer_id=1),
                    Novel(id=3, title="Kindred", writer_id=2),
                ]
            )
            await session.commit()
        await admin.initialize()

    async def drop_novels():
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE related_novels"))

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(seed)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        yield client, drop_novels


def test_a_writers_novels_are_listed(started):
    client, _ = started

    response = client.get("/admin/Writer/related/1/novels")

    assert response.status_code == 200
    assert "The Dispossessed" in response.text
    assert "The Lathe of Heaven" in response.text
    assert "Kindred" not in response.text


def test_a_novels_writer_is_shown_by_its_display_field(started):
    client, _ = started

    response = client.get("/admin/Novel/related/3/writer")

    assert response.status_code == 200
    assert "Octavia" in response.text


def test_the_relationship_options_use_the_display_field(started):
    client, _ = started

    response = client.get("/admin/Novel/relationship-options/writer")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "display_name": "Ursula"},
        {"id": 2, "display_name": "Octavia"},
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/admin/Writer/related/1/publishers",
        "/admin/Novel/relationship-options/publisher",
    ],
)
def test_an_unknown_relationship_answers_404(started, path):
    client, _ = started

    response = client.get(path)

    assert response.status_code == 404
    assert "not found" in response.json()["message"]


@pytest.mark.parametrize(
    "path",
    ["/admin/Writer/related/1/novels", "/admin/Writer/relationship-options/novels"],
)
def test_a_database_error_answers_500_and_is_logged(started, caplog, path):
    client, drop_novels = started
    caplog.set_level(logging.ERROR)
    assert client.portal is not None
    client.portal.call(drop_novels)

    response = client.get(path)

    assert response.status_code == 500
    assert "related_novels" not in response.text
    assert "Writer.novels" in caplog.text
    assert "no such table" in caplog.text
