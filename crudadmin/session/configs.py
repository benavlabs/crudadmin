"""
Session backend configuration classes.

This module provides Pydantic models for configuring different session backends
in a type-safe and validated manner.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RedisConfig(BaseModel):
    """Configuration for Redis session backend."""

    url: Optional[str] = None
    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    username: Optional[str] = None
    password: Optional[str] = None
    pool_size: Optional[int] = Field(default=None, ge=1)
    connect_timeout: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("url", "host", "username", "password")
    @classmethod
    def validate_strings(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    def to_dict(self) -> Dict[str, Any]:
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
    """Configuration for Memcached session backend."""

    servers: Optional[List[str]] = None
    host: str = "localhost"
    port: int = Field(default=11211, ge=1, le=65535)
    pool_size: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, v):
        if v is not None:
            for server in v:
                if not isinstance(server, str) or not server.strip():
                    raise ValueError("Server addresses must be non-empty strings")
                if ":" in server:
                    host, port_str = server.split(":", 1)
                    try:
                        port = int(port_str)
                        if not (1 <= port <= 65535):
                            raise ValueError(
                                f"Port must be between 1 and 65535, got {port}"
                            )
                    except ValueError as e:
                        if "Port must be between" in str(e):
                            raise e
                        raise ValueError(
                            f"Invalid port in server address '{server}'"
                        ) from None
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, using servers or individual host/port."""
        result = {}

        if self.servers is not None:
            if self.servers:
                server = self.servers[0]
                if ":" in server:
                    host, port_str = server.split(":", 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        port = 11211
                else:
                    host = server
                    port = 11211
                result.update({"host": host, "port": port})
            else:
                result.update({"host": "localhost", "port": 11211})
        else:
            result.update({"host": self.host, "port": self.port})

        if self.pool_size is not None:
            result["pool_size"] = self.pool_size

        return result


SessionBackendConfig = Union[RedisConfig, MemcachedConfig, Dict[str, Any]]
