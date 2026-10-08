# Managing Admin Users

This guide covers creating and managing the accounts that log in to the admin interface: who may do what, how passwords and sessions behave, and how accounts are deactivated.

## Prerequisites

- A configured CRUDAdmin instance (see [Basic Configuration](configuration.md))
- `admin.initialize()` called in your app's lifespan, which creates the admin tables

---

## Roles

An admin is either a **superuser** or a regular admin.

| | Regular admin | Superuser |
|---|---|---|
| Your models (per `allowed_actions`) | ✅ | ✅ |
| Dashboard and health checks | ✅ | ✅ |
| Own sessions on the Sessions page | ✅ | ✅ |
| Every admin's sessions | ❌ | ✅ |
| Admin users (`/admin/AdminUser`) | ❌ | ✅ |
| Event log | ❌ | ✅ |

New admins are **not** superusers unless you make them one. The admin created from `initial_admin` is always a superuser.

Admin users can be viewed, created and updated, but not deleted; deactivate them instead (see below).

---

## Creating Admin Users

### The initial admin

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=os.environ["ADMIN_SECRET_KEY"],
    initial_admin={
        "username": "admin",
        "password": os.environ["ADMIN_INITIAL_PASSWORD"],
    },
)
```

During `admin.initialize()`, this account is created as a superuser if no admin exists yet. If several workers start at once, only one creates it. Changing `initial_admin` later has no effect once an admin exists.

### In the interface

1. Go to `/admin/AdminUser` (superusers only).
2. Click **Add AdminUser**.
3. Confirm your own password. Creating or editing an admin account asks for it again; the confirmation lasts five minutes, after which the next change asks again. Three wrong passwords lock the confirmation for 15 minutes.
4. Fill in the username and password, and choose whether the new admin is a superuser.

### In code

```python
from crudauth import get_password_hash_async

from crudadmin.admin_user.schemas import AdminUserCreateInternal


async def create_admin_user(username: str, password: str, superuser: bool = False):
    new_admin = AdminUserCreateInternal(
        username=username,
        hashed_password=await get_password_hash_async(password),
        is_superuser=superuser,
    )
    async with admin.db_config.admin_session_maker() as db:
        await admin.db_config.crud_users.create(db, object=new_admin)
        await db.commit()
```

Validate the password with `AdminUserCreate(username=..., password=...)` first if it comes from user input.

---

## Validation Rules

**Usernames**: 2 to 20 characters, lowercase letters and digits only (`^[a-z0-9]+$`). `admin` and `user123` are valid; `Admin`, `user-name` and `ab` are not.

**Passwords**: 8 to 128 characters. There are no character-class rules: a long passphrase is stronger than a short "complex" password.

Passwords are hashed by [crudauth](https://github.com/benavlabs/crudauth): bcrypt over a SHA-256 pre-hash, so there's no 72-byte limit. Hashes written by crudadmin 0.5 and earlier keep working and are upgraded on the admin's next login.

---

## Editing Admin Users

In `/admin/AdminUser`, open an admin to change their username, password, superuser status or active status. Leave the password empty to keep it.

Changes take effect at once:

- **New password**: every other session of that admin ends. If you change your own password, your current session stays.
- **Deactivated** (`is_active` unchecked): the admin can't log in, and their open sessions stop working on their next request.
- **No longer a superuser**: their sessions end, so they log in again with the reduced access.
- **The last active superuser** can't be demoted or deactivated; the form refuses with "At least one active superuser must remain."

### In code

```python
from crudauth import get_password_hash_async


async def reset_password(user_id: int, new_password: str):
    async with admin.db_config.admin_session_maker() as db:
        await admin.db_config.crud_users.update(
            db,
            object={"hashed_password": await get_password_hash_async(new_password)},
            id=user_id,
        )
        await db.commit()
    await admin.session_manager.revoke_all(user_id)


async def deactivate(user_id: int):
    async with admin.db_config.admin_session_maker() as db:
        await admin.db_config.crud_users.update(db, object={"is_active": False}, id=user_id)
        await db.commit()
    await admin.session_manager.revoke_all(user_id)
```

`revoke_all` ends every session the admin has. A deactivated admin is refused on the next request anyway; revoking also removes their sessions from the Sessions page.

---

## Sessions

Each login creates a session, stored in the configured [session backend](session-backends.md):

```python
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    max_sessions_per_user=3,
    session_timeout_minutes=30,
    cleanup_interval_minutes=15,
)
```

- A session ends after `session_timeout_minutes` without activity. The cookie lasts until the browser closes.
- Past `max_sessions_per_user`, the oldest session is ended.
- Logging in again from the same browser ends the session it had.

The **Sessions** page (`/admin/management/sessions`) lists sessions with their browser, IP address, sign-in time and last activity, and a **Sign out** button for each. Admins see their own sessions; superusers see everyone's. Session ids are never shown.

To end sessions from code, use the session manager:

```python
sessions = await admin.session_manager.list_for_user(user_id)
await admin.session_manager.revoke_by_handle(sessions[0]["id"], owner_id=user_id)
await admin.session_manager.revoke_all(user_id)
```

---

## Login Protection

Logins are protected by crudauth's lockout. crudadmin's defaults:

- 5 failed attempts lock the username and the IP address;
- the first lock lasts one minute, doubling on repeated lockouts up to five minutes;
- a successful login clears the failure counters (`on_login_success="clear_all"`).

Anyone who knows an admin's username can lock it out by failing on purpose, which is why the cap is short. Keep strangers away from the login page with `allowed_ips` or `allowed_networks`. To tune the lockout:

```python
from crudauth.ratelimit import LockoutConfig

admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=key,
    lockout=LockoutConfig(max_attempts=10, lockout_max_seconds=600),
    allowed_networks=["10.0.0.0/8"],
)
```

Behind a reverse proxy, set `trusted_proxy_hops` to the number of proxies so lockouts count the real client IP; with the default `0`, `X-Forwarded-For` is ignored.

Logged-in requests that change data (POST, PUT, PATCH, DELETE), including logout, need the session's CSRF token in an `X-CSRF-Token` header. The bundled `admin.js` sends it for the interface's forms, htmx requests and `fetch` calls.

---

## Upgrading from 0.5

`admin.initialize()` adds the `is_active` and `token_version` columns to an existing `admin_user` table, so no manual step is needed. If you manage the admin database with Alembic, add them in a migration instead:

```python
import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column(
        "admin_user",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "admin_user",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
```

Existing admins keep their `is_superuser` value. The old `admin_session` table is no longer used and can be dropped.

---

## Next Steps

1. **[Learn the Interface](interface.md)** to navigate and use the admin panel
2. **[Add Models](adding-models.md)** to manage your application data
3. **[Session Backends](session-backends.md)** to choose where sessions are kept in production
