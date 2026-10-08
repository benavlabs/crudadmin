# Session Backends

CRUDAdmin keeps admin sessions with [crudauth](https://benavlabs.github.io/crudauth). The session backend decides where sessions, CSRF tokens and login lockout counters are stored. This guide covers the three backends, how to pick one, and the settings that shape sessions and logins.

## Prerequisites

- CRUDAdmin 0.6 or later
- For the `redis` backend: a Redis server and `pip install "crudadmin[redis]"`

## Choosing a backend

| Backend | Where state lives | Shared between workers | Extra infrastructure | Use it for |
|---------|-------------------|------------------------|----------------------|------------|
| `memory` (default) | The process's memory | No | None | Development, tests, a single-process deployment |
| `redis` | Redis | Yes | A Redis server | Production with several workers or several hosts |
| `database` | Two tables in the admin database | Yes | None | Production with several workers, without Redis |

The backend holds more than sessions: login lockout counters live in the same place. With several workers on the `memory` backend, an admin who logs in on one worker is unknown to the next, and each worker counts failed logins on its own, so lockout is several times weaker. Any deployment that runs more than one worker process (for example `gunicorn -w 4` or `uvicorn --workers 4`) needs `redis` or `database`.

The value is case-insensitive.

## Memory

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
)
```

`memory` is the default. Sessions are lost when the process restarts. CRUDAdmin logs a warning at startup when this backend is active, as a reminder that it isn't suitable for multi-worker production.

## Redis

```python
from crudadmin import CRUDAdmin, RedisConfig

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    redis_config=RedisConfig(
        host="redis.internal",
        port=6379,
        db=0,
        username="crudadmin",
        password=REDIS_PASSWORD,
        pool_size=10,
        connect_timeout=5,
    ),
)
```

`redis_config` takes a `RedisConfig` or a plain dict with the same keys. Without it, CRUDAdmin connects to `localhost:6379`, database `0`.

A connection URL works too:

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    redis_config=RedisConfig(url="rediss://crudadmin:secret@redis.example.com:6380/1"),
)
```

The URL is passed to the Redis client whole, so a `rediss://` URL keeps TLS. `pool_size` sets the client's maximum number of connections and `connect_timeout` its connection timeout in seconds.

CRUDAdmin opens the Redis client and closes it in `admin.shutdown()`. All keys are prefixed, so the admin can share a Redis with your application, including one that uses crudauth itself:

| Prefix | Holds |
|--------|-------|
| `crudadmin:session:` | Sessions |
| `crudadmin:csrf:` | CSRF tokens |
| `crudadmin:rl:` | Login lockout counters |

## Database

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="database",
)
```

Sessions, CSRF tokens and lockout counters are stored in two tables of the admin database, `crudadmin_auth_store` and `crudadmin_auth_counters`. They are created by `admin.initialize()`. This uses crudauth's `DatabaseStore`, which opens a short-lived database session for each operation and works on SQLite, PostgreSQL and MySQL.

Choose it when you run several workers but don't run Redis. Every worker reads the same tables, so logins and lockout are shared. For a multi-worker deployment, point the admin database at PostgreSQL or MySQL with `admin_db_url`; SQLite serializes writers and suits a single host.

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    admin_db_url="postgresql+asyncpg://user:password@db.internal/admin",
    session_backend="database",
)
```

Expired rows are removed in small batches as writes go by, so the tables don't grow without bound.

## Application lifecycle

Call `admin.initialize()` before serving requests and `admin.shutdown()` when the application stops:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    await admin.initialize()
    yield
    await admin.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

`initialize()` creates the admin tables (and the `database` backend's tables), and opens the session stores. `shutdown()` closes the stores and the Redis client CRUDAdmin opened.

## How sessions work

Sessions are created at login and kept by crudauth:

- The browser gets two cookies, `crudadmin_session` and `crudadmin_csrf`. The names are namespaced, so the admin and an application on the same domain don't overwrite each other's cookies.
- `crudadmin_session` is `HttpOnly`. Both cookies are `SameSite=Strict`, scoped to the admin's mount path, and `Secure` unless you pass `secure_cookies=False` (only do that for local development over plain HTTP).
- The cookies have no fixed lifetime. A session ends when the admin is idle for `session_timeout_minutes`; every request moves that deadline forward.
- The store keeps an HMAC of each session id and CSRF token, keyed with `SECRET_KEY`, never the raw values. Read access to Redis or to the tables doesn't yield a working session. Changing `SECRET_KEY` signs every admin out.
- Logging in again from the same browser ends the session it presented.

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    session_timeout_minutes=60,
    max_sessions_per_user=3,
    cleanup_interval_minutes=15,
)
```

| Setting | Default | Meaning |
|---------|---------|---------|
| `session_timeout_minutes` | `30` | Idle time after which a session ends |
| `max_sessions_per_user` | `5` | Sessions one admin may hold at once; a login over the limit ends the least recently active one |
| `cleanup_interval_minutes` | `15` | Minimum time between sweeps of idle sessions; each store also expires idle sessions on its own |
| `secure_cookies` | `True` | Send the cookies over HTTPS only |

## CSRF protection

Every `POST`, `PUT`, `PATCH` and `DELETE` to the admin must carry the session's CSRF token in an `X-CSRF-Token` header, or it gets a `403`. A cookie is sent with cross-site requests but a custom header is not, so requiring the header is what blocks cross-site request forgery.

The admin's own pages handle this for you: the bundled `admin.js` reads the `crudadmin_csrf` cookie and adds the header to htmx requests, `fetch` calls, and the create and update forms. Logout is a `POST` for the same reason, so a link or an image on another page can't log an admin out.

If you call admin endpoints from your own scripts, read the `crudadmin_csrf` cookie and send it back as `X-CSRF-Token`.

## Login protection

### Lockout

Failed logins are counted per username and per IP address. With CRUDAdmin's defaults, five failures lock the login for a minute; repeated lockouts double the duration, up to five minutes. A successful login clears the counters.

Anyone who knows an admin's username can trigger that lockout, so the cap is deliberately short. To keep strangers away from the login page altogether, restrict it with `allowed_ips` or `allowed_networks`.

Pass a crudauth `LockoutConfig` to change the defaults:

```python
from crudauth.ratelimit import LockoutConfig

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    lockout=LockoutConfig(max_attempts=10, lockout_max_seconds=900),
)
```

### Client IP behind a proxy

`trusted_proxy_hops` tells CRUDAdmin how many reverse proxies sit in front of the application. It decides which address is used for lockout and recorded on sessions.

- `0` (the default) ignores `X-Forwarded-For` and uses the connecting address. Use it when clients connect to the application directly.
- `N` reads the `N`-th entry of `X-Forwarded-For` counted from the right, the address your outermost trusted proxy saw. Values a client adds on the left are never read.

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    session_backend="redis",
    trusted_proxy_hops=1,
)
```

Set it to the real number of proxies. Too high a value lets a client choose its own address; too low makes every request look like it comes from the proxy.

## The Sessions page

The admin sidebar links to **Sessions** (`/management/sessions`). It lists active sessions with the browser and operating system, IP address, sign-in time and last activity, and marks the current one. Session ids are never shown.

- An admin sees and can end their own sessions.
- A superuser sees and can end every admin's sessions.

The same operations are available in code through `admin.session_manager`, crudauth's session manager:

```python
sessions = await admin.session_manager.list_for_user(user_id)
await admin.session_manager.revoke_by_handle(sessions[0]["id"], owner_id=user_id)
await admin.session_manager.revoke_all(user_id)
```

Logins, logouts, failed logins and lockouts are recorded in the event log when `track_events=True`.

## Removed and deprecated options

| Option | In 0.6 |
|--------|--------|
| `session_backend="memcached"`, `memcached_config` | Raises `ValueError` at startup naming the replacements, `redis` and `database`. `MemcachedConfig` can still be imported, so existing imports don't break. |
| `session_backend="hybrid"` | Deprecated: runs on `redis` and emits a `DeprecationWarning`. It will be removed in a later release. |
| `track_sessions_in_db=True` | Deprecated: emits a `DeprecationWarning`. With the `memory` backend it switches to `database`, so deployments that relied on it keep a shared store; with `redis` it changes nothing. Use `session_backend="database"` instead. |

Sessions are no longer stored in an `admin_session` table. A database upgraded from an earlier version keeps that table unused; you can drop it once every worker runs 0.6.

## Next steps

- [Basic Configuration](configuration.md) for the rest of the `CRUDAdmin` options
- [Managing Admin Users](admin-users.md) for accounts, superusers and the password confirmation step
- [Session Management API](../api/session.md) for the configuration classes
