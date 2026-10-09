from typing import Any

from crudauth import AuthHooks, HookContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..event import EventType


def auth_event_hooks(
    integration: Any, session_maker: async_sessionmaker[AsyncSession]
) -> AuthHooks:
    """crudauth hooks that record logins, logouts, refused logins and lockouts.

    Each event is written to the event log in a session of its own, opened from
    ``session_maker``.
    """

    def details(context: HookContext, **extra: Any) -> dict[str, Any]:
        return {
            "auth_details": {
                "ip_address": context.ip_address or "unknown",
                "user_agent": context.user_agent or "unknown",
                **extra,
            },
            "session_details": {"session_id": context.session_handle or "unknown"},
        }

    async def record(
        event_type: Any,
        user_id: int | None,
        context: HookContext,
        success: bool,
        event_details: dict[str, Any],
    ) -> None:
        async with session_maker() as db:
            await integration.log_auth_event(
                db=db,
                event_type=event_type,
                user_id=user_id or 0,
                session_id=context.session_handle or "unknown",
                request=context.request,
                success=success,
                details=event_details,
            )

    async def on_after_login(user: dict, *, request: Any, context: HookContext) -> None:
        await record(
            EventType.LOGIN,
            user.get("id"),
            context,
            True,
            details(context, username=user.get("username")),
        )

    async def on_after_logout(
        user: dict, *, request: Any, context: HookContext
    ) -> None:
        await record(
            EventType.LOGOUT,
            user.get("id"),
            context,
            True,
            details(context, username=user.get("username")),
        )

    async def on_login_failed(
        identifier: str, *, user: dict | None, reason: str, context: HookContext
    ) -> None:
        event_details = details(context, username=identifier, reason=reason)
        event_details["username"] = identifier
        await record(
            EventType.FAILED_LOGIN,
            (user or {}).get("id"),
            context,
            False,
            event_details,
        )

    async def on_lockout(
        identifier: str, *, retry_after: int, context: HookContext
    ) -> None:
        event_details = details(
            context, username=identifier, reason="lockout", retry_after=retry_after
        )
        event_details["username"] = identifier
        await record(EventType.FAILED_LOGIN, None, context, False, event_details)

    return AuthHooks(
        on_after_login=on_after_login,
        on_after_logout=on_after_logout,
        on_login_failed=on_login_failed,
        on_lockout=on_lockout,
    )
