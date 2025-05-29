from datetime import UTC, datetime
from typing import Optional, Type

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def create_admin_user(base: Type[DeclarativeBase]) -> Type[DeclarativeBase]:
    class AdminUser(base):  # type: ignore
        __tablename__ = "admin_user"

        id: Mapped[int] = mapped_column(
            "id", autoincrement=True, nullable=False, unique=True, primary_key=True
        )
        username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
        hashed_password: Mapped[str] = mapped_column(String)

        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=datetime.now(UTC),
        )
        updated_at: Mapped[Optional[datetime]] = mapped_column(
            DateTime(timezone=True),
            onupdate=datetime.now(UTC),
            default=None,
        )
        is_superuser: Mapped[bool] = mapped_column(Boolean, default=True)

    return AdminUser
