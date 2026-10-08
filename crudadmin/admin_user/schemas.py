from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..core.schemas.timestamp import TimestampSchema

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class AdminUserBase(BaseModel):
    username: Annotated[
        str,
        Field(min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["admin"]),
    ]


class AdminUser(TimestampSchema, AdminUserBase):
    id: int
    hashed_password: str
    is_superuser: bool = False
    is_active: bool = True
    token_version: int = 0


class AdminUserRead(BaseModel):
    id: int
    username: str
    is_superuser: bool
    is_active: bool


class AdminUserCreate(AdminUserBase):
    model_config = ConfigDict(extra="forbid")

    password: Annotated[
        str,
        Field(
            min_length=PASSWORD_MIN_LENGTH,
            max_length=PASSWORD_MAX_LENGTH,
            examples=["Str1ngst!"],
        ),
    ]
    is_superuser: bool = False


class AdminUserCreateInternal(AdminUserBase):
    hashed_password: str
    is_superuser: bool = False


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        Optional[str],
        Field(
            min_length=2,
            max_length=20,
            pattern=r"^[a-z0-9]+$",
            examples=["admin"],
        ),
    ] = None
    password: Annotated[
        Optional[str],
        Field(
            min_length=PASSWORD_MIN_LENGTH,
            max_length=PASSWORD_MAX_LENGTH,
            examples=["NewStr1ngst!"],
        ),
    ] = None
    is_superuser: Optional[bool] = None
    is_active: Optional[bool] = None


class AdminUserUpdateInternal(AdminUserUpdate):
    updated_at: datetime
    hashed_password: Optional[str] = None
