"""
Type-annotated wrapper for the user_agents module.
This module provides proper type annotations for the user_agents module.
"""

from typing import NamedTuple, Optional, cast

# mypy: disable-error-code="import-untyped"
from user_agents import parse as _parse


class Browser(NamedTuple):
    """Browser information."""

    family: str
    version: Optional[str] = None
    version_string: str = ""


class OperatingSystem(NamedTuple):
    """Operating system information."""

    family: str
    version: Optional[str] = None
    version_string: str = ""


class Device(NamedTuple):
    """Device information."""

    family: str
    brand: Optional[str] = None
    model: Optional[str] = None


class UserAgent:
    """User agent information with proper typing."""

    browser: Browser
    os: OperatingSystem
    device: Device
    is_mobile: bool
    is_tablet: bool
    is_pc: bool
    is_bot: bool

    def __str__(self) -> str:
        return f"{self.browser.family}/{self.browser.version_string} ({self.os.family})"


def parse(user_agent_string: str) -> UserAgent:
    """
    Parse a user agent string into structured data.

    Args:
        user_agent_string: The user agent string to parse

    Returns:
        A UserAgent object with parsed information
    """
    return cast(UserAgent, _parse(user_agent_string))
