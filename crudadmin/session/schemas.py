from datetime import UTC, datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AdminSessionBase(BaseModel):
    user_id: int
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    ip_address: str
    user_agent: str
    device_info: Dict[str, Any]
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True
    session_metadata: dict = Field(default_factory=dict)


class AdminSessionCreate(AdminSessionBase):
    pass


class AdminSessionUpdate(BaseModel):
    last_activity: Optional[datetime] = None
    is_active: Optional[bool] = None
    session_metadata: Optional[Dict[str, Any]] = None


class AdminSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    session_id: str
    ip_address: str
    user_agent: str
    device_info: dict
    created_at: datetime
    last_activity: datetime
    is_active: bool
    session_metadata: dict
