from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from ..core.schemas.timestamp import TimestampSchema


class DeviceType(str, Enum):
    """Device type enumeration"""

    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"
    UNKNOWN = "unknown"


class BaseSession(BaseModel):
    """Common base fields for all session types."""

    user_id: int = Field(
        ..., description="The ID of the user associated with the session."
    )

    session_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique session identifier"
    )
    ip_address: str = Field(..., description="Client IP address")
    user_agent: str = Field(..., description="Client user agent string")
    device_info: dict[str, Any] = Field(
        default_factory=dict, description="Additional device information"
    )
    is_active: bool = Field(default=True, description="Whether session is active")

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, ip: str) -> str:
        """Validate IP address format."""
        import ipaddress

        try:
            ipaddress.ip_address(ip)
        except ValueError as err:
            raise ValueError("Invalid IP Address format") from err
        return ip


class SessionData(BaseSession):
    """Common session data for any user session."""

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional session metadata"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Session creation timestamp",
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last activity timestamp"
    )


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

    browser: str = Field(..., description="Browser name")
    browser_version: str = Field(..., description="Browser version")
    os: str = Field(..., description="Operating System")
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


class AdminSession(TimestampSchema, BaseSession):
    """Full AdminSession schema with all fields."""

    id: int
    session_metadata: dict[str, Any] = Field(
        default_factory=dict, description="admin specific session metadata"
    )
    # remove redundant timestamp fields - let TimestampSchema handle them


class AdminSessionRead(BaseSession):
    """Schema for reading AdminSession data."""

    id: int
    session_metadata: dict[str, Any]
    created_at: datetime
    last_activity: datetime
    is_active: bool


class AdminSessionCreate(BaseSession):
    """Schema for creating AdminSession in database."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_metadata: dict[str, Any] = Field(default_factory=dict)


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
    "AdminSession",
    "AdminSessionRead",
    "AdminSessionCreate",
    "AdminSessionUpdate",
    "AdminSessionUpdateInternal",
]
