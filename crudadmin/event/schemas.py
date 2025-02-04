import enum
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class EventType(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    FAILED_LOGIN = "failed_login"


class EventStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"


class AdminEventLogBase(BaseModel):
    event_type: EventType
    status: EventStatus
    user_id: int
    session_id: str
    ip_address: str
    user_agent: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Dict[str, Any] = {}


class AdminEventLogCreate(AdminEventLogBase):
    pass


class AdminEventLogRead(AdminEventLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime


class AdminAuditLogBase(BaseModel):
    event_id: int
    resource_type: str
    resource_id: str
    action: str
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    changes: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}


class AdminAuditLogCreate(AdminAuditLogBase):
    pass


class AdminAuditLogRead(AdminAuditLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
