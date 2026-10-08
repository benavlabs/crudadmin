"""Admin authentication, built on crudauth.

crudauth keeps the sessions, CSRF tokens and login lockout, and verifies
passwords. This module configures it for the admin: admins log in by username,
the session cookies and storage keys are namespaced so the admin can run beside
a host app that uses crudauth too, and password hashes written by crudadmin 0.5
and earlier keep verifying (and are upgraded on the next login).
"""

import logging
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from crudauth import (
    AuthHooks,
    CRUDAuth,
    DatabaseStore,
    IdentityConfig,
    Principal,
    SessionTransport,
    SudoConfig,
)
from crudauth.core import CookieConfig
from crudauth.ratelimit import LockoutConfig
from crudauth.utils import verify_plain_bcrypt
from fastapi import Depends, Request

from ..admin_user.schemas import (
    AdminUserCreate,
    AdminUserRead,
    AdminUserUpdate,
    AdminUserUpdateInternal,
)
from ..core.db import DatabaseConfig

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "crudadmin_session"
CSRF_COOKIE_NAME = "crudadmin_csrf"
SESSION_STORAGE_PREFIX = "crudadmin:session:"
CSRF_STORAGE_PREFIX = "crudadmin:csrf:"
RATE_LIMIT_PREFIX = "crudadmin:rl:"
STORE_TABLE = "crudadmin_auth_store"
COUNTER_TABLE = "crudadmin_auth_counters"

SESSION_BACKENDS = ("memory", "redis", "database")

ADMIN_LOGIN_LOCKOUT = LockoutConfig(
    on_login_success="clear_all",
    lockout_max_seconds=5 * 60,
)


class ReauthenticationRequired(Exception):
    """The route needs a recent password confirmation (sudo) the session doesn't have.

    The admin app turns it into a redirect to the password confirmation page, which
    sends the admin back to ``next_path`` once confirmed.
    """

    def __init__(self, next_path: str) -> None:
        super().__init__("Re-authentication required")
        self.next_path = next_path


class AdminAuthentication:
    """The admin's crudauth instance and the dependencies routes use.

    Args:
        database_config: The admin database; admins and, with the ``database``
            backend, sessions and lockout counters live there.
        secret_key: Keys the stored session and CSRF identifiers.
        cookie_path: Path the session cookies are scoped to (the admin's prefix).
        secure_cookies: Send the cookies over HTTPS only.
        session_backend: ``"memory"``, ``"redis"`` or ``"database"``.
        redis_client: The Redis client for the ``redis`` backend.
        session_timeout_minutes: Idle time after which a session ends.
        max_sessions_per_user: Sessions an admin may hold at once.
        cleanup_interval_minutes: How often idle sessions are swept.
        trusted_proxy_hops: Reverse proxies in front of the app; ``0`` ignores
            ``X-Forwarded-For``.
        lockout: Login lockout tuning. Defaults to [ADMIN_LOGIN_LOCKOUT][]: five
            failures lock the username and the IP, for a minute at first and at
            most five minutes. Anyone who knows an admin's username can lock it
            out this way, so the cap is kept short; ``allowed_ips`` keeps
            strangers away from the login page altogether.
        hooks: Login and logout hooks, used for the event log.
    """

    def __init__(
        self,
        database_config: DatabaseConfig,
        secret_key: str,
        *,
        cookie_path: str = "/",
        secure_cookies: bool = True,
        session_backend: str = "memory",
        redis_client: Any = None,
        session_timeout_minutes: int = 30,
        max_sessions_per_user: int = 5,
        cleanup_interval_minutes: int = 15,
        trusted_proxy_hops: int = 0,
        lockout: Optional[LockoutConfig] = None,
        hooks: Optional[AuthHooks] = None,
    ) -> None:
        if session_backend not in SESSION_BACKENDS:
            raise ValueError(
                f"Unknown session backend {session_backend!r}: expected one of "
                f"{', '.join(SESSION_BACKENDS)}"
            )
        self.db_config = database_config

        self.database_store: Optional[DatabaseStore] = None
        if session_backend == "database":
            self.database_store = DatabaseStore(
                database_config.admin_session_maker,
                store_table=STORE_TABLE,
                counter_table=COUNTER_TABLE,
            )

        self.session_transport = SessionTransport(
            backend=session_backend,
            redis_client=redis_client if session_backend == "redis" else None,
            cookie_name=SESSION_COOKIE_NAME,
            csrf_cookie_name=CSRF_COOKIE_NAME,
            storage_prefix=SESSION_STORAGE_PREFIX,
            csrf_storage_prefix=CSRF_STORAGE_PREFIX,
            cookies=CookieConfig(
                secure=secure_cookies, samesite="strict", path=cookie_path
            ),
            session_timeout_minutes=session_timeout_minutes,
            max_sessions_per_user=max_sessions_per_user,
            cleanup_interval_minutes=cleanup_interval_minutes,
        )

        self.auth = CRUDAuth(
            session=database_config.get_admin_db,
            user_model=database_config.AdminUser,
            SECRET_KEY=secret_key,
            identity=IdentityConfig(login=["username"], recovery=None),
            transports=[self.session_transport],
            database_store=self.database_store,
            rate_limit_prefix=RATE_LIMIT_PREFIX,
            lockout=lockout or ADMIN_LOGIN_LOCKOUT,
            trusted_proxy_hops=trusted_proxy_hops,
            legacy_verifiers=[verify_plain_bcrypt],
            sudo=SudoConfig(),
            hooks=hooks,
            warn_on_memory_backend=False,
        )
        if session_backend == "memory":
            logger.warning(
                "crudadmin: sessions and login lockout counters are kept in memory, "
                "per process. With more than one worker, admins are logged out "
                "between workers and lockout counts failures per worker. Use "
                "session_backend='redis' or 'database' in production."
            )

        self.auth_models: dict[str, dict[str, Any]] = {
            self.db_config.AdminUser.__name__: {
                "model": self.db_config.AdminUser,
                "crud": self.db_config.crud_users,
                "create_schema": AdminUserCreate,
                "update_schema": AdminUserUpdate,
                "update_internal_schema": AdminUserUpdateInternal,
                "delete_schema": None,
                "select_schema": AdminUserRead,
            }
        }

        self._current_user = self._user_dependency(self.auth.current_user())
        self._current_superuser = self._user_dependency(
            self.auth.current_user(superuser=True)
        )
        self._recent_superuser = self._sudo_dependency(self._current_superuser)

    @property
    def session_cookie_name(self) -> str:
        return SESSION_COOKIE_NAME

    @property
    def csrf_cookie_name(self) -> str:
        return CSRF_COOKIE_NAME

    async def initialize(self) -> None:
        """Create the database backend's tables, then open crudauth's stores."""
        if self.database_store is not None:
            await self.database_store.create_tables()
        await self.auth.initialize()

    async def shutdown(self) -> None:
        await self.auth.shutdown()

    def _user_dependency(
        self, principal_dependency: Callable[..., Any]
    ) -> Callable[..., Any]:
        sessions = self.auth.sessions

        async def current_admin(
            request: Request, principal: Principal = Depends(principal_dependency)
        ) -> AdminUserRead:
            user = AdminUserRead.model_validate(principal.user, from_attributes=True)
            request.state.user = user.model_dump()
            request.state.principal = principal
            session_id = principal.metadata.get("session_id")
            if session_id:
                request.state.session_handle = sessions.session_handle(str(session_id))
            return user

        return current_admin

    def _sudo_dependency(
        self, user_dependency: Callable[..., Any]
    ) -> Callable[..., Any]:
        sudo = self.auth.sudo
        assert sudo is not None

        async def recently_confirmed(
            request: Request, user: AdminUserRead = Depends(user_dependency)
        ) -> AdminUserRead:
            principal: Principal = request.state.principal
            if not await sudo.is_elevated(principal):
                referer = request.headers.get("referer")
                next_path = request.url.path
                if request.method != "GET" and referer:
                    parts = urlsplit(referer)
                    next_path = parts.path + (f"?{parts.query}" if parts.query else "")
                raise ReauthenticationRequired(next_path)
            return user

        return recently_confirmed

    def get_current_user(self) -> Callable[..., Any]:
        """The dependency that resolves the request's session to an active admin.

        Raises 401 without a valid session, and 403 on a POST, PUT, PATCH or
        DELETE without a valid ``X-CSRF-Token`` header.
        """
        return self._current_user

    def get_current_superuser(self) -> Callable[..., Any]:
        """Like [get_current_user][], and 403 unless the admin is a superuser."""
        return self._current_superuser

    def get_recently_confirmed_superuser(self) -> Callable[..., Any]:
        """A superuser who confirmed their password in the last few minutes.

        Guards changes to admin accounts: a stolen session alone can't create an
        admin or change one's password. Without a recent confirmation it raises
        [ReauthenticationRequired][], which redirects to the confirmation page.
        """
        return self._recent_superuser
