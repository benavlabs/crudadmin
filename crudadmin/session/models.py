# In crudadmin/session/models.py

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

def create_admin_session_model(base):
    class AdminSession(base):
        __tablename__ = "admin_session"

        id: Mapped[int] = mapped_column(
            "id",
            autoincrement=True,
            nullable=False,
            unique=True,
            primary_key=True
        )
        user_id: Mapped[int] = mapped_column(index=True)
        session_id: Mapped[str] = mapped_column(
            String(36), 
            unique=True, 
            index=True,
            nullable=False
        )
        ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
        user_agent: Mapped[str] = mapped_column(String(512), nullable=False)
        device_info: Mapped[dict] = mapped_column(JSON, nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            nullable=False
        )
        last_activity: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            nullable=False
        )
        is_active: Mapped[bool] = mapped_column(
            Boolean,
            default=True,
            nullable=False
        )
        session_metadata: Mapped[dict] = mapped_column(
            JSON,
            default=dict,
            nullable=False
        )

        def __repr__(self):
            return f"<AdminSession(id={self.id}, user_id={self.user_id}, session_id={self.session_id})>"

    return AdminSession
