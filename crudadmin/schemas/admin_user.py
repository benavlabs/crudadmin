from typing import Annotated, Optional
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .timestamp import TimestampSchema


class AdminUserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(
            min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["userson"]
        ),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]


class AdminUser(TimestampSchema, AdminUserBase):
    hashed_password: str
    is_superuser: bool = True


class AdminUserRead(BaseModel):
    id: int

    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(
            min_length=2, max_length=20, pattern=r"^[a-z0-9]+$", examples=["userson"]
        ),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]
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

    name: Annotated[
        Optional[str],
        Field(min_length=2, max_length=30, examples=["User Userberg"], default=None),
    ]
    username: Annotated[
        Optional[str],
        Field(
            min_length=2,
            max_length=20,
            pattern=r"^[a-z0-9]+$",
            examples=["userberg"],
            default=None,
        ),
    ]
    email: Annotated[
        Optional[EmailStr], Field(examples=["user.userberg@example.com"], default=None)
    ]


class AdminUserUpdateInternal(AdminUserUpdate):
    updated_at: datetime
