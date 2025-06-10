from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy import JSON, DateTime, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .schemas import EventStatus, EventType

UTC = timezone.utc


def create_admin_event_log(base: type[DeclarativeBase]) -> type[DeclarativeBase]:
    tablename = "admin_event_log"

    if hasattr(base, "registry") and hasattr(base.registry, "_class_registry"):
        existing_class = base.registry._class_registry.get("AdminEventLog")
        if existing_class is not None and isinstance(existing_class, type):
            if issubclass(existing_class, base):
                return cast(type[DeclarativeBase], existing_class)

    class AdminEventLog(base):  # type: ignore
        __tablename__ = tablename
        __table_args__ = {"extend_existing": True}

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True,
        )
        timestamp: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
        )
        event_type: Mapped[EventType] = mapped_column(
            SQLEnum(EventType), nullable=False
        )
        status: Mapped[EventStatus] = mapped_column(
            SQLEnum(EventStatus), nullable=False
        )
        user_id: Mapped[int] = mapped_column(index=True)
        session_id: Mapped[str] = mapped_column(String(36), index=True)
        ip_address: Mapped[str] = mapped_column(String(45))
        user_agent: Mapped[str] = mapped_column(String(512))
        resource_type: Mapped[Optional[str]] = mapped_column(String(128))
        resource_id: Mapped[Optional[str]] = mapped_column(String(128))
        details: Mapped[dict[str, Any]] = mapped_column(
            JSON, default=dict, nullable=False
        )

        def __repr__(self):
            return f"<AdminEventLog(id={self.id}, event_type={self.event_type}, user_id={self.user_id})>"

    return AdminEventLog


def create_admin_audit_log(base: type[DeclarativeBase]) -> type[DeclarativeBase]:
    tablename = "admin_audit_log"

    if hasattr(base, "registry") and hasattr(base.registry, "_class_registry"):
        existing_class = base.registry._class_registry.get("AdminAuditLog")
        if existing_class is not None and isinstance(existing_class, type):
            if issubclass(existing_class, base):
                return cast(type[DeclarativeBase], existing_class)

    class AdminAuditLog(base):  # type: ignore
        __tablename__ = tablename
        __table_args__ = {"extend_existing": True}

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True,
        )
        event_id: Mapped[int] = mapped_column(index=True)
        timestamp: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
        )
        resource_type: Mapped[str] = mapped_column(String(128))
        resource_id: Mapped[str] = mapped_column(String(128))
        action: Mapped[str] = mapped_column(String(64))
        previous_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
            JSON, nullable=True
        )
        new_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
        changes: Mapped[dict[str, Any]] = mapped_column(
            JSON, default=dict, nullable=False
        )
        audit_metadata: Mapped[dict[str, Any]] = mapped_column(
            JSON, default=dict, nullable=False
        )

        def __repr__(self):
            return f"<AdminAuditLog(id={self.id}, resource_type={self.resource_type}, resource_id={self.resource_id})>"

    return AdminAuditLog
