"""Who may do what: superusers manage admins, and account changes need a fresh password."""

import pytest
from crudauth import get_password_hash
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin, SessionConfig
from crudadmin.core.db import DatabaseConfig
from crudadmin.event import create_admin_audit_log, create_admin_event_log

ROOT = {"username": "root", "password": "root-password-123"}
STAFF = {"username": "staff", "password": "staff-password-123"}
CSRF_COOKIE = "crudadmin_csrf"


async def _get_session():
    yield None


@pytest.fixture
def admin(tmp_path):
    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
            admin_event_log=create_admin_event_log(AdminBase),
            admin_audit_log=create_admin_audit_log(AdminBase),
        ),
        sessions=SessionConfig(secure_cookies=False),
        track_events=True,
        initial_admin=ROOT,
    )
    return admin


@pytest.fixture
def app(admin):
    app = FastAPI()
    app.mount("/admin", admin.app)
    return app


@pytest.fixture
def started(admin, app):
    """Start the app once, add a non-superuser admin, and hand out client factories."""
    clients = []

    def client():
        c = TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000))
        c.__enter__()
        clients.append(c)
        return c

    first = client()
    first.portal.call(admin.initialize)

    async def add_staff():
        model = admin.db_config.AdminUser
        async with admin.db_config.admin_session_maker() as db:
            db.add(
                model(
                    username=STAFF["username"],
                    hashed_password=get_password_hash(STAFF["password"]),
                )
            )
            await db.commit()

    first.portal.call(add_staff)
    yield client, first
    for c in clients:
        c.__exit__(None, None, None)


def _login(client, who):
    response = client.post("/admin/login", data=who)
    assert response.status_code == 303, response.text
    return client


def _csrf(client):
    return {"X-CSRF-Token": client.cookies[CSRF_COOKIE]}


def _confirm(client, password, next_path="/admin/"):
    return client.post(
        "/admin/sudo",
        data={"password": password, "next": next_path},
        headers=_csrf(client),
    )


async def _staff_id(admin):
    model = admin.db_config.AdminUser
    async with admin.db_config.admin_session_maker() as db:
        return (
            await db.execute(select(model.id).where(model.username == "staff"))
        ).scalar_one()


class TestSuperuserOnly:
    @pytest.mark.parametrize(
        "path",
        [
            "/admin/AdminUser/",
            "/admin/AdminUser/get_model_list",
            "/admin/AdminUser/create_page",
            "/admin/management/events",
            "/admin/management/events/content",
        ],
    )
    def test_staff_gets_403(self, started, path):
        new_client, _ = started
        staff = _login(new_client(), STAFF)

        assert staff.get(path).status_code == 403

    def test_staff_still_reaches_the_dashboard_health_and_own_sessions(self, started):
        new_client, _ = started
        staff = _login(new_client(), STAFF)

        assert staff.get("/admin/").status_code == 200
        assert staff.get("/admin/management/health").status_code == 200
        sessions = staff.get("/admin/management/sessions/content")
        assert sessions.status_code == 200
        assert "staff" in sessions.text
        assert "root" not in sessions.text

    def test_superuser_sees_every_admins_sessions(self, started):
        new_client, _ = started
        _login(new_client(), STAFF)
        root = _login(new_client(), ROOT)

        sessions = root.get("/admin/management/sessions/content")

        assert "staff" in sessions.text and "root" in sessions.text


class TestSessionRevocation:
    def test_staff_cannot_end_someone_elses_session(self, started, admin):
        new_client, _ = started
        root = _login(new_client(), ROOT)
        staff = _login(new_client(), STAFF)

        response = staff.post(
            "/admin/management/sessions/revoke",
            data={"user_id": 1, "handle": "anything"},
            headers=_csrf(staff),
        )

        assert response.status_code == 403
        assert root.get("/admin/").status_code == 200

    def test_superuser_ends_another_admins_session(self, started, admin):
        new_client, first = started
        staff = _login(new_client(), STAFF)
        root = _login(new_client(), ROOT)
        staff_id = first.portal.call(_staff_id, admin)
        handle = first.portal.call(admin.session_manager.list_for_user, staff_id)[0][
            "id"
        ]

        response = root.post(
            "/admin/management/sessions/revoke",
            data={"user_id": staff_id, "handle": handle},
            headers=_csrf(root),
        )

        assert response.status_code == 200
        assert staff.get("/admin/").status_code == 303


class TestRecentPasswordConfirmation:
    def test_account_pages_ask_for_the_password_first(self, started):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        response = root.get("/admin/AdminUser/create_page")

        assert response.status_code == 303
        assert response.headers["location"] == (
            "/admin/sudo?next=/admin/AdminUser/create_page"
        )
        page = root.get(response.headers["location"])
        assert page.status_code == 200
        assert "Confirm your password" in page.text

    def test_wrong_password_is_refused(self, started):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        response = _confirm(root, "not-the-password")

        assert response.status_code == 401
        assert "Incorrect password." in response.text
        assert root.get("/admin/AdminUser/create_page").status_code == 303

    def test_confirmed_password_opens_account_pages_and_returns_to_them(self, started):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        confirmed = _confirm(root, ROOT["password"], "/admin/AdminUser/create_page")

        assert confirmed.status_code == 303
        assert confirmed.headers["location"] == "/admin/AdminUser/create_page"
        assert root.get("/admin/AdminUser/create_page").status_code == 200

    def test_next_cannot_leave_the_site(self, started):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        confirmed = _confirm(root, ROOT["password"], "https://evil.example/")

        assert confirmed.headers["location"] == "/admin/"

    def test_account_writes_need_the_confirmation_too(self, started, admin):
        new_client, first = started
        root = _login(new_client(), ROOT)
        staff_id = first.portal.call(_staff_id, admin)

        response = root.post(
            f"/admin/AdminUser/form_update/{staff_id}",
            data={"username": "renamed"},
            headers={
                **_csrf(root),
                "referer": f"http://testserver/admin/AdminUser/update/{staff_id}",
            },
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/sudo?next=")


class TestAccountChanges:
    def _update_staff(self, root, staff_id, **changes):
        """Post the update form as a browser does: checked boxes are sent as "on"."""
        still_active_checkbox = {"is_active": "on"}
        return root.post(
            f"/admin/AdminUser/form_update/{staff_id}",
            data={**still_active_checkbox, **changes},
            headers=_csrf(root),
        )

    def test_password_change_ends_that_admins_sessions(self, started, admin):
        new_client, first = started
        staff = _login(new_client(), STAFF)
        root = _login(new_client(), ROOT)
        _confirm(root, ROOT["password"])
        staff_id = first.portal.call(_staff_id, admin)

        response = self._update_staff(root, staff_id, password="brand-new-password")

        assert response.status_code == 303
        assert staff.get("/admin/").status_code == 303
        assert root.get("/admin/").status_code == 200
        assert new_client().post("/admin/login", data=STAFF).status_code == 401
        assert (
            new_client()
            .post(
                "/admin/login",
                data={"username": "staff", "password": "brand-new-password"},
            )
            .status_code
            == 303
        )

    def test_deactivation_ends_sessions_and_blocks_login(self, started, admin):
        new_client, first = started
        staff = _login(new_client(), STAFF)
        root = _login(new_client(), ROOT)
        _confirm(root, ROOT["password"])
        staff_id = first.portal.call(_staff_id, admin)

        response = self._update_staff(root, staff_id, is_active="false")

        assert response.status_code == 303
        assert staff.get("/admin/").status_code == 303
        assert new_client().post("/admin/login", data=STAFF).status_code == 401

    def test_the_last_active_superuser_cannot_be_demoted(self, started, admin):
        new_client, _ = started
        root = _login(new_client(), ROOT)
        _confirm(root, ROOT["password"])

        response = self._update_staff(root, 1, is_superuser="false")

        assert response.status_code != 303
        assert "At least one active superuser must remain." in response.text
        assert root.get("/admin/AdminUser/").status_code == 200

    def test_new_admins_are_not_superusers_by_default(self, started, admin):
        new_client, first = started
        root = _login(new_client(), ROOT)
        _confirm(root, ROOT["password"])

        created = root.post(
            "/admin/AdminUser/form_create",
            data={"username": "newbie", "password": "newbie-password-1"},
            headers=_csrf(root),
        )

        assert created.status_code == 303
        newbie = _login(
            new_client(), {"username": "newbie", "password": "newbie-password-1"}
        )
        assert newbie.get("/admin/AdminUser/").status_code == 403


class TestConfirmationErrors:
    def test_repeated_wrong_passwords_lock_the_confirmation(self, started):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        allowed_attempts = 3
        statuses = [
            _confirm(root, "not-the-password").status_code
            for _ in range(allowed_attempts)
        ]

        assert statuses == [401, 401, 429]
        locked = _confirm(root, ROOT["password"])
        assert locked.status_code == 429
        assert "Too many failed attempts" in locked.text

    def test_an_unexpected_error_is_a_server_error_not_a_wrong_password(
        self, started, admin
    ):
        new_client, _ = started
        root = _login(new_client(), ROOT)

        async def broken_elevate(*args, **kwargs):
            raise RuntimeError("session store unavailable")

        sudo = admin.admin_authentication.auth.sudo
        original_elevate = sudo.elevate
        sudo.elevate = broken_elevate
        try:
            with pytest.raises(RuntimeError, match="session store unavailable"):
                _confirm(root, ROOT["password"])
        finally:
            sudo.elevate = original_elevate


def test_no_password_hash_reaches_the_event_log(started, admin):
    new_client, first = started
    root = _login(new_client(), ROOT)
    _confirm(root, ROOT["password"])
    created = root.post(
        "/admin/AdminUser/form_create",
        data={"username": "newbie", "password": "newbie-password-1"},
        headers=_csrf(root),
    )
    assert created.status_code == 303
    user_model = admin.db_config.AdminUser

    async def newbie() -> tuple[int, str]:
        async with admin.db_config.admin_session_maker() as db:
            row = (
                await db.execute(
                    select(user_model.id, user_model.hashed_password).where(
                        user_model.username == "newbie"
                    )
                )
            ).one()
            return row.id, row.hashed_password

    newbie_id, first_hash = first.portal.call(newbie)
    updated = root.post(
        f"/admin/AdminUser/form_update/{newbie_id}",
        data={"password": "changed-password-2"},
        headers=_csrf(root),
    )
    assert updated.status_code == 303
    _, second_hash = first.portal.call(newbie)

    async def stored_events() -> str:
        async with admin.db_config.admin_session_maker() as db:
            events = (await db.execute(select(admin.db_config.AdminEventLog))).scalars()
            audits = (await db.execute(select(admin.db_config.AdminAuditLog))).scalars()
            return repr(
                [event.details for event in events]
                + [
                    (a.previous_state, a.new_state, a.changes, a.audit_metadata)
                    for a in audits
                ]
            )

    stored = first.portal.call(stored_events)
    assert "newbie" in stored
    assert first_hash not in stored
    assert second_hash not in stored
