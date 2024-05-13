from datetime import datetime

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column


def create_admin_token_blacklist(base):
    class AdminTokenBlacklist(base):
        __tablename__ = "admin_token_blacklist"

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True,
            init=False,
        )
        token: Mapped[str] = mapped_column(String, unique=True, index=True)
        expires_at: Mapped[datetime] = mapped_column(DateTime)

    return AdminTokenBlacklist
