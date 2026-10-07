import hashlib
from typing import Optional


def session_handle(session_id: Optional[str]) -> str:
    """A short, non-reversible stand-in for a session id or CSRF token.

    The raw value is a bearer credential: anyone who holds it is logged in. Logs
    and the event log use this handle instead, which still lets entries for the
    same session be correlated.
    """
    if not session_id:
        return "unknown"
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]
