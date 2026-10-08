from datetime import datetime, timezone
from typing import Optional, Type

from sqlalchemy import Boolean, DateTime, Integer, String, false, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UTC = timezone.utc


def create_admin_user(base: Type[DeclarativeBase]) -> Type[DeclarativeBase]:
    class AdminUser(base):  # type: ignore
        """An admin account, read by crudauth.

        An inactive admin can't log in and loses their sessions at once; raising
        ``token_version`` ends every session the admin has.
        """

        __tablename__ = "admin_user"

        id: Mapped[int] = mapped_column(
            "id", autoincrement=True, nullable=False, unique=True, primary_key=True
        )
        username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
        hashed_password: Mapped[str] = mapped_column(String)

        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
        )
        updated_at: Mapped[Optional[datetime]] = mapped_column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(UTC),
            default=None,
        )
        is_superuser: Mapped[bool] = mapped_column(
            Boolean, default=False, server_default=false()
        )
        is_active: Mapped[bool] = mapped_column(
            Boolean, default=True, server_default=true()
        )
        token_version: Mapped[int] = mapped_column(
            Integer, default=0, server_default="0"
        )

    return AdminUser
