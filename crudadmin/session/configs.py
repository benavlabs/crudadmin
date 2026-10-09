"""
Session backend configuration classes.

This module provides Pydantic models for configuring different session backends
in a type-safe and validated manner.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RedisConfig(BaseModel):
    """Configuration for Redis session backend."""

    url: str | None = None
    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    username: str | None = None
    password: str | None = None
    pool_size: int | None = Field(default=None, ge=1)
    connect_timeout: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("url", "host", "username", "password")
    @classmethod
    def validate_strings(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values and handling URL parsing."""
        result = {}

        if self.url is not None:
            from urllib.parse import urlparse

            parsed = urlparse(self.url)
            result.update(
                {
                    "host": parsed.hostname or "localhost",
                    "port": parsed.port or 6379,
                    "db": int(parsed.path.lstrip("/"))
                    if parsed.path and parsed.path != "/"
                    else 0,
                }
            )
            if parsed.username:
                result["username"] = parsed.username
            if parsed.password:
                result["password"] = parsed.password
        else:
            result.update(
                {
                    "host": self.host,
                    "port": self.port,
                    "db": self.db,
                }
            )
            if self.username is not None:
                result["username"] = self.username
            if self.password is not None:
                result["password"] = self.password

        if self.pool_size is not None:
            result["pool_size"] = self.pool_size
        if self.connect_timeout is not None:
            result["connect_timeout"] = self.connect_timeout

        return result


class MemcachedConfig(BaseModel):
    """Configuration for the removed Memcached session backend.

    Kept so existing imports keep working; passing it to ``CRUDAdmin`` raises a
    ``ValueError`` that names the replacements (``redis`` or ``database``).
    """

    servers: list[str] | None = None
    host: str = "localhost"
    port: int = Field(default=11211, ge=1, le=65535)
    pool_size: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


SessionBackendConfig = RedisConfig | MemcachedConfig | dict[str, Any]
