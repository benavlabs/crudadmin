from datetime import datetime

from pydantic import BaseModel


class AdminToken(BaseModel):
    access_token: str
    token_type: str


class AdminTokenData(BaseModel):
    username_or_email: str


class AdminTokenBlacklistBase(BaseModel):
    token: str
    expires_at: datetime


class AdminTokenBlacklistCreate(AdminTokenBlacklistBase):
    pass


class AdminTokenBlacklistUpdate(AdminTokenBlacklistBase):
    pass
