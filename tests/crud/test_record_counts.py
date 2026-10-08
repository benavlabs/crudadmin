"""Record counts are computed for the dashboard only, and kept for a while.

Pages other than the dashboard run no ``COUNT(*)`` beyond the one a model list
needs for its own pagination. The dashboard keeps each count for a minute, and
forgets a model's count when the admin creates or deletes one of its records.
"""

import re
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Integer, String, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin
from crudadmin.admin_interface.record_counts import RecordCounts

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
ARTICLES = 4
COMMENTS = 2


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "counted_articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50))


class Comment(Base):
    __tablename__ = "counted_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(String(50))


class ArticleCreate(BaseModel):
    title: str


class ArticleUpdate(BaseModel):
    title: Optional[str] = None


class CommentCreate(BaseModel):
    body: str


class CommentUpdate(BaseModel):
    body: Optional[str] = None


@pytest.fixture
def counted(tmp_path):
    """A logged-in client, and the COUNT statements the app database has run."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    count_statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_counts(conn, cursor, statement, parameters, context, executemany):
        if re.search(r"\bcount\(", statement, re.IGNORECASE):
            count_statements.append(statement)

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
    admin.add_view(
        model=Article, create_schema=ArticleCreate, update_schema=ArticleUpdate
    )
    admin.add_view(
        model=Comment, create_schema=CommentCreate, update_schema=CommentUpdate
    )

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            session.add_all(Article(title=f"a{n}") for n in range(ARTICLES))
            session.add_all(Comment(body=f"c{n}") for n in range(COMMENTS))
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(seed)
        assert client.post("/admin/login", data=CREDENTIALS).status_code == 303
        count_statements.clear()
        yield client, count_statements


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["crudadmin_csrf"]}


def _dashboard_counts(client) -> dict[str, int]:
    html = client.get("/admin/dashboard-content").text
    return {
        name: int(count)
        for name, count in re.findall(
            r'class="module-title">([^<]+)</a>\s*<div class="module-stats">'
            r'\s*<span>[^<]*</span>\s*<span class="stats-badge">(\d+)</span>',
            html,
        )
    }


class TestPagesWithoutCounts:
    @pytest.mark.parametrize(
        "path", ["/admin/", "/admin/management/sessions", "/admin/management/health"]
    )
    def test_a_page_runs_no_count(self, counted, path):
        client, count_statements = counted

        assert client.get(path).status_code == 200
        assert count_statements == []

    def test_a_model_list_counts_only_its_own_table(self, counted):
        client, count_statements = counted

        assert client.get("/admin/Article/").status_code == 200

        assert count_statements
        assert all("counted_comments" not in s for s in count_statements)

    def test_the_sidebar_shows_no_counts(self, counted):
        client, _ = counted

        html = client.get("/admin/Article/").text

        assert "model-count" not in html


class TestDashboardCounts:
    def test_the_dashboard_shows_each_model_and_the_admins(self, counted):
        client, _ = counted

        assert _dashboard_counts(client) == {
            "Admin Users": 1,
            "Article": ARTICLES,
            "Comment": COMMENTS,
        }

    def test_a_second_dashboard_view_reuses_the_counts(self, counted):
        client, count_statements = counted
        _dashboard_counts(client)
        count_statements.clear()

        _dashboard_counts(client)

        assert count_statements == []

    def test_a_create_through_the_admin_shows_at_once(self, counted):
        client, _ = counted
        _dashboard_counts(client)

        response = client.post(
            "/admin/Article/form_create",
            data={"id": "", "title": "fresh"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        assert _dashboard_counts(client)["Article"] == ARTICLES + 1

    def test_a_delete_through_the_admin_shows_at_once(self, counted):
        client, _ = counted
        _dashboard_counts(client)

        response = client.request(
            "DELETE",
            "/admin/Comment/bulk-delete",
            json={"ids": [1]},
            headers=_csrf(client),
        )

        assert response.status_code == 200
        assert _dashboard_counts(client)["Comment"] == COMMENTS - 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TestRecordCounts:
    @pytest.fixture
    def clock(self):
        return FakeClock()

    @pytest.fixture
    def counter(self):
        calls: list[int] = []

        async def count() -> int:
            calls.append(1)
            return len(calls)

        return count, calls

    async def test_a_count_is_kept_until_it_expires(self, clock, counter):
        count, calls = counter
        counts = RecordCounts(ttl_seconds=60, clock=clock)

        assert await counts.get("Article", count) == 1
        clock.now = 59.9
        assert await counts.get("Article", count) == 1
        clock.now = 60.0
        assert await counts.get("Article", count) == 2
        assert len(calls) == 2

    async def test_forget_makes_the_next_get_recount(self, clock, counter):
        count, calls = counter
        counts = RecordCounts(ttl_seconds=60, clock=clock)
        await counts.get("Article", count)

        counts.forget("Article")

        assert await counts.get("Article", count) == 2

    async def test_models_are_counted_separately(self, clock, counter):
        count, calls = counter
        counts = RecordCounts(ttl_seconds=60, clock=clock)

        await counts.get("Article", count)
        await counts.get("Comment", count)
        counts.forget("Comment")

        assert await counts.get("Article", count) == 1
        assert len(calls) == 2
