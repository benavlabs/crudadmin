import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import Request, Response

from ..core.rate_limiter import SimpleRateLimiter
from .schemas import CSRFToken, SessionCreate, SessionData, UserAgentInfo
from .storage import AbstractSessionStorage, get_session_storage
from .user_agents_types import parse

UTC = timezone.utc

logger = logging.getLogger(__name__)

SamesiteType = Literal["lax", "strict", "none"]
DEV_SAMESITE: SamesiteType = "lax"
PROD_SAMESITE: SamesiteType = "strict"

DEFAULT_SETTINGS = {
    "SESSION_BACKEND": "memory",
    "SESSION_TIMEOUT_MINUTES": 30,
    "SESSION_CLEANUP_INTERVAL_MINUTES": 15,
    "MAX_SESSIONS_PER_USER": 5,
    "SESSION_COOKIE_MAX_AGE": 30 * 60,
    "CSRF_ENABLED": True,
    "DEBUG": False,
    "REDIS_HOST": "localhost",
    "REDIS_PORT": 6379,
    "REDIS_DB": 0,
    "REDIS_PASSWORD": None,
    "REDIS_POOL_SIZE": 10,
    "REDIS_CONNECT_TIMEOUT": 10,
    "MEMCACHED_HOST": "localhost",
    "MEMCACHED_PORT": 11211,
    "MEMCACHED_POOL_SIZE": 10,
}


def get_settings():
    """Get session settings with fallback to defaults."""
    return type("Settings", (), DEFAULT_SETTINGS)()


class SessionManager:
    """Session manager for handling secure authentication sessions in crudadmin.

    This class implements a comprehensive session-based authentication system with the following features:

    - Secure session creation and validation
    - CSRF protection with token generation and validation
    - Session expiration and automatic cleanup
    - Device fingerprinting and user agent tracking
    - Multi-device support with configurable session limits per user
    - IP address tracking for security monitoring
    - Session metadata for storing additional authentication context
    - Rate limiting for login attempts with IP and username tracking

    Authentication Flow:
    1. When a user logs in successfully, create_session() generates a new session and CSRF token
    2. Session cookies are set via set_session_cookies() - a httpOnly session_id and a non-httpOnly csrf_token
    3. On subsequent requests, validate_session() confirms the session is valid and not expired
    4. For state-changing operations, validate_csrf_token() provides protection against CSRF attacks
    5. Sessions automatically expire after inactivity, or can be manually terminated
    6. Periodic cleanup_expired_sessions() removes stale sessions

    Security Features:
    - Sessions are stored server-side with only the ID transmitted to clients
    - CSRF protection through synchronized tokens
    - Session hijacking protection via IP and user agent tracking
    - Automatic session expiration after configurable timeout
    - Forced logout of oldest sessions when session limit is reached
    - Different SameSite cookie settings for development and production
    - Rate limiting for login attempts to prevent brute force attacks

    Usage:
    Sessions should be validated on each authenticated request, with CSRF tokens validated
    for any state-changing operations. The cleanup method should be called periodically
    to remove expired sessions.
    """

    def __init__(
        self,
        session_storage: Optional[AbstractSessionStorage[SessionData]] = None,
        max_sessions_per_user: int = 5,
        session_timeout_minutes: int = 30,
        cleanup_interval_minutes: int = 15,
        csrf_token_bytes: int = 32,
        rate_limiter: Optional[SimpleRateLimiter] = None,
        login_max_attempts: int = 5,
        login_window_minutes: int = 15,
        session_backend: str = "memory",
        **backend_kwargs: Any,
    ):
        """Initialize the session manager.

        Args:
            session_storage: Storage backend for sessions (if None, will be created)
            max_sessions_per_user: Maximum number of active sessions per user
            session_timeout_minutes: Session timeout in minutes
            cleanup_interval_minutes: Interval for cleaning up expired sessions
            csrf_token_bytes: Number of bytes to use for CSRF tokens
            rate_limiter: Optional rate limiter implementation for login attempts
            login_max_attempts: Maximum failed login attempts before rate limiting
            login_window_minutes: Time window for tracking failed login attempts
            session_backend: Backend type if creating storage automatically
            **backend_kwargs: Additional arguments for backend creation
        """
        self.max_sessions = max_sessions_per_user
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self.last_cleanup = datetime.now(UTC)
        self.csrf_token_bytes = csrf_token_bytes
        self.rate_limiter = rate_limiter
        self.login_max_attempts = login_max_attempts
        self.login_window = timedelta(minutes=login_window_minutes)

        if session_storage is None:
            storage_settings = {
                "prefix": "session:",
                "expiration": session_timeout_minutes * 60,
                **backend_kwargs,
            }
            self.storage: AbstractSessionStorage[SessionData] = get_session_storage(
                backend=session_backend, model_type=SessionData, **storage_settings
            )
        else:
            self.storage = session_storage

        csrf_storage_settings = {
            "prefix": "csrf:",
            "expiration": session_timeout_minutes * 60,
        }
        csrf_storage_settings.update(backend_kwargs)
        self.csrf_storage: AbstractSessionStorage[CSRFToken] = get_session_storage(
            backend=session_backend, model_type=CSRFToken, **csrf_storage_settings
        )

    def parse_user_agent(self, user_agent_string: str) -> UserAgentInfo:
        """Parse User-Agent string into structured information.

        Args:
            user_agent_string: Raw User-Agent header

        Returns:
            Structured UserAgentInfo
        """
        ua_parser = parse(user_agent_string)
        return UserAgentInfo(
            browser=ua_parser.browser.family,
            browser_version=ua_parser.browser.version_string,
            os=ua_parser.os.family,
            device=ua_parser.device.family,
            is_mobile=ua_parser.is_mobile,
            is_tablet=ua_parser.is_tablet,
            is_pc=ua_parser.is_pc,
        )

    async def create_session(
        self, request: Request, user_id: int, metadata: Optional[dict[str, Any]] = None
    ) -> tuple[str, str]:
        """Create a new session for a user and generate a CSRF token.

        Args:
            request: The request object
            user_id: The user ID
            metadata: Optional session metadata

        Returns:
            Tuple of (session_id, csrf_token)

        Raises:
            ValueError: If the request client is invalid
        """
        logger.info(f"Creating new session for user_id: {user_id}")

        try:
            user_agent = request.headers.get("user-agent", "")
            current_time = datetime.now(UTC)

            client = request.client
            if client is None:
                logger.error("Request client is None. Cannot retrieve IP address.")
                raise ValueError("Invalid request client.")

            device_info = self.parse_user_agent(user_agent).model_dump()

            ip_address = (
                request.headers.get("x-forwarded-for", client.host)
                .split(",")[0]
                .strip()
            )

            await self._enforce_session_limit(user_id)

            session_data = SessionCreate(
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                device_info=device_info,
                last_activity=current_time,
                is_active=True,
                metadata=metadata or {},
            )

            session_id = await self.storage.create(session_data)
            csrf_token = await self._generate_csrf_token(user_id, session_id)

            logger.info(f"Session {session_id} created successfully")
            return session_id, csrf_token

        except Exception as e:
            logger.error(f"Error creating session: {str(e)}", exc_info=True)
            raise

    async def validate_session(
        self, session_id: str, update_activity: bool = True
    ) -> Optional[SessionData]:
        """Validate if a session is active and not timed out.

        Args:
            session_id: The session ID
            update_activity: Whether to update the last activity timestamp

        Returns:
            The session data if valid, None otherwise
        """
        if not session_id:
            return None

        try:
            session_data = await self.storage.get(session_id, SessionData)
            if session_data is None:
                logger.warning(f"Session not found: {session_id}")
                return None

            if not session_data.is_active:
                logger.warning(f"Session is not active: {session_id}")
                return None

            current_time = datetime.now(UTC)
            session_age = current_time - session_data.last_activity

            if session_age > self.session_timeout:
                logger.warning(f"Session timed out: {session_id}")
                await self.terminate_session(session_id)
                return None

            if update_activity:
                session_data.last_activity = current_time
                await self.storage.update(session_id, session_data)

            return session_data

        except Exception as e:
            logger.error(f"Error validating session: {str(e)}", exc_info=True)
            return None

    async def validate_csrf_token(
        self,
        session_id: str,
        csrf_token: str,
    ) -> bool:
        """Validate a CSRF token for a session.

        Args:
            session_id: The session ID
            csrf_token: The CSRF token to validate

        Returns:
            True if valid, False otherwise
        """
        if not session_id or not csrf_token:
            logger.warning(
                f"Missing session_id or csrf_token: session_id={session_id}, csrf_token={csrf_token}"
            )
            return False

        try:
            token_data = await self.csrf_storage.get(csrf_token, CSRFToken)
            if token_data is None:
                logger.warning(f"CSRF token not found in storage: {csrf_token}")
                return False

            if token_data.session_id != session_id:
                logger.warning(
                    f"CSRF token session mismatch: {csrf_token} should be for session {session_id}, "
                    f"but is for session {token_data.session_id}"
                )
                return False

            current_time = datetime.now(UTC)
            if token_data.expires_at < current_time:
                logger.warning(
                    f"CSRF token expired: {csrf_token}, expired at {token_data.expires_at}, current time is {current_time}"
                )
                await self.csrf_storage.delete(csrf_token)
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating CSRF token: {str(e)}", exc_info=True)
            return False

    async def regenerate_csrf_token(
        self,
        user_id: int,
        session_id: str,
    ) -> str:
        """Regenerate a CSRF token for an existing session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            The new CSRF token
        """
        try:
            if hasattr(self.csrf_storage, "_scan_iter"):
                keys = await self.csrf_storage._scan_iter(
                    match=f"{self.csrf_storage.prefix}*"
                )
                for key in keys:
                    try:
                        token_id = key[len(self.csrf_storage.prefix) :]
                        csrf_data = await self.csrf_storage.get(token_id, CSRFToken)
                        if csrf_data and csrf_data.session_id == session_id:
                            await self.csrf_storage.delete(token_id)
                    except Exception as e:
                        logger.warning(f"Error cleaning up old CSRF token: {e}")
        except Exception as e:
            logger.warning(f"Error scanning for old CSRF tokens: {e}")

        return await self._generate_csrf_token(user_id, session_id)

    async def _generate_csrf_token(
        self,
        user_id: int,
        session_id: str,
    ) -> str:
        """Generate a new CSRF token for a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            The CSRF token
        """
        token = secrets.token_hex(self.csrf_token_bytes)
        expires_at = datetime.now(UTC) + self.session_timeout

        csrf_data = CSRFToken(
            token=token,
            user_id=user_id,
            session_id=session_id,
            expires_at=expires_at,
        )

        await self.csrf_storage.create(csrf_data, session_id=token)
        return token

    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a specific session.

        Args:
            session_id: The session ID

        Returns:
            True if the session was terminated, False otherwise
        """
        try:
            session_data = await self.storage.get(session_id, SessionData)
            if session_data is None:
                return False

            session_data.is_active = False
            session_data.metadata = {
                **session_data.metadata,
                "terminated_at": datetime.now(UTC).isoformat(),
                "termination_reason": "manual_termination",
            }

            return await self.storage.update(session_id, session_data)

        except Exception as e:
            logger.error(f"Error terminating session: {str(e)}", exc_info=True)
            return False

    async def _enforce_session_limit(self, user_id: int) -> None:
        """Enforce the maximum number of sessions per user.

        Terminates the oldest sessions if the limit is exceeded.

        Args:
            user_id: The user ID
        """
        try:
            active_sessions = []

            if hasattr(self.storage, "get_user_sessions"):
                try:
                    session_ids = await self.storage.get_user_sessions(user_id)
                    for session_id in session_ids:
                        try:
                            session_data = await self.storage.get(
                                session_id, SessionData
                            )
                            if session_data and session_data.is_active:
                                active_sessions.append(session_data)
                        except Exception as e:
                            logger.warning(
                                f"Error processing session {session_id}: {e}"
                            )
                            continue
                except Exception as e:
                    logger.warning(f"Error getting user sessions: {e}")
                    active_sessions = await self._get_active_sessions_by_scan(user_id)
            else:
                active_sessions = await self._get_active_sessions_by_scan(user_id)

            if len(active_sessions) >= self.max_sessions:
                active_sessions.sort(key=lambda s: s.last_activity)

                excess_count = len(active_sessions) - self.max_sessions + 1
                for i in range(excess_count):
                    if i < len(active_sessions):
                        await self.terminate_session(active_sessions[i].session_id)

        except Exception as e:
            logger.error(f"Error enforcing session limit: {e}", exc_info=True)

    async def _get_active_sessions_by_scan(self, user_id: int) -> list[SessionData]:
        """Get active sessions for a user by scanning all keys.

        This is a fallback method when indexed groups are not available.

        Args:
            user_id: The user ID

        Returns:
            List of active sessions for the user
        """
        active_sessions = []

        if hasattr(self.storage, "_scan_iter"):
            keys = await self.storage._scan_iter(match=f"{self.storage.prefix}*")
            for key in keys:
                try:
                    session_data_bytes = await self.storage.get(
                        session_id=key[len(self.storage.prefix) :],
                        model_class=SessionData,
                    )
                    if (
                        session_data_bytes
                        and session_data_bytes.user_id == user_id
                        and session_data_bytes.is_active
                    ):
                        active_sessions.append(session_data_bytes)
                except Exception as e:
                    logger.warning(f"Error processing session during cleanup: {e}")
                    continue
        elif hasattr(self.storage, "client") and hasattr(
            self.storage.client, "scan_iter"
        ):
            async for key in self.storage.client.scan_iter(
                match=f"{self.storage.prefix}*"
            ):
                try:
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    session_id = key[len(self.storage.prefix) :]

                    session_data = await self.storage.get(session_id, SessionData)
                    if (
                        session_data
                        and session_data.user_id == user_id
                        and session_data.is_active
                    ):
                        active_sessions.append(session_data)
                except Exception as e:
                    logger.warning(f"Error processing session during cleanup: {e}")
                    continue

        return active_sessions

    async def cleanup_expired_sessions(self) -> None:
        """Cleanup expired and inactive sessions.

        This should be called periodically.
        """
        now = datetime.now(UTC)

        if now - self.last_cleanup < self.cleanup_interval:
            return

        timeout_threshold = now - self.session_timeout

        try:
            if hasattr(self.storage, "_scan_iter"):
                keys = await self.storage._scan_iter(match=f"{self.storage.prefix}*")
                for key in keys:
                    try:
                        session_id = key[len(self.storage.prefix) :]
                        session_data = await self.storage.get(session_id, SessionData)
                        if (
                            session_data
                            and session_data.is_active
                            and session_data.last_activity < timeout_threshold
                        ):
                            session_data.is_active = False
                            session_data.metadata = {
                                **session_data.metadata,
                                "terminated_at": now.isoformat(),
                                "termination_reason": "session_timeout",
                            }
                            await self.storage.update(session_id, session_data)
                    except Exception as e:
                        logger.warning(f"Error processing session during cleanup: {e}")
                        continue
            elif hasattr(self.storage, "client") and hasattr(
                self.storage.client, "scan_iter"
            ):
                async for key in self.storage.client.scan_iter(
                    match=f"{self.storage.prefix}*"
                ):
                    try:
                        if isinstance(key, bytes):
                            key = key.decode("utf-8")
                        session_id = key[len(self.storage.prefix) :]

                        session_data = await self.storage.get(session_id, SessionData)
                        if (
                            session_data
                            and session_data.is_active
                            and session_data.last_activity < timeout_threshold
                        ):
                            session_data.is_active = False
                            session_data.metadata = {
                                **session_data.metadata,
                                "terminated_at": now.isoformat(),
                                "termination_reason": "session_timeout",
                            }
                            await self.storage.update(
                                session_data.session_id, session_data
                            )
                    except Exception as e:
                        logger.warning(f"Error processing session during cleanup: {e}")
                        continue

            if self.rate_limiter:
                try:
                    await self.cleanup_rate_limits()
                except Exception as e:
                    logger.error(f"Error cleaning up rate limits: {e}")

            self.last_cleanup = now

        except Exception as e:
            logger.error(f"Error during session cleanup: {e}", exc_info=True)

    def set_session_cookies(
        self,
        response: Response,
        session_id: str,
        csrf_token: str,
        max_age: Optional[int] = None,
        path: str = "/",
        secure: bool = True,
    ) -> None:
        """Set session cookies in the response.

        Args:
            response: The response object
            session_id: The session ID
            csrf_token: The CSRF token
            max_age: Cookie max age in seconds
            path: Cookie path
            secure: Whether to set the Secure flag
        """
        settings = get_settings()
        samesite: SamesiteType = DEV_SAMESITE if settings.DEBUG else PROD_SAMESITE
        cookie_max_age = (
            max_age if max_age is not None else settings.SESSION_COOKIE_MAX_AGE
        )

        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path=path,
            max_age=cookie_max_age,
        )

        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=secure,
            samesite=samesite,
            path=path,
            max_age=cookie_max_age,
        )

    def clear_session_cookies(
        self,
        response: Response,
        path: str = "/",
    ) -> None:
        """Clear session cookies from the response.

        Args:
            response: The response object
            path: Cookie path
        """
        response.delete_cookie(key="session_id", path=path)
        response.delete_cookie(key="csrf_token", path=path)

    async def track_login_attempt(
        self, ip_address: str, username: str, success: bool = False
    ) -> tuple[bool, Optional[int]]:
        """Track login attempts and apply rate limiting.

        Args:
            ip_address: Client IP address
            username: Username being used for login
            success: Whether the login attempt was successful

        Returns:
            Tuple of (is_allowed, attempts_remaining)

        If rate limiting is not configured, this will always return (True, None)
        but log a warning about missing rate limiting.
        """
        if not self.rate_limiter:
            logger.warning(
                "No rate limiter configured for login attempts. "
                "It is strongly recommended to configure rate limiting for security."
            )
            return True, None

        try:
            ip_key = f"login:ip:{ip_address}"
            username_key = f"login:user:{username}"

            if success:
                try:
                    await self.rate_limiter.delete(ip_key)
                    await self.rate_limiter.delete(username_key)
                    return True, None
                except Exception as e:
                    logger.warning(
                        f"Error clearing rate limit after successful login: {e}"
                    )
                    return True, None

            try:
                expiry_seconds = int(self.login_window.total_seconds())
                ip_count = await self.rate_limiter.increment(ip_key, 1, expiry_seconds)
                username_count = await self.rate_limiter.increment(
                    username_key, 1, expiry_seconds
                )
            except Exception as e:
                logger.warning(f"Error tracking login attempt rate limits: {e}")
                return True, None

            attempt_count = max(ip_count, username_count)
            remaining = max(0, self.login_max_attempts - attempt_count)

            is_allowed = attempt_count <= self.login_max_attempts

            if not is_allowed:
                logger.warning(
                    f"Rate limit exceeded for login: {ip_address}, username: {username}, attempts: {attempt_count}"
                )

            return is_allowed, remaining

        except Exception as e:
            logger.error(f"Unexpected error in login rate limiting: {e}", exc_info=True)
            return True, None

    async def cleanup_rate_limits(self) -> None:
        """Clean up expired rate limit records.

        This should be called periodically along with session cleanup.
        """
        if not self.rate_limiter:
            return

        try:
            if hasattr(self.rate_limiter, "delete_pattern"):
                await self.rate_limiter.delete_pattern("login:*")
            else:
                logger.debug("Rate limiter does not support pattern-based cleanup")
        except Exception as e:
            logger.error(f"Error cleaning up rate limit records: {e}", exc_info=True)
