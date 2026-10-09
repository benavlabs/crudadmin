"""SessionConfig and AccessConfig, and the flat arguments they replace."""

import warnings

import pytest
from crudauth.ratelimit import LockoutConfig
from pydantic import ValidationError

from crudadmin import AccessConfig, CRUDAdmin, RedisConfig, SessionConfig
from crudadmin.admin_interface.middleware import (
    HTTPSRedirectMiddleware,
    IPRestrictionMiddleware,
)

LOCKOUT = LockoutConfig(lockout_max_seconds=60)

DEPRECATED_ARGUMENTS = [
    ("session_backend", "database", "sessions", "backend"),
    ("redis_config", RedisConfig(host="r"), "sessions", "redis"),
    ("session_timeout_minutes", 45, "sessions", "timeout_minutes"),
    ("max_sessions_per_user", 2, "sessions", "max_per_admin"),
    ("cleanup_interval_minutes", 5, "sessions", "cleanup_interval_minutes"),
    ("secure_cookies", False, "sessions", "secure_cookies"),
    ("allowed_ips", ["10.0.0.1"], "access", "allowed_ips"),
    ("allowed_networks", ["10.0.0.0/8"], "access", "allowed_networks"),
    ("enforce_https", True, "access", "enforce_https"),
    ("https_port", 8443, "access", "https_port"),
    ("trusted_proxy_hops", 1, "access", "trusted_proxy_hops"),
    ("lockout", LOCKOUT, "access", "lockout"),
]


async def _no_session():
    yield None


def _admin(tmp_path, **kwargs) -> CRUDAdmin:
    return CRUDAdmin(
        session=_no_session,
        SECRET_KEY="x" * 32,
        admin_db_url=f"sqlite+aiosqlite:///{tmp_path}/admin.db",
        **kwargs,
    )


@pytest.mark.parametrize(
    "argument, value, group, field",
    DEPRECATED_ARGUMENTS,
    ids=[argument for argument, *_ in DEPRECATED_ARGUMENTS],
)
def test_a_deprecated_argument_lands_in_its_config_and_warns_once(
    tmp_path, argument, value, group, field
):
    with pytest.warns(DeprecationWarning, match=argument) as caught:
        admin = _admin(tmp_path, **{argument: value})

    assert getattr(getattr(admin, group), field) == value
    [warning] = [w for w in caught if "deprecated" in str(w.message)]
    assert warning.filename == __file__


def test_several_deprecated_arguments_warn_once_naming_each(tmp_path):
    with pytest.warns(DeprecationWarning) as caught:
        admin = _admin(tmp_path, secure_cookies=False, session_timeout_minutes=10)

    [warning] = caught
    assert "secure_cookies" in str(warning.message)
    assert "session_timeout_minutes" in str(warning.message)
    assert "sessions=SessionConfig(...)" in str(warning.message)
    assert (admin.sessions.secure_cookies, admin.sessions.timeout_minutes) == (
        False,
        10,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sessions": SessionConfig(), "secure_cookies": False},
        {"access": AccessConfig(), "allowed_ips": ["10.0.0.1"]},
    ],
    ids=["sessions", "access"],
)
def test_a_deprecated_argument_beside_its_config_is_refused(tmp_path, kwargs):
    with pytest.raises(ValueError, match="not as separate arguments"):
        _admin(tmp_path, **kwargs)


def test_the_defaults_warn_nothing(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        admin = _admin(tmp_path)

    assert admin.sessions == SessionConfig()
    assert admin.access == AccessConfig()


def test_the_configs_reach_the_session_manager_and_the_middleware(tmp_path):
    admin = _admin(
        tmp_path,
        sessions=SessionConfig(max_per_admin=2, timeout_minutes=12),
        access=AccessConfig(allowed_ips=["10.0.0.1"], enforce_https=True),
    )

    assert admin.session_manager.max_sessions == 2
    assert admin.session_manager.session_timeout.total_seconds() == 12 * 60
    installed = {middleware.cls for middleware in admin.app.user_middleware}
    assert {IPRestrictionMiddleware, HTTPSRedirectMiddleware} <= installed


@pytest.mark.parametrize(
    "build",
    [
        lambda: SessionConfig(timeout_minutes=0),
        lambda: SessionConfig(max_per_admin=0),
        lambda: SessionConfig.model_validate({"backend_name": "redis"}),
        lambda: AccessConfig(https_port=70000),
        lambda: AccessConfig(trusted_proxy_hops=-1),
        lambda: AccessConfig(lockout="strict"),
    ],
)
def test_the_configs_validate_their_values(build):
    with pytest.raises(ValidationError):
        build()


def test_a_redis_dict_is_read_as_a_redis_config():
    assert SessionConfig(redis={"host": "h", "db": 3}).redis == RedisConfig(
        host="h", db=3
    )
