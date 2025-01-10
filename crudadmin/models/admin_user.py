from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column


def create_admin_user(base):
    class AdminUser(base):
        __tablename__ = "admin_user"

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True
        )
        name: Mapped[str] = mapped_column(String(30))
        username: Mapped[str] = mapped_column(
            String(20), unique=True, index=True
        )
        email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
        hashed_password: Mapped[str] = mapped_column(String)

        created_at: Mapped[datetime] = mapped_column(
            DateTime, default=datetime.now(timezone.utc)
        )
        updated_at: Mapped[Optional[datetime]] = mapped_column(default=None)
        is_superuser: Mapped[bool] = mapped_column(default=True)

    return AdminUser