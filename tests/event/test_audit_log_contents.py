"""Regression tests for what the audit log stores.

Metadata: the create schema called the field ``metadata`` while the column is
``audit_metadata``. ``metadata`` is reserved on SQLAlchemy models, so the value
was silently dropped and every audit row stored ``{}``.

Secrets: snapshots copied every column, so updating an admin user wrote
``hashed_password`` into an audit row any admin can read.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from crudadmin.event import EventStatus, EventType
from crudadmin.event.models import create_admin_audit_log, create_admin_event_log
from crudadmin.event.schemas import AdminAuditLogCreate, AdminAuditLogRead
from crudadmin.event.service import REDACTED, EventService, redact_secrets


@pytest.fixture
async def audit_env():
    class Base(DeclarativeBase):
        pass

    event_log = create_admin_event_log(Base)
    audit_log = create_admin_audit_log(Base)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    service = EventService(
        SimpleNamespace(AdminEventLog=event_log, AdminAuditLog=audit_log)
    )
    yield service, audit_log, async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _write_audit(service, audit_log, session_factory, **audit_kwargs):
    async with session_factory() as db:
        event = await service.log_event(
            db=db,
            event_type=EventType.UPDATE,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="handle",
            request=SimpleNamespace(client=None, headers={}),
            resource_type="AdminUser",
            resource_id="1",
        )
        await service.create_audit_log(
            db=db,
            event_id=event.id,
            resource_type="AdminUser",
            resource_id="1",
            action="update",
            **audit_kwargs,
        )
        await db.commit()
        return (await db.execute(audit_log.__table__.select())).mappings().one()


def test_schema_accepts_metadata_as_an_alias():
    audit = AdminAuditLogCreate(
        event_id=1,
        resource_type="Note",
        resource_id="1",
        action="create",
        metadata={"ip": "10.0.0.1"},
    )

    assert audit.model_dump()["audit_metadata"] == {"ip": "10.0.0.1"}
    assert "metadata" not in audit.model_dump()


@pytest.mark.asyncio
async def test_audit_metadata_is_written_and_read_back(audit_env):
    row = await _write_audit(
        *audit_env,
        new_state={"text": "hi"},
        metadata={"ip_address": "10.0.0.1"},
    )

    assert row["audit_metadata"] == {"ip_address": "10.0.0.1"}
    read = AdminAuditLogRead.model_validate(dict(row))
    assert read.audit_metadata == {"ip_address": "10.0.0.1"}


@pytest.mark.asyncio
async def test_password_hashes_are_not_stored(audit_env):
    old_hash = "$2b$12$" + "o" * 53
    new_hash = "$2b$12$" + "n" * 53

    row = await _write_audit(
        *audit_env,
        previous_state={"username": "admin", "hashed_password": old_hash},
        new_state={"username": "root", "hashed_password": new_hash},
    )

    stored = str(dict(row))
    assert old_hash not in stored
    assert new_hash not in stored
    assert row["previous_state"]["hashed_password"] == REDACTED
    assert row["new_state"]["username"] == "root"
    # The change is still recorded, without the values
    assert row["changes"]["hashed_password"] == {"old": REDACTED, "new": REDACTED}
    assert row["changes"]["username"] == {"old": "admin", "new": "root"}


def test_redaction_applies_at_any_depth_and_keeps_other_values():
    data = {
        "name": "x",
        "api_key": "k",
        "nested": {"client_secret": "s", "count": 3},
        "items": [{"csrf_token": "t", "ok": True}],
        "password": None,
    }

    assert redact_secrets(data) == {
        "name": "x",
        "api_key": REDACTED,
        "nested": {"client_secret": REDACTED, "count": 3},
        "items": [{"csrf_token": REDACTED, "ok": True}],
        "password": None,
    }


@pytest.mark.asyncio
async def test_event_details_and_audit_metadata_are_redacted(audit_env):
    service, audit_log, session_factory = audit_env
    password_hash = "$2b$12$" + "d" * 53
    details = {
        "resource_details": {
            "changes": {"username": "root", "hashed_password": password_hash}
        }
    }

    async with session_factory() as db:
        event = await service.log_event(
            db=db,
            event_type=EventType.UPDATE,
            status=EventStatus.SUCCESS,
            user_id=1,
            session_id="handle",
            request=SimpleNamespace(client=None, headers={}),
            details=details,
        )
        await service.create_audit_log(
            db=db,
            event_id=event.id,
            resource_type="AdminUser",
            resource_id="1",
            action="update",
            metadata=details,
        )
        await db.commit()
        audit = (await db.execute(audit_log.__table__.select())).mappings().one()

    assert password_hash not in str(event.details)
    assert password_hash not in str(dict(audit))
    assert event.details["resource_details"]["changes"] == {
        "username": "root",
        "hashed_password": REDACTED,
    }
