import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Request
from user_agents import parse

from .schemas import AdminSessionCreate, AdminSessionUpdate

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(
        self,
        db_config: Any,
        max_sessions_per_user: int = 5,
        session_timeout_minutes: int = 30,
        cleanup_interval_minutes: int = 15,
    ):
        self.db_config = db_config
        self.max_sessions = max_sessions_per_user
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self.last_cleanup = datetime.now(UTC)

    async def create_session(
        self, request: Request, user_id: int, metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[AdminSessionCreate]:
        """Create a new session for a user"""
        logger.info(f"Creating new session for user_id: {user_id}")

        try:
            user_agent = request.headers.get("user-agent", "")
            ua_parser = parse(user_agent)
            current_time = datetime.now(UTC)

            client = request.client
            if client is None:
                logger.error("Request client is None. Cannot retrieve IP address.")
                raise ValueError("Invalid request client.")

            device_info = {
                "browser": ua_parser.browser.family,
                "browser_version": ua_parser.browser.version_string,
                "os": ua_parser.os.family,
                "device": ua_parser.device.family,
                "is_mobile": ua_parser.is_mobile,
                "is_tablet": ua_parser.is_tablet,
                "is_pc": ua_parser.is_pc,
            }

            session_id = str(uuid4())
            session_data = AdminSessionCreate(
                user_id=user_id,
                session_id=session_id,
                ip_address=client.host,
                user_agent=user_agent,
                device_info=device_info,
                last_activity=current_time,
                is_active=True,
                session_metadata=metadata or {},
            )

            logger.debug(f"Session data prepared: {session_data.model_dump()}")

            async for admin_session in self.db_config.get_admin_db():
                try:
                    existing_sessions = await self.get_user_active_sessions(
                        admin_session, user_id
                    )
                    if len(existing_sessions) >= self.max_sessions:
                        logger.info(
                            f"Max sessions ({self.max_sessions}) reached, deactivating old sessions"
                        )
                        for session in existing_sessions:
                            await self.terminate_session(
                                admin_session, session["session_id"]
                            )
                            await admin_session.commit()

                    logger.info("Creating new session in database")
                    result = await self.db_config.crud_sessions.create(
                        admin_session, object=session_data
                    )
                    logger.debug(f"Create session result: {result}")

                    if not result:
                        raise Exception("Failed to create session - no result returned")

                    await admin_session.commit()
                    logger.info(
                        f"Session {session_id} created and committed successfully"
                    )
                    return session_data

                except Exception as e:
                    logger.error(f"Error in session creation: {str(e)}", exc_info=True)
                    await admin_session.rollback()
                    raise

        except Exception as e:
            logger.error(f"Session creation failed: {str(e)}", exc_info=True)
            raise

        return None

    def make_timezone_aware(self, dt: datetime) -> datetime:
        """Convert naive datetime to UTC timezone-aware datetime"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    async def validate_session(
        self, db: Any, session_id: str, update_activity: bool = True
    ) -> bool:
        """Validate if a session is active and not timed out"""
        logger.debug(f"Validating session: {session_id}")

        try:
            result = await self.db_config.crud_sessions.get_multi(
                db, session_id=session_id, limit=1
            )

            if not result or "data" not in result:
                logger.warning(f"Session not found: {session_id}")
                return False

            sessions = result["data"]
            if not sessions:
                logger.warning(f"No session found: {session_id}")
                return False

            session = sessions[0]
            if not session.get("is_active", False):
                logger.warning(f"Session is not active: {session_id}")
                return False

            try:
                last_activity_str = session.get("last_activity")
                if not last_activity_str:
                    logger.warning(f"No last_activity found for session: {session_id}")
                    return False

                if isinstance(last_activity_str, datetime):
                    last_activity = self.make_timezone_aware(last_activity_str)
                else:
                    last_activity = datetime.fromisoformat(
                        last_activity_str.replace("Z", "+00:00")
                    )
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=UTC)

                current_time = datetime.now(UTC)
                if current_time - last_activity > self.session_timeout:
                    logger.warning(f"Session timed out: {session_id}")
                    await self.terminate_session(db, session_id)
                    return False

                if update_activity:
                    logger.debug(f"Updating activity for session: {session_id}")
                    update_data = AdminSessionUpdate(last_activity=current_time)
                    await self.db_config.crud_sessions.update(
                        db, session_id=session_id, object=update_data
                    )

                return True

            except Exception as e:
                logger.error(
                    f"Error processing session last_activity: {str(e)}", exc_info=True
                )
                return False

        except Exception as e:
            logger.error(f"Error validating session: {str(e)}", exc_info=True)
            return False

    async def update_activity(self, db: Any, session_id: str) -> None:
        """Update last activity timestamp for a session"""
        update_data = AdminSessionUpdate(last_activity=datetime.now(UTC))
        await self.db_config.crud_sessions.update(
            db, session_id=session_id, object=update_data
        )

    async def terminate_session(self, db: Any, session_id: str) -> None:
        """Terminate a specific session"""
        update_data = AdminSessionUpdate(
            is_active=False,
            session_metadata={
                "terminated_at": datetime.now(UTC).isoformat(),
                "termination_reason": "manual_termination",
            },
        )
        await self.db_config.crud_sessions.update(
            db, session_id=session_id, object=update_data
        )

    async def get_user_active_sessions(
        self, db: Any, user_id: int
    ) -> List[Dict[str, Any]]:
        """Get all active sessions for a user"""
        sessions = await self.db_config.crud_sessions.get_multi(
            db, user_id=user_id, is_active=True
        )
        data = sessions.get("data", [])

        if not isinstance(data, list):
            logger.error("Expected 'data' to be a list, got something else.")
            return []

        valid_sessions = [session for session in data if isinstance(session, dict)]
        return valid_sessions

    async def cleanup_expired_sessions(self, db: Any) -> None:
        """Cleanup expired and inactive sessions"""
        now = datetime.now(UTC)

        if now - self.last_cleanup < self.cleanup_interval:
            return

        timeout_threshold = now - self.session_timeout

        expired_sessions = await self.db_config.crud_sessions.get_multi(
            db, is_active=True, last_activity__lt=timeout_threshold
        )

        for session in expired_sessions.get("data", []):
            if not isinstance(session, dict):
                logger.warning(f"Invalid session data format: {session}")
                continue

            update_data = AdminSessionUpdate(
                is_active=False,
                session_metadata={
                    "terminated_at": now.isoformat(),
                    "termination_reason": "session_timeout",
                },
            )
            await self.db_config.crud_sessions.update(
                db, session_id=session.get("session_id", ""), object=update_data
            )

        self.last_cleanup = now

    async def get_session_metadata(
        self, db: Any, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get complete session metadata including user agent info"""
        session = await self.db_config.crud_sessions.get(db, session_id=session_id)
        if not session:
            return None

        return {
            "session_id": session.get("session_id"),
            "user_id": session.get("user_id"),
            "ip_address": session.get("ip_address"),
            "device_info": session.get("device_info"),
            "created_at": session.get("created_at"),
            "last_activity": session.get("last_activity"),
            "is_active": session.get("is_active"),
            "metadata": session.get("metadata"),
        }

    async def handle_concurrent_login(
        self, db: Any, user_id: int, current_session_id: str
    ) -> None:
        """Handle a new login when user has other active sessions"""
        active_sessions = await self.get_user_active_sessions(db, user_id)

        for session in active_sessions:
            if session.get("session_id") != current_session_id:
                metadata = session.get("metadata", {})
                metadata["concurrent_login"] = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "new_session_id": current_session_id,
                }

                update_data = AdminSessionUpdate(session_metadata=metadata)
                await self.db_config.crud_sessions.update(
                    db, session_id=session.get("session_id", ""), object=update_data
                )
