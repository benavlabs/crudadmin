# Session Management API Reference

Since 0.6, CRUDAdmin keeps admin sessions with [crudauth](https://benavlabs.github.io/crudauth). This page covers what CRUDAdmin itself exposes: the backend configuration classes and the session manager on a `CRUDAdmin` instance. For choosing a backend and the settings around sessions, see [Session Backends](../usage/session-backends.md).

## Configuration classes

### RedisConfig

Connection settings for `session_backend="redis"`. Pass an instance, or a dict with the same keys, as `redis_config`.

::: crudadmin.session.configs.RedisConfig
    rendering:
      show_if_no_docstring: true

| Field | Default | Meaning |
|-------|---------|---------|
| `url` | `None` | A full connection URL. When set, it is used as is (a `rediss://` URL keeps TLS) and the other address fields are ignored. |
| `host` | `"localhost"` | Server host |
| `port` | `6379` | Server port, 1 to 65535 |
| `db` | `0` | Database number |
| `username` | `None` | ACL username (Redis 6+) |
| `password` | `None` | Password |
| `pool_size` | `None` | Maximum number of connections in the client's pool |
| `connect_timeout` | `None` | Connection timeout in seconds |

```python
from crudadmin import CRUDAdmin, RedisConfig

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    redis_config=RedisConfig(url="redis://localhost:6379/0", pool_size=10),
)
```

### MemcachedConfig

The Memcached backend was removed in 0.6. The class is kept so existing imports keep working, but passing it to `CRUDAdmin` (or using `session_backend="memcached"`) raises a `ValueError` that names the replacements, `redis` and `database`.

::: crudadmin.session.configs.MemcachedConfig
    rendering:
      show_if_no_docstring: true

## The session manager

`CRUDAdmin.session_manager` is crudauth's `SessionManager` for the admin's sessions. It is available as soon as the `CRUDAdmin` instance exists; call `admin.initialize()` before using it.

```python
sessions = await admin.session_manager.list_for_user(user_id)
```

Each entry is a dict with:

| Key | Meaning |
|-----|---------|
| `id` | The session's public handle, safe to show and to pass back; never the session id |
| `device` | Browser and operating system parsed from the user agent |
| `ip` | Client IP address |
| `created_at` | When the admin signed in |
| `last_activity` | The last request on the session |
| `current` | Whether this is the session given as `current_session_id` |

Ending sessions:

```python
await admin.session_manager.revoke_by_handle(handle, owner_id=user_id)
await admin.session_manager.revoke_all(user_id)
await admin.session_manager.revoke_all(user_id, exclude=current_session_id)
```

`revoke_by_handle` ends one session of `owner_id`, found by the handle from `list_for_user`, and returns whether one was ended. `revoke_all` ends every session of the admin, optionally keeping one, and returns how many were ended.

The admin interface uses the same calls on its **Sessions** page (`/management/sessions`): admins see and end their own sessions, superusers everyone's.

For the rest of the session manager's API, see [crudauth's documentation](https://benavlabs.github.io/crudauth).

## Session settings on CRUDAdmin

These `CRUDAdmin` arguments configure sessions and logins. The [Session Backends](../usage/session-backends.md) guide explains each one.

| Argument | Default | Meaning |
|----------|---------|---------|
| `session_backend` | `"memory"` | `"memory"`, `"redis"` or `"database"` |
| `redis_config` | `None` | `RedisConfig` or dict, for the `redis` backend |
| `session_timeout_minutes` | `30` | Idle time after which a session ends |
| `max_sessions_per_user` | `5` | Sessions one admin may hold at once |
| `cleanup_interval_minutes` | `15` | Minimum time between sweeps of idle sessions |
| `secure_cookies` | `True` | Send the session cookies over HTTPS only |
| `trusted_proxy_hops` | `0` | Reverse proxies in front of the app; `0` ignores `X-Forwarded-For` |
| `lockout` | 5 failures, 1 to 5 minutes | A crudauth `LockoutConfig` for the login lockout |
| `track_sessions_in_db` | `False` | Deprecated; see below |

## Names CRUDAdmin uses

| Name | Value |
|------|-------|
| Session cookie | `crudadmin_session` |
| CSRF cookie | `crudadmin_csrf` |
| CSRF request header | `X-CSRF-Token` |
| Session key prefix | `crudadmin:session:` |
| CSRF key prefix | `crudadmin:csrf:` |
| Lockout counter prefix | `crudadmin:rl:` |
| `database` backend tables | `crudadmin_auth_store`, `crudadmin_auth_counters` |

## Deprecated and removed

- `session_backend="hybrid"` runs on `redis` with a `DeprecationWarning`, and will be removed.
- `track_sessions_in_db=True` emits a `DeprecationWarning`. With the `memory` backend it switches to `database`; with `redis` it changes nothing.
- `session_backend="memcached"` and `memcached_config` raise a `ValueError` at startup.
- The `crudadmin.session.manager`, `crudadmin.session.storage` and `crudadmin.session.backends` modules were removed; `crudadmin.session` now only holds `RedisConfig` and `MemcachedConfig`.
- Sessions are no longer stored in an `admin_session` table. After upgrading, you can drop that table.
