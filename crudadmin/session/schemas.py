from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..core.schemas.timestamp import TimestampSchema


class SessionData(BaseModel):
    """Common base data for any user session."""

    user_id: int
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    ip_address: str
    user_agent: str
    device_info: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(SessionData):
    """Schema for creating a new session."""

    pass


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    last_activity: Optional[datetime] = None
    is_active: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = None


class UserAgentInfo(BaseModel):
    """User agent information parsed from the User-Agent header."""

    browser: str
    browser_version: str
    os: str
    device: str
    is_mobile: bool
    is_tablet: bool
    is_pc: bool


class CSRFToken(BaseModel):
    """CSRF token data."""

    token: str
    user_id: int
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class AdminSessionBase(BaseModel):
    """Base schema for AdminSession."""

    user_id: int
    session_id: str
    ip_address: str
    user_agent: str
    device_info: dict[str, Any] = Field(default_factory=dict)
    session_metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class AdminSession(TimestampSchema, AdminSessionBase):
    """Full AdminSession schema with all fields."""

    id: int
    created_at: datetime
    last_activity: datetime


class AdminSessionRead(BaseModel):
    """Schema for reading AdminSession data."""

    id: int
    user_id: int
    session_id: str
    ip_address: str
    user_agent: str
    device_info: dict[str, Any]
    session_metadata: dict[str, Any]
    created_at: datetime
    last_activity: datetime
    is_active: bool


class AdminSessionCreate(AdminSessionBase):
    """Schema for creating AdminSession in database."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AdminSessionUpdate(BaseModel):
    """Schema for updating AdminSession."""

    last_activity: Optional[datetime] = None
    is_active: Optional[bool] = None
    session_metadata: Optional[dict[str, Any]] = None


class AdminSessionUpdateInternal(AdminSessionUpdate):
    """Internal schema for AdminSession updates."""

    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "SessionData",
    "SessionCreate",
    "SessionUpdate",
    "UserAgentInfo",
    "CSRFToken",
    "AdminSessionBase",
    "AdminSession",
    "AdminSessionRead",
    "AdminSessionCreate",
    "AdminSessionUpdate",
    "AdminSessionUpdateInternal",
]
