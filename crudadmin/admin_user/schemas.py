from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..core.schemas.timestamp import TimestampSchema


class AdminUserBase(BaseModel):
    username: Annotated[
        str,
        Field(min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["admin"]),
    ]


class AdminUser(TimestampSchema, AdminUserBase):
    id: int
    hashed_password: str
    is_superuser: bool = True


class AdminUserRead(BaseModel):
    id: int
    username: str
    is_superuser: bool


class AdminUserCreate(AdminUserBase):
    model_config = ConfigDict(extra="forbid")

    password: Annotated[
        str,
        Field(
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
            examples=["Str1ngst!"],
        ),
    ]


class AdminUserCreateInternal(AdminUserBase):
    hashed_password: str


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        Optional[str],
        Field(
            min_length=2,
            max_length=20,
            pattern=r"^[a-z0-9]+$",
            examples=["admin"],
            default=None,
        ),
    ]
    password: Annotated[
        Optional[str],
        Field(
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
            examples=["NewStr1ngst!"],
            default=None,
        ),
    ]


class AdminUserUpdateInternal(AdminUserUpdate):
    updated_at: datetime
    hashed_password: Optional[str] = None
