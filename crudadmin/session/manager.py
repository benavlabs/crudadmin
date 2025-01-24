from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging
from uuid import uuid4

from fastapi import Request
from user_agents import parse

from .schemas import AdminSessionCreate, AdminSessionUpdate

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(
        self,
        db_config,
        max_sessions_per_user: int = 5,
        session_timeout_minutes: int = 30,
        cleanup_interval_minutes: int = 15,
    ):
        self.db_config = db_config
        self.max_sessions = max_sessions_per_user
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self.last_cleanup = datetime.now(timezone.utc)

    async def create_session(
        self, request: Request, user_id: int, metadata: dict = None
    ) -> AdminSessionCreate:
        """Create a new session for a user"""
        logger.info(f"Creating new session for user_id: {user_id}")

        try:
            user_agent = request.headers.get("user-agent", "")
            ua_parser = parse(user_agent)
            current_time = datetime.now(timezone.utc)

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
                ip_address=request.client.host,
                user_agent=user_agent,
                device_info=device_info,
                created_at=current_time,
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

    def make_timezone_aware(self, dt: datetime) -> datetime:
        """Convert naive datetime to UTC timezone-aware datetime"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    async def validate_session(
        self, db, session_id: str, update_activity: bool = True
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
                        last_activity = last_activity.replace(tzinfo=timezone.utc)

                current_time = datetime.now(timezone.utc)
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
                    await db.commit()

                return True

            except Exception as e:
                logger.error(
                    f"Error processing session last_activity: {str(e)}", exc_info=True
                )
                return False

        except Exception as e:
            logger.error(f"Error validating session: {str(e)}", exc_info=True)
            return False

    async def update_activity(self, db, session_id: str) -> None:
        """Update last activity timestamp for a session"""
        update_data = AdminSessionUpdate(last_activity=datetime.now(timezone.utc))
        await self.db_config.crud_sessions.update(
            db, session_id=session_id, object=update_data
        )

    async def terminate_session(self, db, session_id: str) -> None:
        """Terminate a specific session"""
        update_data = AdminSessionUpdate(
            is_active=False,
            session_metadata={
                "terminated_at": datetime.now(timezone.utc).isoformat(),
                "termination_reason": "manual_termination",
            },
        )
        await self.db_config.crud_sessions.update(
            db, session_id=session_id, object=update_data
        )

    async def get_user_active_sessions(self, db, user_id: int) -> List[dict]:
        """Get all active sessions for a user"""
        sessions = await self.db_config.crud_sessions.get_multi(
            db, user_id=user_id, is_active=True
        )
        return sessions["data"]

    async def cleanup_expired_sessions(self, db) -> None:
        """Cleanup expired and inactive sessions"""
        now = datetime.now(timezone.utc)

        if now - self.last_cleanup < self.cleanup_interval:
            return

        timeout_threshold = now - self.session_timeout

        expired_sessions = await self.db_config.crud_sessions.get_multi(
            db, is_active=True, last_activity__lt=timeout_threshold
        )

        for session in expired_sessions["data"]:
            update_data = AdminSessionUpdate(
                is_active=False,
                metadata={
                    "terminated_at": now.isoformat(),
                    "termination_reason": "session_timeout",
                },
            )
            await self.db_config.crud_sessions.update(
                db, session_id=session["session_id"], object=update_data
            )

        self.last_cleanup = now

    async def get_session_metadata(self, db, session_id: str) -> Optional[dict]:
        """Get complete session metadata including user agent info"""
        session = await self.db_config.crud_sessions.get(db, session_id=session_id)
        if not session:
            return None

        return {
            "session_id": session["session_id"],
            "user_id": session["user_id"],
            "ip_address": session["ip_address"],
            "device_info": session["device_info"],
            "created_at": session["created_at"],
            "last_activity": session["last_activity"],
            "is_active": session["is_active"],
            "metadata": session["metadata"],
        }

    async def handle_concurrent_login(
        self, db, user_id: int, current_session_id: str
    ) -> None:
        """Handle a new login when user has other active sessions"""
        active_sessions = await self.get_user_active_sessions(db, user_id)

        for session in active_sessions:
            if session["session_id"] != current_session_id:
                metadata = session["metadata"] or {}
                metadata["concurrent_login"] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "new_session_id": current_session_id,
                }

                update_data = AdminSessionUpdate(metadata=metadata)
                await self.db_config.crud_sessions.update(
                    db, session_id=session["session_id"], object=update_data
                )
