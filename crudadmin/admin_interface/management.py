import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import DatabaseConfig
from ..event import EventStatus, EventType
from ..event.service import redact_secrets
from .admin_site import AdminSite
from .auth import AdminAuthentication
from .typing import RouteResponse

UTC = timezone.utc

logger = logging.getLogger("crudadmin")

EndpointFunction = Callable[[Request, AsyncSession], Awaitable[RouteResponse]]


def _day(value: Optional[str]) -> Optional[datetime]:
    """The start of a ``YYYY-MM-DD`` day in UTC, or None when it isn't one."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


class ManagementPages:
    """The health check and event log pages.

    ``CRUDAdmin.setup()`` builds one once the admin site exists and adds its
    endpoints to the management routes; the event log routes need a superuser.

    Args:
        admin_site: Supplies the page context and the URL prefix.
        templates: The admin's Jinja2 templates.
        database_config: The admin database, where admins and events are kept.
        admin_authentication: Its lockout limiter is pinged by the health check.
        session_backend: Named on the health page.
    """

    def __init__(
        self,
        admin_site: AdminSite,
        templates: Jinja2Templates,
        database_config: DatabaseConfig,
        admin_authentication: AdminAuthentication,
        session_backend: str,
    ) -> None:
        self.admin_site = admin_site
        self.templates = templates
        self.db_config = database_config
        self.admin_authentication = admin_authentication
        self.session_backend = session_backend

    def event_log_page(
        self,
    ) -> Callable[[Request, AsyncSession], Awaitable[RouteResponse]]:
        """
        Create endpoint for event log main page.

        Returns:
            FastAPI route handler that renders event log template
            with filtering options
        """

        admin_db_db_dependency = cast(
            Callable[..., AsyncSession], self.db_config.get_admin_db
        )

        async def event_log_page_inner(
            request: Request,
            admin_db: AsyncSession = Depends(admin_db_db_dependency),
        ) -> RouteResponse:
            users = await self.db_config.crud_users.get_multi(db=admin_db)

            context = self.admin_site.get_base_context(request)
            context.update(
                {
                    "include_sidebar_and_header": True,
                    "event_types": [e.value for e in EventType],
                    "statuses": [s.value for s in EventStatus],
                    "users": users["data"],
                    "url_prefix": self.admin_site.get_url_prefix(),
                }
            )

            return self.templates.TemplateResponse(
                name="admin/management/events.html", request=request, context=context
            )

        return event_log_page_inner

    def event_log_content(self) -> EndpointFunction:
        """
        Create endpoint for event log data with filtering and pagination.

        Returns:
            FastAPI route handler that provides filtered event data
            with user and audit details

        Notes:
            - Supports filtering by:
            - Event type
            - Status
            - Username
            - Date range
            - Returns enriched events with:
            - Username
            - Resource details
            - Audit trail data
            - Includes pagination metadata

        Examples:
            Filter events:
            GET /management/events/content?event_type=create&status=success

            Filter by date:
            GET /management/events/content?start_date=2024-01-01&end_date=2024-01-31
        """

        admin_db_db_dependency = cast(
            Callable[..., AsyncSession], self.db_config.get_admin_db
        )

        async def event_log_content_inner(
            request: Request,
            admin_db: AsyncSession = Depends(admin_db_db_dependency),
            page: int = 1,
            limit: int = 10,
        ) -> RouteResponse:
            try:
                if not self.db_config.AdminEventLog:
                    raise ValueError("AdminEventLog is not configured")

                crud_events: FastCRUD = FastCRUD(self.db_config.AdminEventLog)

                event_type = request.query_params.get("event_type")
                status = request.query_params.get("status")
                username = request.query_params.get("username")
                start_date = request.query_params.get("start_date")
                end_date = request.query_params.get("end_date")

                filter_criteria: Dict[str, Any] = {}
                if event_type in {kind.value for kind in EventType}:
                    filter_criteria["event_type"] = event_type
                if status in {state.value for state in EventStatus}:
                    filter_criteria["status"] = status

                if username:
                    user = await self.db_config.crud_users.get(
                        db=admin_db, username=username
                    )
                    if user and isinstance(user, dict):
                        filter_criteria["user_id"] = user.get("id")

                first_day = _day(start_date)
                if first_day is not None:
                    filter_criteria["timestamp__gte"] = first_day
                last_day = _day(end_date)
                if last_day is not None:
                    filter_criteria["timestamp__lt"] = last_day + timedelta(days=1)

                events = await crud_events.get_multi(
                    db=admin_db,
                    offset=(page - 1) * limit,
                    limit=limit,
                    sort_columns=["timestamp"],
                    sort_orders=["desc"],
                    **filter_criteria,
                )

                enriched_events = []
                if isinstance(events["data"], list):
                    for event in events["data"]:
                        if isinstance(event, dict):
                            event_data = dict(event)
                            user = await self.db_config.crud_users.get(
                                db=admin_db, id=event.get("user_id")
                            )
                            if isinstance(user, dict):
                                event_data["username"] = user.get("username", "Unknown")
                            event_data["details"] = redact_secrets(
                                event.get("details") or {}
                            )

                            enriched_events.append(event_data)

                total_items = events.get("total_count", 0)
                assert isinstance(total_items, int), (
                    f"'total_count' should be int, got {type(total_items)}"
                )

                total_pages = max(1, (total_items + limit - 1) // limit)

                return self.templates.TemplateResponse(
                    name="admin/management/events_content.html",
                    request=request,
                    context={
                        "events": enriched_events,
                        "page": page,
                        "total_pages": total_pages,
                        "url_prefix": self.admin_site.get_url_prefix(),
                        "start_date": start_date,
                        "end_date": end_date,
                        "selected_type": event_type,
                        "selected_status": status,
                        "selected_user": username,
                    },
                )

            except SQLAlchemyError:
                logger.exception("Could not read the event log")
                return self.templates.TemplateResponse(
                    name="admin/management/events_content.html",
                    request=request,
                    context={
                        "events": [],
                        "page": 1,
                        "total_pages": 1,
                        "url_prefix": self.admin_site.get_url_prefix(),
                    },
                )

        return event_log_content_inner

    def health_check_page(
        self,
    ) -> Callable[[Request], Awaitable[RouteResponse]]:
        """
        Create endpoint for system health check page.

        Returns:
            FastAPI route handler that renders health check template
        """

        async def health_check_page_inner(request: Request) -> RouteResponse:
            context = self.admin_site.get_base_context(request)
            context.update({"include_sidebar_and_header": True})

            return self.templates.TemplateResponse(
                name="admin/management/health.html", request=request, context=context
            )

        return health_check_page_inner

    def health_check_content(
        self,
    ) -> Callable[[Request, AsyncSession], Awaitable[RouteResponse]]:
        """
        Create endpoint for health check data.

        Returns:
            FastAPI route handler that checks:
            - Database connectivity
            - Session management
            - Token service
        """

        db_dependency = cast(Callable[..., AsyncSession], self.db_config.session)

        async def health_check_content_inner(
            request: Request, db: AsyncSession = Depends(db_dependency)
        ) -> RouteResponse:
            health_checks = {}

            start_time = time.time()
            try:
                await db.execute(text("SELECT 1"))
                latency = (time.time() - start_time) * 1000
                health_checks["database"] = {
                    "status": "healthy",
                    "message": "Connected successfully",
                    "latency": latency,
                }
            except Exception:
                logger.exception("Database health check failed")
                health_checks["database"] = {
                    "status": "unhealthy",
                    "message": "The database is unreachable",
                }

            try:
                limiter = self.admin_authentication.auth.runtime.rate_limiter
                if limiter is not None:
                    await limiter.ping()
                health_checks["session_management"] = {
                    "status": "healthy",
                    "message": f"Session store: {self.session_backend}",
                }
            except Exception:
                logger.exception("Session store health check failed")
                health_checks["session_management"] = {
                    "status": "unhealthy",
                    "message": f"Session store ({self.session_backend}) is unreachable",
                }

            context = {
                "health_checks": health_checks,
                "last_checked": datetime.now(UTC),
            }

            return self.templates.TemplateResponse(
                name="admin/management/health_content.html",
                request=request,
                context=context,
            )

        return health_check_content_inner
