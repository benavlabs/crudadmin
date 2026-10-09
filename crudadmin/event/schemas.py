import enum
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict = {}


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
    previous_state: dict | None = None
    new_state: dict | None = None
    changes: dict = {}
    audit_metadata: dict = Field(
        default_factory=dict,
        validation_alias=AliasChoices("audit_metadata", "metadata"),
    )


class AdminAuditLogCreate(AdminAuditLogBase):
    pass


class AdminAuditLogRead(AdminAuditLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
