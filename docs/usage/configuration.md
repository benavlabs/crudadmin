# Basic Configuration

This guide covers the settings you need to get a CRUDAdmin instance running, and the ones to revisit before production.

## Prerequisites

- A working FastAPI application
- SQLAlchemy models defined (see [Quick Start](../quick-start.md))
- CRUDAdmin installed (`uv add crudadmin`)

---

## Creating Your CRUDAdmin Instance

### Minimal Setup

Two parameters are required, the session dependency and the secret key:

```python
from crudadmin import CRUDAdmin

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="your-secret-key-here",
)
```

### Common Configuration

```python
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from crudadmin import CRUDAdmin

engine = create_async_engine("sqlite+aiosqlite:///./app.db")


async def get_session():
    async with AsyncSession(engine) as session:
        yield session


admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    mount_path="/admin",
    theme="dark-theme",
    admin_db_path=None,
    initial_admin={
        "username": "admin",
        "password": os.environ["ADMIN_INITIAL_PASSWORD"],
    },
)
```

Every parameter except `session` and `SECRET_KEY` has a default. `mount_path` defaults to `/admin`, `theme` to `dark-theme`, and with `admin_db_path=None` the admin database is created at `./crudadmin_data/admin.db`.

!!! warning "Security Best Practices"
    **Database Security:** When using SQLite, add `*.db`, `*.sqlite` and `crudadmin_data/` to your `.gitignore`.

    **Production Security:**

    - Use a strong, randomly generated `SECRET_KEY` from the environment, and keep it stable.
    - With more than one worker, use the `redis` or `database` session backend (see [Session Backends](session-backends.md)).
    - Behind a reverse proxy, set `trusted_proxy_hops`.
    - Restrict access with `allowed_ips` / `allowed_networks`, and serve the admin over HTTPS.

---

## Parameter Details

### `session` (Callable, required)

An async dependency that yields a SQLAlchemy `AsyncSession` for your application database:

```python
async def get_session():
    async with AsyncSession(engine) as session:
        yield session


admin = CRUDAdmin(session=get_session, SECRET_KEY=secret_key)
```

### `SECRET_KEY` (str, required)

Keys the stored session and CSRF identifiers, so a copy of the session store can't be turned into working sessions. CRUDAdmin refuses to start without it. Changing it signs every admin out, so keep it stable and load it from the environment:

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
)
```

Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### `mount_path` (str, default: "/admin")

The URL path the admin is served under. If you mount it somewhere else, pass the same path here, so links and the session cookie's path match:

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    mount_path="/dashboard",
)

app.mount("/dashboard", admin.app)
```

### `theme` (str, default: "dark-theme")

`"dark-theme"` or `"light-theme"`.

### `admin_db_path` / `admin_db_url`

Where the admin database lives: admin users, the event log and, with `session_backend="database"`, sessions and lockout counters. By default it's SQLite at `./crudadmin_data/admin.db`. Use `admin_db_path` for another SQLite file, or `admin_db_url` for any async SQLAlchemy URL:

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    admin_db_url="postgresql+asyncpg://user:pass@localhost/admin",
)
```

### `initial_admin` (dict, default: None)

Creates a superuser during `admin.initialize()` if no admin exists yet. See [Managing Admin Users](admin-users.md).

### Sessions

| Parameter | Default | Meaning |
|---|---|---|
| `session_backend` | `"memory"` | `"memory"`, `"redis"` or `"database"`; see [Session Backends](session-backends.md) |
| `redis_config` | `None` | `RedisConfig` or dict for the `redis` backend |
| `session_timeout_minutes` | `30` | Idle time after which a session ends |
| `max_sessions_per_user` | `5` | Sessions an admin may hold at once; the oldest ends past this |
| `cleanup_interval_minutes` | `15` | How often idle sessions are swept |
| `secure_cookies` | `True` | Send session cookies over HTTPS only |

### Security

| Parameter | Default | Meaning |
|---|---|---|
| `allowed_ips` / `allowed_networks` | `None` | Only these addresses reach the admin, login page included |
| `enforce_https` / `https_port` | `False` / `443` | Redirect HTTP requests to HTTPS |
| `trusted_proxy_hops` | `0` | Reverse proxies in front of the app; with `0`, `X-Forwarded-For` is ignored |
| `lockout` | crudadmin's | A `crudauth.ratelimit.LockoutConfig` for the login lockout |

Login lockout defaults to 5 failures, a first lock of one minute, and at most five minutes. A successful login clears the counters. Anyone who knows an admin's username can trigger a lockout, which is why the cap is short and why `allowed_ips` is worth setting.

Requests that change data need the session's CSRF token in an `X-CSRF-Token` header. The interface's bundled `admin.js` sends it for forms, htmx requests and `fetch` calls, and logging out is a POST.

### `track_events` (bool, default: False)

Records logins, failed logins, lockouts and every create, update and delete in the event log, visible to superusers.

---

## FastAPI Integration

Call `admin.initialize()` on startup and `admin.shutdown()` on shutdown:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await admin.initialize()
    yield
    await admin.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/admin", admin.app)
```

`initialize()` creates the admin tables, adds columns introduced by newer versions to existing ones, opens the session store, and creates the initial admin. `shutdown()` closes the session store and any Redis client CRUDAdmin opened.

---

## Development vs Production

### Development

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY="dev-key-change-in-production",
    secure_cookies=False,
    initial_admin={
        "username": "admin",
        "password": "admin123",
    },
)
```

`secure_cookies=False` lets the session cookie work over plain HTTP. Chrome and Firefox already accept secure cookies on `http://localhost`; other hosts, and Safari, need this in development.

### Production

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    session_backend="database",
    trusted_proxy_hops=1,
    allowed_networks=["10.0.0.0/8"],
    enforce_https=True,
    track_events=True,
)
```

With the memory backend CRUDAdmin logs a warning at startup, because sessions and lockout counters aren't shared between workers.

---

## Next Steps

1. **[Add Models](adding-models.md)** to create your admin interface
2. **[Set up Admin Users](admin-users.md)** for access control
3. **[Learn the Interface](interface.md)** to manage your data
