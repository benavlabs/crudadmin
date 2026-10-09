"""PostgreSQL and MySQL servers for the ``databases`` tests, started once per session.

These tests need Docker. They are deselected by default; ``pytest -m databases``
runs them, and fails rather than skips when Docker isn't available, so a CI job
can't pass without running them.
"""

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from docker.errors import DockerException
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.core.docker_client import DockerClient
from testcontainers.mysql import MySqlContainer
from testcontainers.postgres import PostgresContainer

MYSQL_ROOT_PASSWORD = "root-password"


@dataclass(frozen=True)
class DatabaseServer:
    """A running server: its dialect, and a URL for an account that may create databases."""

    dialect: str
    url: URL

    def database(self, name: str) -> str:
        return self.url.set(database=name).render_as_string(hide_password=False)


def _require_docker() -> None:
    try:
        DockerClient()
    except DockerException as error:
        pytest.fail(f"The databases tests need Docker, which isn't available: {error}")


def _postgres() -> Iterator[DatabaseServer]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as server:
        yield DatabaseServer(
            "postgresql", make_url(server.get_connection_url()).set(database="postgres")
        )


def _mysql() -> Iterator[DatabaseServer]:
    with MySqlContainer("mysql:8.4", root_password=MYSQL_ROOT_PASSWORD) as server:
        url = make_url(server.get_connection_url()).set(
            drivername="mysql+aiomysql",
            username="root",
            password=MYSQL_ROOT_PASSWORD,
            database=None,
        )
        yield DatabaseServer("mysql", url)


SERVERS = {"postgresql": _postgres, "mysql": _mysql}


@pytest.fixture(scope="session", params=list(SERVERS))
def database_server(request: pytest.FixtureRequest) -> Iterator[DatabaseServer]:
    _require_docker()
    yield from SERVERS[request.param]()


async def _create_database(server: DatabaseServer, name: str) -> None:
    engine = create_async_engine(server.url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f"CREATE DATABASE {name}"))
    await engine.dispose()


@dataclass(frozen=True)
class Databases:
    """An app database and an admin database of their own, on one server."""

    dialect: str
    app_url: str
    admin_url: str


@pytest.fixture
def databases(database_server: DatabaseServer) -> Databases:
    suffix = uuid.uuid4().hex[:12]
    names = (f"app_{suffix}", f"admin_{suffix}")
    for name in names:
        asyncio.run(_create_database(database_server, name))
    return Databases(
        dialect=database_server.dialect,
        app_url=database_server.database(names[0]),
        admin_url=database_server.database(names[1]),
    )
