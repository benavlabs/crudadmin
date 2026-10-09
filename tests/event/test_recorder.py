"""AdminEvents.record, the one way model changes reach the event log."""

import logging

import pytest
from sqlalchemy import Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.requests import Request

from crudadmin import CRUDAdmin
from crudadmin.event import AdminEvents, EventType
from crudadmin.event.service import REDACTED


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "recorded_products"
    sku: Mapped[str] = mapped_column(String(20), primary_key=True)
    stock: Mapped[int] = mapped_column(Integer)


async def _no_session():
    yield None


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/products/restock",
            "headers": [(b"user-agent", b"tests")],
            "client": ("10.0.0.1", 1),
            "state": {"user": {"id": 7, "username": "ops"}, "session_handle": "h1"},
        }
    )


@pytest.fixture
async def admin(tmp_path):
    admin = CRUDAdmin(
        session=_no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        track_events=True,
    )
    await admin.initialize()
    yield admin
    await admin.shutdown()


async def _stored(admin):
    async with admin.db_config.admin_session_maker() as db:
        events = (
            (await db.execute(select(admin.db_config.AdminEventLog))).scalars().all()
        )
        audits = (
            (await db.execute(select(admin.db_config.AdminAuditLog))).scalars().all()
        )
        return list(events), list(audits)


async def test_a_change_is_recorded_with_its_admin_and_audit_row(admin):
    async with admin.db_config.admin_session_maker() as admin_db:
        await admin.events.record(
            _request(),
            admin_db,
            EventType.UPDATE,
            Product,
            record_id="A-1",
            before={"sku": "A-1", "stock": 3, "api_key": "k1"},
            after={"sku": "A-1", "stock": 9, "api_key": "k2"},
        )

    events, audits = await _stored(admin)
    [event] = events
    assert (event.event_type.value, event.status.value) == ("update", "success")
    assert (event.user_id, event.session_id, event.resource_id) == (7, "h1", "A-1")
    assert event.details["resource_details"]["changes"] == {
        "stock": {"old": 3, "new": 9},
        "api_key": {"old": REDACTED, "new": REDACTED},
    }
    [audit] = audits
    assert audit.previous_state == {"sku": "A-1", "stock": 3, "api_key": REDACTED}
    assert audit.new_state == {"sku": "A-1", "stock": 9, "api_key": REDACTED}


async def test_a_delete_gets_an_audit_row_per_record_under_its_primary_key(admin):
    async with admin.db_config.admin_session_maker() as admin_db:
        await admin.events.record(
            _request(),
            admin_db,
            EventType.DELETE,
            Product,
            deleted=[{"sku": "A-1", "stock": 0}, {"sku": "B-2", "stock": 1}],
        )

    _, audits = await _stored(admin)
    assert sorted(audit.resource_id for audit in audits) == ["A-1", "B-2"]


async def test_a_refused_change_is_recorded_without_audit_rows(admin):
    async with admin.db_config.admin_session_maker() as admin_db:
        await admin.events.record(
            _request(), admin_db, EventType.CREATE, Product, succeeded=False
        )

    events, audits = await _stored(admin)
    assert [event.status.value for event in events] == ["failure"]
    assert audits == []


async def test_a_failing_write_is_logged_and_absorbed(admin, caplog):
    caplog.set_level(logging.ERROR)

    async def broken(**kwargs):
        raise RuntimeError("the event table is gone")

    assert admin.events.integration is not None
    admin.events.integration.log_model_event = broken

    async with admin.db_config.admin_session_maker() as admin_db:
        await admin.events.record(_request(), admin_db, EventType.CREATE, Product)

    assert "Could not record the create of Product" in caplog.text
    assert "the event table is gone" in caplog.text


async def test_without_event_tracking_nothing_is_recorded():
    events = AdminEvents(None)

    await events.record(_request(), None, EventType.CREATE, Product)  # type: ignore[arg-type]

    assert not events.enabled
