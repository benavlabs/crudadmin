"""The settings ``CRUDAdmin`` groups: how sessions are kept, and who may reach the admin.

Before 0.7 each setting was a constructor argument of its own. Those arguments
still work, with a ``DeprecationWarning``, and are mapped onto these objects.
"""

import warnings
from typing import Any, TypeVar

from crudauth.ratelimit import LockoutConfig
from pydantic import BaseModel, ConfigDict, Field

from .session.configs import RedisConfig


class SessionConfig(BaseModel):
    """How admin sessions are kept.

    Args:
        backend: ``"memory"`` (one process), ``"redis"`` or ``"database"`` (the
            admin database). The last two share sessions and login lockout
            between workers.
        redis: The Redis server for the ``redis`` backend; a ``RedisConfig`` or a
            dict of its fields. Defaults to ``localhost:6379``.
        timeout_minutes: Idle time after which a session ends.
        max_per_admin: Sessions an admin may hold at once; logging in again ends
            the oldest.
        cleanup_interval_minutes: How often expired sessions are swept.
        secure_cookies: Send the session cookies over HTTPS only. Turn off only
            for local development over plain HTTP.

    Example:
        ```python
        SessionConfig(backend="redis", redis=RedisConfig(url=REDIS_URL))
        ```
    """

    model_config = ConfigDict(extra="forbid")

    backend: str = "memory"
    redis: RedisConfig | None = None
    timeout_minutes: int = Field(default=30, ge=1)
    max_per_admin: int = Field(default=5, ge=1)
    cleanup_interval_minutes: int = Field(default=15, ge=1)
    secure_cookies: bool = True


class AccessConfig(BaseModel):
    """Who may reach the admin, and how hard logging in is to guess.

    Args:
        allowed_ips: Client addresses allowed in. With these or
            ``allowed_networks`` set, every other client gets a 403.
        allowed_networks: Client networks allowed in, in CIDR notation.
        enforce_https: Redirect plain HTTP requests to HTTPS.
        https_port: The port HTTPS redirects go to.
        trusted_proxy_hops: Reverse proxies in front of the app, whose
            ``X-Forwarded-For`` entries are trusted for the client address.
            ``0`` ignores the header.
        lockout: Login lockout tuning, a crudauth ``LockoutConfig``. Defaults to
            five failures locking the username and the address, for one to five
            minutes.

    Example:
        ```python
        AccessConfig(allowed_networks=["10.0.0.0/8"], enforce_https=True)
        ```
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    allowed_ips: list[str] = Field(default_factory=list)
    allowed_networks: list[str] = Field(default_factory=list)
    enforce_https: bool = False
    https_port: int = Field(default=443, ge=1, le=65535)
    trusted_proxy_hops: int = Field(default=0, ge=0)
    lockout: LockoutConfig | None = None


SESSION_ARGUMENTS = {
    "session_backend": "backend",
    "redis_config": "redis",
    "session_timeout_minutes": "timeout_minutes",
    "max_sessions_per_user": "max_per_admin",
    "cleanup_interval_minutes": "cleanup_interval_minutes",
    "secure_cookies": "secure_cookies",
}

ACCESS_ARGUMENTS = {
    "allowed_ips": "allowed_ips",
    "allowed_networks": "allowed_networks",
    "enforce_https": "enforce_https",
    "https_port": "https_port",
    "trusted_proxy_hops": "trusted_proxy_hops",
    "lockout": "lockout",
}

ConfigType = TypeVar("ConfigType", SessionConfig, AccessConfig)


def config_from_arguments(
    config_class: type[ConfigType],
    argument: str,
    config: ConfigType | None,
    deprecated_arguments: dict[str, Any],
    field_names: dict[str, str],
) -> ConfigType:
    """The config object for ``argument``, built from deprecated arguments if any were passed.

    A deprecated argument counts as passed when it isn't None. Passing one warns;
    passing one together with the config object raises, since it isn't clear
    which should win.

    Raises:
        ValueError: If both deprecated arguments and the config object were passed.
    """
    passed = {
        name: value for name, value in deprecated_arguments.items() if value is not None
    }
    if not passed:
        return config if config is not None else config_class()
    names = ", ".join(passed)
    if config is not None:
        raise ValueError(
            f"Pass {names} inside {argument}={config_class.__name__}(...), not as "
            f"separate arguments alongside {argument}."
        )
    warnings.warn(
        f"{names}: these CRUDAdmin arguments are deprecated and will be removed. "
        f"Pass {argument}={config_class.__name__}(...) instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    return config_class(**{field_names[name]: value for name, value in passed.items()})
