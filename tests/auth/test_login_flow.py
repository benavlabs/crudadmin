"""The admin login flow on crudauth: login, logout, lockout, CSRF and the event log."""

import logging

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import DeclarativeBase

from crudadmin import CRUDAdmin
from crudadmin.core.db import DatabaseConfig

CREDENTIALS = {"username": "admin", "password": "correct-horse-battery"}
SESSION_COOKIE = "crudadmin_session"
CSRF_COOKIE = "crudadmin_csrf"


async def _get_session():
    yield None


def _build(tmp_path, **kwargs):
    class AdminBase(DeclarativeBase):
        pass

    admin = CRUDAdmin(
        session=_get_session,
        SECRET_KEY="x" * 32,
        db_config=DatabaseConfig(
            base=AdminBase,
            session=_get_session,
            admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        ),
        secure_cookies=False,
        session_timeout_minutes=480,
        initial_admin=CREDENTIALS,
        **kwargs,
    )
    app = FastAPI()
    app.mount("/admin", admin.app)
    return admin, app


@pytest.fixture
def admin_and_client(tmp_path):
    admin, app = _build(tmp_path, track_events=True)
    with TestClient(app, follow_redirects=False, client=("127.0.0.1", 50000)) as client:
        assert client.portal is not None
        client.portal.call(admin.initialize)
        yield admin, client
        assert client.portal is not None
        client.portal.call(admin.shutdown)


@pytest.fixture
def client(admin_and_client):
    return admin_and_client[1]


def _login(client, password=CREDENTIALS["password"]):
    return client.post(
        "/admin/login", data={"username": CREDENTIALS["username"], "password": password}
    )


def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies[CSRF_COOKIE]}


class TestLogin:
    def test_login_sets_namespaced_cookies_and_opens_the_dashboard(self, client):
        response = _login(client)

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"
        assert {SESSION_COOKIE, CSRF_COOKIE} <= set(client.cookies.keys())
        assert client.get("/admin/").status_code == 200

    def test_session_cookie_is_httponly_strict_and_has_no_fixed_lifetime(self, client):
        response = _login(client)

        cookie = next(
            c
            for c in response.headers.get_list("set-cookie")
            if c.startswith(f"{SESSION_COOKIE}=")
        ).lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/admin/" in cookie
        assert "max-age" not in cookie and "expires" not in cookie

    @pytest.mark.parametrize(
        "username, password",
        [("admin", "wrong-password"), ("nobody", "correct-horse-battery")],
    )
    def test_bad_credentials_get_one_generic_message(self, client, username, password):
        response = client.post(
            "/admin/login", data={"username": username, "password": password}
        )

        assert response.status_code == 401
        assert "Invalid username or password." in response.text
        assert SESSION_COOKIE not in client.cookies

    def test_repeated_failures_lock_the_login(self, client):
        statuses = [_login(client, "wrong-password").status_code for _ in range(6)]

        assert statuses[:5] == [401] * 5
        assert statuses[5] == 429
        locked = _login(client)
        assert locked.status_code == 429
        assert "Too many failed attempts" in locked.text

    def test_cross_site_login_is_refused(self, client):
        response = client.post(
            "/admin/login",
            data=CREDENTIALS,
            headers={"Sec-Fetch-Site": "cross-site"},
        )

        assert response.status_code == 403
        assert SESSION_COOKIE not in client.cookies

    def test_login_page_shows_only_known_messages(self, client):
        crafted = client.get("/admin/login", params={"error": "Call +1-555 now"})
        known = client.get("/admin/login", params={"error": "session_ended"})

        assert "Call +1-555 now" not in crafted.text
        assert "Your session has ended" in known.text

    def test_logged_in_admin_skips_the_login_page(self, client):
        _login(client)

        response = client.get("/admin/login")

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/"

    def test_session_ids_never_reach_the_logs(self, client, caplog):
        caplog.set_level(logging.DEBUG)

        _login(client)
        session_id = client.cookies[SESSION_COOKIE]
        csrf_token = client.cookies[CSRF_COOKIE]
        client.get("/admin/")
        client.get("/admin/management/sessions/content")
        client.post("/admin/logout", headers={"X-CSRF-Token": csrf_token})

        assert caplog.records
        assert session_id not in caplog.text
        assert csrf_token not in caplog.text

    def test_inactive_admin_cannot_log_in_and_loses_open_sessions(
        self, admin_and_client
    ):
        admin, client = admin_and_client
        _login(client)
        assert client.get("/admin/").status_code == 200

        async def deactivate():
            async with admin.db_config.admin_session_maker() as db:
                await db.execute(
                    update(admin.db_config.AdminUser).values(is_active=False)
                )
                await db.commit()

        assert client.portal is not None

        client.portal.call(deactivate)

        assert client.get("/admin/").status_code == 303
        assert _login(client).status_code == 401


class TestLegacyPasswordHash:
    def test_a_0_5_hash_logs_in_and_is_upgraded(self, admin_and_client):
        """crudadmin 0.5 hashed the raw password with bcrypt; crudauth pre-hashes it."""
        admin, client = admin_and_client
        legacy = bcrypt.hashpw(
            CREDENTIALS["password"].encode(), bcrypt.gensalt()
        ).decode()
        user_model = admin.db_config.AdminUser

        async def set_hash(value):
            async with admin.db_config.admin_session_maker() as db:
                await db.execute(update(user_model).values(hashed_password=value))
                await db.commit()

        async def stored_hash():
            async with admin.db_config.admin_session_maker() as db:
                return (await db.execute(select(user_model.hashed_password))).scalar()

        assert client.portal is not None

        client.portal.call(set_hash, legacy)

        assert _login(client).status_code == 303
        upgraded = client.portal.call(stored_hash)
        assert upgraded != legacy

        client.post("/admin/logout", headers=_csrf(client))
        assert _login(client).status_code == 303


class TestCSRF:
    def test_logout_needs_the_csrf_header(self, client):
        _login(client)

        assert client.post("/admin/logout").status_code == 403
        assert client.get("/admin/").status_code == 200

        response = client.post("/admin/logout", headers=_csrf(client))
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        assert client.get("/admin/").status_code == 303

    def test_logout_is_not_a_get(self, client):
        _login(client)

        assert client.get("/admin/logout").status_code in (303, 405)
        assert client.get("/admin/").status_code == 200

    def test_writes_need_the_csrf_header(self, client):
        _login(client)

        missing = client.post(
            "/admin/management/sessions/revoke", data={"user_id": 1, "handle": "x"}
        )
        wrong = client.post(
            "/admin/management/sessions/revoke",
            data={"user_id": 1, "handle": "x"},
            headers={"X-CSRF-Token": "forged"},
        )
        valid = client.post(
            "/admin/management/sessions/revoke",
            data={"user_id": 1, "handle": "x"},
            headers=_csrf(client),
        )

        assert missing.status_code == 403
        assert wrong.status_code == 403
        assert valid.status_code == 200


class TestHtmx:
    def test_anonymous_htmx_request_gets_hx_redirect(self, client):
        response = client.get(
            "/admin/dashboard-content", headers={"HX-Request": "true"}
        )

        assert response.status_code == 204
        assert response.headers["HX-Redirect"] == "/admin/login?error=login_required"


class TestEventLog:
    def test_a_passed_in_db_config_gets_event_tables(self, admin_and_client):
        """track_events used to need the event models on a custom db_config."""
        admin, _ = admin_and_client

        assert admin.db_config.AdminEventLog is not None
        assert admin.db_config.AdminAuditLog is not None

    def test_logins_logouts_and_failures_are_recorded(self, admin_and_client):
        admin, client = admin_and_client
        _login(client, "wrong-password")
        _login(client)
        client.post("/admin/logout", headers=_csrf(client))

        async def events():
            model = admin.db_config.AdminEventLog
            async with admin.db_config.admin_session_maker() as db:
                rows = (
                    (await db.execute(select(model).order_by(model.id))).scalars().all()
                )
                return [
                    (r.event_type.value, r.status.value, r.session_id) for r in rows
                ]

        recorded = client.portal.call(events)

        kinds = [(kind, status) for kind, status, _ in recorded]
        assert kinds == [
            ("failed_login", "failure"),
            ("login", "success"),
            ("logout", "success"),
        ]
        login_handle, logout_handle = recorded[1][2], recorded[2][2]
        assert login_handle == logout_handle != "unknown"


FETCH = {"X-CRUDAdmin-Fetch": "1"}


class TestFetchSubmissions:
    """admin.js submits forms with fetch; a redirect comes back as a 204 naming it.

    The page then navigates once, instead of fetch loading the target page and
    the page loading it again.
    """

    def test_a_redirect_becomes_a_204_with_the_target(self, client):
        _login(client)

        response = client.post(
            "/admin/sudo",
            data={"password": CREDENTIALS["password"], "next": "/admin/"},
            headers={**_csrf(client), **FETCH},
        )

        assert response.status_code == 204
        assert response.headers["X-CRUDAdmin-Location"] == "/admin/"
        assert "location" not in response.headers

    def test_logout_still_clears_the_cookies(self, client):
        _login(client)

        response = client.post("/admin/logout", headers={**_csrf(client), **FETCH})

        assert response.status_code == 204
        assert response.headers["X-CRUDAdmin-Location"] == "/admin/login"
        cleared = " ".join(response.headers.get_list("set-cookie"))
        assert "crudadmin_session=" in cleared
        assert client.get("/admin/").status_code == 303

    def test_an_expired_session_points_to_the_login_page(self, client):
        response = client.post("/admin/logout", headers=FETCH)

        assert response.status_code == 204
        assert response.headers["X-CRUDAdmin-Location"].startswith("/admin/login")

    def test_pages_and_errors_pass_through(self, client):
        _login(client)

        page = client.post(
            "/admin/sudo",
            data={"password": "wrong", "next": "/admin/"},
            headers={**_csrf(client), **FETCH},
        )

        assert page.status_code == 401
        assert "Incorrect password." in page.text

    def test_requests_without_the_header_still_get_redirects(self, client):
        _login(client)

        response = client.post("/admin/logout", headers=_csrf(client))

        assert response.status_code == 303


class TestLockoutDefaults:
    def test_admin_lockout_is_short_and_cleared_by_a_successful_login(
        self, admin_and_client
    ):
        admin, _ = admin_and_client
        policy = admin.admin_authentication.auth.runtime.lockout

        assert policy.lockout_max == 5 * 60
        assert policy.on_login_success == "clear_all"

    def test_a_given_lockout_config_is_used_instead(self, tmp_path):
        from crudauth.ratelimit import LockoutConfig

        custom = LockoutConfig(max_attempts=3, lockout_max_seconds=900)
        admin, _ = _build(tmp_path, lockout=custom)
        policy = admin.admin_authentication.auth.runtime.lockout

        assert policy.max_attempts == 3
        assert policy.lockout_max == 900
