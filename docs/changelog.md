# Changelog

Notable changes to CRUDAdmin, newest first. CRUDAdmin is pre-1.0, so minor versions may include
breaking changes; they are called out under **Breaking changes**, and **Upgrading** says what to do.

___

## 0.6.0 - 2026-10-08

Authentication moves onto [crudauth](https://github.com/benavlabs/crudauth). Login, sessions, CSRF
and login lockout are crudauth's; CRUDAdmin renders the pages around them. This closes the
remaining security gaps from the 0.5 review (CSRF and login rate limiting were documented but never
enforced, and `X-Forwarded-For` was trusted unconditionally), adds superuser-only account
management, and fixes a set of audit-log and form bugs. Deploying it signs every admin out once.

#### Added
- **CSRF protection.** Every POST, PUT, PATCH and DELETE needs the `X-CSRF-Token` header. The new
  `static/admin.js` sends it with htmx requests, `fetch` calls and plain `<form method="post">`
  submissions.
- **Login lockout.** Five failed attempts lock the username and the IP: one minute at first,
  doubling to at most five minutes, cleared by a successful login. Tune it with
  `CRUDAdmin(lockout=LockoutConfig(...))`.
- **`trusted_proxy_hops`.** `X-Forwarded-For` is ignored unless you say how many trusted proxies
  sit in front of the app.
- **Sessions page** (`/management/sessions`): device, IP and times for each session, never its
  id. Admins see and end their own sessions; superusers see and end everyone's.
- **Password confirmation for account changes.** Creating or editing an admin asks the superuser
  to confirm their password; the confirmation lasts five minutes.
- **`is_active` and `token_version` on `AdminUser`.** A deactivated admin can't log in and loses
  their sessions at once; a password change ends the admin's other sessions.
- **`admin.shutdown()`** closes the session stores and the Redis client CRUDAdmin opened.
- **`admin.session_manager`**, crudauth's session manager, for listing and revoking sessions in
  your own code.
- **Session backends:** `memory`, `redis` and `database`. With `database`, login lockout counters
  are kept in the admin database too, so they are shared across workers.

#### Changed
- **Admin users and the event log are superuser-only.** New admins are not superusers unless
  created as one; the initial admin is.
- **Logout is a POST** with the CSRF header; `GET /logout` no longer exists.
- **The last active superuser can't be demoted or deactivated.**
- **Password hashes from 0.5 keep working** and are rehashed in crudauth's format at the next
  login.
- **The login page** answers bad credentials with 401, a lockout with 429 and a cross-site login
  with 403, and shows only its own messages from the `error` query parameter.
- **A form submitted through `admin.js` loads the next page once.** A redirect answering it comes
  back as a 204 with `X-CRUDAdmin-Location`.
- **`track_events=True` with your own `db_config`** gets the event and audit tables automatically.
- **One mypy configuration** (`[tool.mypy]` in `pyproject.toml`, with the pydantic plugin) checks
  the package and the tests; CI and the pre-commit hook both run `mypy`.

#### Fixed
- **Editing an admin user always failed** (the update form added `updated_at`, which
  `AdminUserUpdate` rejects).
- **Audit log:**
  - an action that failed is recorded as `failure`, with no audit rows;
  - a delete writes one audit row per deleted record, keyed by the model's primary key, including
    keys not named `id`;
  - creates are keyed by the real primary key too;
  - an event and its audit rows are written in one transaction and rolled back together if any
    write fails.
- **Forms and lists:**
  - `Optional[bool]` (and other `Optional[...]`) fields render as their real input type, so
    `Optional[bool]` is a checkbox;
  - an empty input clears a nullable column on update;
  - the password transformer keeps `False` and `0`;
  - bulk delete works with UUID primary keys, and a malformed id gets a 422;
  - pagination keeps the active search;
  - a list query that fails is an error page, not "0 items".
- **Upgrading several workers at once** no longer fails: the new `admin_user` columns are added in
  their own transactions, and a worker that loses the race carries on.

#### Security
- Fixes the reports in GHSA-fv5q-2mg9-c62x (`X-Forwarded-For` spoofing),
  GHSA-4cwg-f726-9hfv and GHSA-7c4p-r94r-6r3j (no login rate limiting).
- CSRF tokens are now checked on every state-changing request.
- Session ids and CSRF tokens are stored as HMACs keyed with `SECRET_KEY`, never raw.

#### Removed
- The `crudadmin.session` session layer (`SessionManager`, `get_session_storage`, the memory,
  Redis, Memcached, database and hybrid backends, and the `AdminSession` model and view).
  `crudadmin.session` keeps `RedisConfig` and `MemcachedConfig`.
- `crudadmin.core.auth`, `crudadmin.core.rate_limiter`, `AdminUserService` and
  `log_auth_action`. Logins and logouts are recorded through crudauth hooks.
- The `memcached` extra.

#### Deprecated
- `session_backend="hybrid"` now means `"redis"` and warns; it will be removed.
- `track_sessions_in_db` warns; with the memory backend it switches to `"database"`. It will be
  removed.

#### Breaking changes
- **Deploying 0.6 signs every admin out once.** Sessions are now crudauth's and stored under new
  keys.
- **`SECRET_KEY` is required and used.** It keys stored session ids and CSRF tokens; changing it
  signs everyone out.
- **`session_backend="memcached"` and `memcached_config=` fail at startup.** Use `"redis"` or
  `"database"`.
- **Logout is a POST** that needs the `X-CSRF-Token` header.
- **New admins aren't superusers by default.**
- **The removed modules above** are gone; use crudauth or `admin.session_manager`.

#### Upgrading
1. Update: `pip install -U crudadmin`. This adds `crudauth[useragent]>=0.8.2,<0.9` (and PyJWT).
2. Call `await admin.shutdown()` after `yield` in your lifespan.
3. Replace `session_backend="memcached"` with `"redis"` or `"database"`.
4. If you run behind a reverse proxy, set `trusted_proxy_hops`.
5. Custom templates or links that log out must POST to `/logout` with the `X-CSRF-Token` header;
   pages extending `base/base.html` get it from `admin.js`.
6. `initialize()` adds `is_active` and `token_version` to an existing `admin_user` table. If you
   manage the admin schema with Alembic instead:

    ```python
    op.add_column(
        "admin_user",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "admin_user",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    ```

7. The `admin_session` table is no longer used and can be dropped: `DROP TABLE admin_session;`

___

## 0.5.2 - 2026-10-07

A security patch release.

#### Security
- Removed the generic `/{Model}/crud` REST routes, which ignored `allowed_actions` and returned
  every column, password hashes included.
- Fixed cross-site scripting in the list page (`sort_order` evaluated by htmx, and string primary
  keys written into an inline handler).
- The IP allowlist and HTTPS redirect apply on every mount path, and the redirect uses the
  configured HTTPS port.

#### Fixed
- Session ids kept out of logs, the event log and the admin lists; password hashes redacted from
  audit snapshots.
- Admin passwords must be 8–128 characters; `PasswordTransformer` requires a hash function.
- The database session backend no longer shares one `AsyncSession` across requests.
- The session cookie no longer expires after a fixed 30 minutes; audit metadata is stored;
  `AdminUser` timestamps are set per row; page size is bounded.
