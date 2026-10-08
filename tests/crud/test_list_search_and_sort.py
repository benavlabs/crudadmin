"""Searching and sorting a model list, through real requests.

A search matches by the column's type: text anywhere and case-insensitively,
numbers and booleans exactly. A value that doesn't fit the column filters
nothing.
"""

import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Boolean, Float, Integer, String, Uuid
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
TOKENS = [uuid.UUID(int=n) for n in range(1, 5)]


class Base(DeclarativeBase):
    pass


class Gadget(Base):
    __tablename__ = "searched_gadgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    stock: Mapped[int] = mapped_column(Integer)
    weight: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean)
    token: Mapped[uuid.UUID] = mapped_column(Uuid)


class GadgetSchema(BaseModel):
    name: str


def _gadgets() -> list[Gadget]:
    return [
        Gadget(id=1, name="Alpha", stock=5, weight=1.5, active=True, token=TOKENS[0]),
        Gadget(id=2, name="beta", stock=7, weight=2.0, active=False, token=TOKENS[1]),
        Gadget(
            id=3, name="alphabet", stock=5, weight=3.0, active=True, token=TOKENS[2]
        ),
        Gadget(id=4, name="gamma", stock=9, weight=1.5, active=False, token=TOKENS[3]),
    ]


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
        initial_admin=CREDENTIALS,
    )
    admin.add_view(model=Gadget, create_schema=GadgetSchema, update_schema=GadgetSchema)

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            session.add_all(_gadgets())
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(seed)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        yield client


def _names(client, **params) -> list[str]:
    response = client.get("/admin/Gadget/get_model_list", params=params)
    assert response.status_code == 200
    return re.findall(r"<td>(Alpha|beta|alphabet|gamma)</td>", response.text)


def _search(client, column: str, value: str) -> list[str]:
    return _names(client, **{"column-to-search": column, "search-input": value})


@pytest.mark.parametrize(
    "column, value, expected",
    [
        ("name", "ALPHA", ["Alpha", "alphabet"]),
        ("name", "  bet ", ["beta", "alphabet"]),
        ("stock", "5", ["Alpha", "alphabet"]),
        ("weight", "1.5", ["Alpha", "gamma"]),
        ("active", "yes", ["Alpha", "alphabet"]),
        ("active", "0", ["beta", "gamma"]),
    ],
)
def test_a_search_matches_by_the_column_type(client, column, value, expected):
    assert _search(client, column, value) == expected


@pytest.mark.parametrize(
    "column, value",
    [
        ("stock", "many"),
        ("active", "maybe"),
        ("no_such_column", "5"),
        ("name", "   "),
    ],
)
def test_a_search_that_does_not_fit_filters_nothing(client, column, value):
    assert _search(client, column, value) == ["Alpha", "beta", "alphabet", "gamma"]


def test_sorting_orders_the_rows(client):
    assert _names(client, sort_by="name", sort_order="desc") == [
        "gamma",
        "beta",
        "alphabet",
        "Alpha",
    ]
    assert _names(client, sort_by="stock", sort_order="asc")[-1] == "gamma"


def test_an_unknown_sort_is_ignored(client):
    assert _names(client, sort_by="nope", sort_order="sideways") == [
        "Alpha",
        "beta",
        "alphabet",
        "gamma",
    ]


def test_a_page_past_the_end_shows_the_last_page(client):
    response = client.get(
        "/admin/Gadget/get_model_list",
        params={"page": "99", "rows-per-page-select": "10"},
    )

    assert response.status_code == 200
    assert "Showing 1 to 4 of 4 entries" in response.text
