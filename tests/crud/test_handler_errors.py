"""How the admin's endpoints answer errors.

An error the admin can act on is shown on the page; a database error is shown
without its SQL and logged; anything else is a bug and answers 500 instead of
being dressed up as a form error.
"""

import logging
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import ForeignKey, Integer, String, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.admin_interface.model_view import PasswordTransformer

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}


class Base(DeclarativeBase):
    pass


class Tag(Base):
    __tablename__ = "handled_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class TagLink(Base):
    __tablename__ = "handled_tag_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("handled_tags.id"))


class Member(Base):
    __tablename__ = "handled_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(100))


class UncreatedBase(DeclarativeBase):
    pass


class Ghost(UncreatedBase):
    __tablename__ = "handled_ghosts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class NameSchema(BaseModel):
    name: str


class NameUpdate(BaseModel):
    name: Optional[str] = None


class MemberCreate(BaseModel):
    name: str
    password: str


class MemberInternal(BaseModel):
    name: str
    hashed_password: str


def _broken_hash(password: str) -> str:
    raise RuntimeError("the hash function has a bug")


@pytest.fixture
def started(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

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
    admin.add_view(model=Tag, create_schema=NameSchema, update_schema=NameUpdate)
    admin.add_view(
        model=Member,
        create_schema=MemberCreate,
        update_schema=NameUpdate,
        update_internal_schema=MemberInternal,
        password_transformer=PasswordTransformer(hash_function=_broken_hash),
    )
    admin.add_view(model=Ghost, create_schema=NameSchema, update_schema=NameUpdate)

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            session.add(Tag(id=1, name="taken"))
            await session.commit()
            session.add(TagLink(id=1, tag_id=1))
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(
        app,
        follow_redirects=False,
        raise_server_exceptions=False,
        client=("127.0.0.1", 50000),
    ) as client:
        assert client.portal is not None
        client.portal.call(seed)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        yield admin, client


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["crudadmin_csrf"]}


class TestWrites:
    def test_a_unique_value_taken_is_refused_without_the_sql(self, started):
        _, client = started

        response = client.post(
            "/admin/Tag/form_create", data={"name": "taken"}, headers=_csrf(client)
        )

        assert response.status_code == 422
        assert "The database refused this record" in response.text
        assert "UNIQUE" not in response.text
        assert "INSERT" not in response.text

    def test_a_database_error_is_logged_and_shown_generically(self, started, caplog):
        _, client = started
        caplog.set_level(logging.ERROR)

        response = client.post(
            "/admin/Ghost/form_create", data={"name": "boo"}, headers=_csrf(client)
        )

        assert response.status_code == 422
        assert "The record could not be saved" in response.text
        assert "no such table" not in response.text
        assert "Could not write the record" in caplog.text
        assert "no such table" in caplog.text

    def test_a_bug_in_a_write_answers_500_instead_of_a_form_error(self, started):
        _, client = started

        response = client.post(
            "/admin/Member/form_create",
            data={"name": "ann", "password": "pw"},
            headers=_csrf(client),
        )

        assert response.status_code == 500
        assert "the hash function has a bug" not in response.text


class TestBulkDelete:
    @pytest.mark.parametrize(
        "body, query, status",
        [
            ("not json", "", 422),
            ("[1, 2]", "", 422),
            ('{"ids": [1]}', "?page=last", 422),
            ("{}", "", 400),
            ('{"ids": []}', "", 400),
        ],
    )
    def test_a_malformed_request_is_refused(self, started, body, query, status):
        _, client = started

        response = client.request(
            "DELETE",
            f"/admin/Tag/bulk-delete{query}",
            content=body,
            headers={**_csrf(client), "Content-Type": "application/json"},
        )

        assert response.status_code == status

    def test_a_record_still_referenced_is_kept_and_the_refusal_logged(
        self, started, caplog
    ):
        _, client = started
        caplog.set_level(logging.ERROR)

        response = client.request(
            "DELETE", "/admin/Tag/bulk-delete", json={"ids": [1]}, headers=_csrf(client)
        )

        assert response.status_code == 400
        assert response.json() == {"detail": [{"message": "Error during deletion."}]}
        assert "Could not delete Tag records" in caplog.text
        assert "FOREIGN KEY" in caplog.text
        listing = client.get("/admin/Tag/get_model_list").text
        assert "taken" in listing


def test_a_session_store_failure_is_an_error_not_a_login_page(started):
    admin, client = started

    async def unreachable(request, update_activity=False):
        raise ConnectionError("the session store is down")

    admin.admin_authentication.auth.resolve_principal = unreachable

    response = client.get("/admin/")

    assert response.status_code == 500
