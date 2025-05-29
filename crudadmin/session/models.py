from datetime import UTC, datetime
from typing import Any, Dict, Type

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def create_admin_session_model(base: Type[DeclarativeBase]) -> Type[DeclarativeBase]:
    class AdminSession(base):  # type: ignore
        __tablename__ = "admin_session"

        id: Mapped[int] = mapped_column(
            "id", autoincrement=True, nullable=False, unique=True, primary_key=True
        )
        user_id: Mapped[int] = mapped_column(index=True)
        session_id: Mapped[str] = mapped_column(
            String(36), unique=True, index=True, nullable=False
        )
        ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
        user_agent: Mapped[str] = mapped_column(String(512), nullable=False)

        device_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
        )
        last_activity: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
        )
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

        session_metadata: Mapped[Dict[str, Any]] = mapped_column(
            JSON, default=dict, nullable=False
        )

        def __repr__(self) -> str:
            return f"<AdminSession(id={self.id}, user_id={self.user_id}, session_id={self.session_id})>"

    return AdminSession
