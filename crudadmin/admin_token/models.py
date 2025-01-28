from typing import Type
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def create_admin_token_blacklist(base: Type[DeclarativeBase]) -> Type[DeclarativeBase]:
    """
    Dynamically create the AdminTokenBlacklist model using the given SQLAlchemy base.

    Args:
        base: A SQLAlchemy declarative base class (e.g., `AdminBase` or another base).

    Returns:
        The newly created AdminTokenBlacklist model class, which inherits from `base`.
    """

    class AdminTokenBlacklist(base):
        __tablename__ = "admin_token_blacklist"

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True,
        )
        token: Mapped[str] = mapped_column(String, unique=True, index=True)
        expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

        def __repr__(self) -> str:
            return f"<AdminTokenBlacklist(id={self.id}, token={self.token})>"

    return AdminTokenBlacklist
