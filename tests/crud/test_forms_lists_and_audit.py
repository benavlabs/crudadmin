"""Form handling, list pages and the audit log, through a real admin app."""

import uuid
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import Boolean, Integer, String, Uuid, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.admin_interface.helper import _get_form_fields_from_schema
from crudadmin.admin_interface.model_view import PasswordTransformer
from crudadmin.core.db import DatabaseConfig

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "forms_jobs"
    job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    note: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "forms_tickets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(50))


class JobCreate(BaseModel):
    name: str
    note: Optional[str] = None
    active: bool = True


class JobUpdate(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    active: Optional[bool] = None


class TicketCreate(BaseModel):
    title: str


class TicketUpdate(BaseModel):
    title: Optional[str] = None


TICKET_IDS = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
JOB_COUNT = 12


@pytest.fixture
def app_and_admin(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session():
        async with session_maker() as session:
            yield session

    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        sessions=SessionConfig(secure_cookies=False),
        track_events=True,
        initial_admin=CREDENTIALS,
    )
    admin.add_view(model=Job, create_schema=JobCreate, update_schema=JobUpdate)
    admin.add_view(model=Ticket, create_schema=TicketCreate, update_schema=TicketUpdate)

    async def seed():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_maker() as session:
            for number in range(1, JOB_COUNT + 1):
                name = "alpha" if number % 2 else "beta"
                session.add(Job(job_id=number, name=f"{name}-{number:02d}", note="n"))
            for ticket_id in TICKET_IDS:
                session.add(Ticket(id=ticket_id, title=f"t-{ticket_id.hex[:6]}"))
            await session.commit()
        await admin.initialize()

    app = FastAPI()
    app.mount("/admin", admin.app)
    return app, admin, seed, session_maker


@pytest.fixture
def client(app_and_admin):
    app, admin, seed, _ = app_and_admin
    with TestClient(
        app,
        follow_redirects=False,
        raise_server_exceptions=False,
        client=("127.0.0.1", 50000),
    ) as client:
        assert client.portal is not None
        client.portal.call(seed)
        response = client.post("/admin/login", data=CREDENTIALS)
        assert response.status_code == 303
        yield client


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["crudadmin_csrf"]}


def _job(client, app_and_admin, job_id) -> Any:
    _, _, _, session_maker = app_and_admin

    async def load():
        async with session_maker() as session:
            return await session.get(Job, job_id)

    assert client.portal is not None
    return client.portal.call(load)


def _events_and_audits(client, admin) -> tuple[list[Any], list[Any]]:
    async def load():
        events_model = admin.db_config.AdminEventLog
        audits_model = admin.db_config.AdminAuditLog
        async with admin.db_config.admin_session_maker() as session:
            events = (
                (await session.execute(select(events_model).order_by(events_model.id)))
                .scalars()
                .all()
            )
            audits = (
                (await session.execute(select(audits_model).order_by(audits_model.id)))
                .scalars()
                .all()
            )
            return list(events), list(audits)

    assert client.portal is not None
    events, audits = client.portal.call(load)
    return events, audits


def _model_events(events: list[Any]) -> list[Any]:
    return [event for event in events if event.resource_type is not None]


class TestFormFields:
    def test_optional_bool_renders_as_a_checkbox(self):
        fields = {
            field["name"]: field for field in _get_form_fields_from_schema(JobUpdate)
        }

        assert fields["active"]["type"] == "checkbox"
        assert fields["note"]["type"] == "text"

    def test_optional_int_renders_as_a_number(self):
        class WithOptionalNumber(BaseModel):
            quantity: Optional[int] = None

        (field,) = _get_form_fields_from_schema(WithOptionalNumber)

        assert field["type"] == "number"

    def test_update_page_shows_the_checkbox(self, client):
        page = client.get("/admin/Job/update/1")

        assert page.status_code == 200
        assert 'type="checkbox"' in page.text


class TestUpdates:
    def test_an_empty_input_clears_a_nullable_column(self, client, app_and_admin):
        response = client.post(
            "/admin/Job/form_update/1",
            data={"name": "alpha-01", "note": "", "active": "on"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        assert _job(client, app_and_admin, 1).note is None

    def test_an_empty_input_leaves_a_not_null_column_alone(self, client, app_and_admin):
        response = client.post(
            "/admin/Job/form_update/1",
            data={"name": "", "note": "kept", "active": "on"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        job = _job(client, app_and_admin, 1)
        assert job.name == "alpha-01"
        assert job.note == "kept"

    def test_an_unchecked_box_sets_false(self, client, app_and_admin):
        response = client.post(
            "/admin/Job/form_update/1",
            data={"name": "alpha-01"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        assert _job(client, app_and_admin, 1).active is False


class TestPasswordTransformer:
    def test_update_keeps_false_and_zero(self):
        class AccountUpdate(BaseModel):
            password: Optional[str] = None
            enabled: Optional[bool] = None
            retries: Optional[int] = None

        transformer = PasswordTransformer(hash_function=lambda value: f"h:{value}")
        form = {"enabled": False, "retries": 0}

        data = transformer.transform_update_data(form, AccountUpdate(**form))

        assert data["enabled"] is False
        assert data["retries"] == 0
        assert "hashed_password" not in data


class TestLists:
    def test_bulk_delete_works_with_uuid_keys(self, client):
        doomed = [str(TICKET_IDS[0]), str(TICKET_IDS[1])]

        response = client.request(
            "DELETE",
            "/admin/Ticket/bulk-delete",
            json={"ids": doomed},
            headers=_csrf(client),
        )

        assert response.status_code == 200
        listing = client.get("/admin/Ticket/get_model_list").text
        assert "Showing 1 to 1 of 1 entries" in listing

    def test_a_malformed_uuid_is_refused(self, client):
        response = client.request(
            "DELETE",
            "/admin/Ticket/bulk-delete",
            json={"ids": ["not-a-uuid"]},
            headers=_csrf(client),
        )

        assert response.status_code == 422

    def test_pagination_carries_the_search(self, client):
        searched = {"column-to-search": "name", "search-input": "alpha"}

        page_one = client.get("/admin/Job/get_model_list", params=searched)

        assert "Showing 1 to 6 of 6 entries" in page_one.text
        include = "[name='column-to-search'],[name='search-input']"
        assert include in page_one.text

    def test_a_failing_list_query_is_an_error_not_an_empty_list(self, client):
        async def broken_count(*args, **kwargs):
            raise RuntimeError("database unavailable")

        original_count = FastCRUD.count
        FastCRUD.count = broken_count  # type: ignore[method-assign]
        try:
            response = client.get("/admin/Job/get_model_list")
        finally:
            FastCRUD.count = original_count  # type: ignore[method-assign]

        assert response.status_code == 500
        assert "0 entries" not in response.text


class TestAuditLog:
    def test_a_create_is_audited_under_the_real_primary_key(
        self, client, app_and_admin
    ):
        _, admin, _, _ = app_and_admin

        response = client.post(
            "/admin/Job/form_create",
            data={"job_id": "", "name": "gamma", "active": "true"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        events, audits = _events_and_audits(client, admin)
        created = _model_events(events)[-1]
        assert (created.event_type.value, created.status.value) == ("create", "success")
        assert audits[-1].resource_id == str(JOB_COUNT + 1)

    def test_each_deleted_record_gets_an_audit_row(self, client, app_and_admin):
        _, admin, _, _ = app_and_admin

        response = client.request(
            "DELETE",
            "/admin/Job/bulk-delete",
            json={"ids": [3, 5]},
            headers=_csrf(client),
        )

        assert response.status_code == 200
        events, audits = _events_and_audits(client, admin)
        deleted = _model_events(events)[-1]
        assert (deleted.event_type.value, deleted.status.value) == ("delete", "success")
        delete_audits = [audit for audit in audits if audit.event_id == deleted.id]
        assert sorted(audit.resource_id for audit in delete_audits) == ["3", "5"]

    def test_an_update_is_audited_with_the_record_before_after_and_the_diff(
        self, client, app_and_admin
    ):
        _, admin, _, _ = app_and_admin

        response = client.post(
            "/admin/Job/form_update/2",
            data={"name": "renamed", "active": "true"},
            headers=_csrf(client),
        )

        assert response.status_code == 303
        events, audits = _events_and_audits(client, admin)
        updated = _model_events(events)[-1]
        assert (updated.event_type.value, updated.status.value) == ("update", "success")
        assert updated.resource_id == "2"
        assert updated.details["resource_details"]["changes"] == {
            "name": {"old": "beta-02", "new": "renamed"}
        }
        audit = audits[-1]
        assert audit.event_id == updated.id
        assert audit.previous_state["name"] == "beta-02"
        assert audit.new_state["name"] == "renamed"
        assert audit.changes == {"name": {"old": "beta-02", "new": "renamed"}}

    def test_a_delete_lists_the_deleted_records_in_the_event(
        self, client, app_and_admin
    ):
        _, admin, _, _ = app_and_admin

        client.request(
            "DELETE", "/admin/Job/bulk-delete", json={"ids": [4]}, headers=_csrf(client)
        )

        events, _ = _events_and_audits(client, admin)
        deleted = _model_events(events)[-1].details["resource_details"]["changes"]
        assert [record["job_id"] for record in deleted["deleted_records"]] == [4]

    def test_a_failed_action_is_recorded_as_a_failure_without_audit_rows(
        self, client, app_and_admin
    ):
        _, admin, _, _ = app_and_admin

        response = client.post(
            "/admin/Job/form_update/2",
            data={"active": "not-a-boolean"},
            headers=_csrf(client),
        )

        assert response.status_code == 400
        events, audits = _events_and_audits(client, admin)
        failed = _model_events(events)[-1]
        assert (failed.event_type.value, failed.status.value) == ("update", "failure")
        assert not [audit for audit in audits if audit.event_id == failed.id]

    def test_a_failing_audit_write_rolls_back_and_keeps_the_change(
        self, client, app_and_admin
    ):
        _, admin, _, _ = app_and_admin
        service = admin.event_service

        async def broken_audit(*args, **kwargs):
            raise RuntimeError("audit table missing")

        original = service.create_audit_log
        service.create_audit_log = broken_audit
        try:
            response = client.post(
                "/admin/Job/form_update/2",
                data={"name": "renamed", "active": "on"},
                headers=_csrf(client),
            )
        finally:
            service.create_audit_log = original

        assert response.status_code == 303
        assert _job(client, app_and_admin, 2).name == "renamed"
        events, _ = _events_and_audits(client, admin)
        assert not [
            event for event in _model_events(events) if event.resource_id == "2"
        ]
