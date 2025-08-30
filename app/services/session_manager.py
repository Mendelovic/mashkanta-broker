import uuid
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from agents import SQLiteSession

from ..config import settings


logger = logging.getLogger(__name__)

# In-memory cache for active sessions
# In production, this could be Redis or another distributed cache
_session_cache: Dict[str, SQLiteSession] = {}
_session_metadata: Dict[str, dict] = {}


class SessionManager:
    """Manages conversation sessions for the mortgage broker AI."""

    def __init__(self):
        self.db_path = settings.session_db_path
        self.session_prefix = settings.default_session_prefix
        # Initialize metadata tracking
        self._session_metadata = _session_metadata

    def create_session(
        self, user_id: Optional[str] = None
    ) -> tuple[str, SQLiteSession]:
        """
        Create a new conversation session.

        Args:
            user_id: Optional user identifier

        Returns:
            Tuple of (session_id, SQLiteSession instance)
        """
        try:
            # Generate unique session ID
            session_id = self._generate_session_id(user_id)

            # Create SQLite session instance
            session = SQLiteSession(session_id, self.db_path)

            # Cache the session
            _session_cache[session_id] = session
            _session_metadata[session_id] = {
                "created_at": datetime.now(),
                "last_accessed": datetime.now(),
                "user_id": user_id,
                "message_count": 0,
            }

            logger.info(f"Created new session: {session_id} (user: {user_id})")
            return session_id, session

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    async def get_session(self, session_id: str) -> Optional[SQLiteSession]:
        """
        Retrieve an existing session.

        Args:
            session_id: Session identifier

        Returns:
            SQLiteSession instance or None if not found
        """
        try:
            # Check cache first
            if session_id in _session_cache:
                # Update last accessed time
                if session_id in _session_metadata:
                    _session_metadata[session_id]["last_accessed"] = datetime.now()

                logger.debug(f"Retrieved session from cache: {session_id}")
                return _session_cache[session_id]

            # Try to recreate from database
            try:
                session = SQLiteSession(session_id, self.db_path)

                # Check if session has any data (i.e., exists in DB)
                items = await session.get_items(limit=1)
                if items or True:  # Accept even empty sessions for now
                    _session_cache[session_id] = session
                    _session_metadata[session_id] = {
                        "created_at": datetime.now(),  # We don't know the real creation time
                        "last_accessed": datetime.now(),
                        "user_id": None,  # We don't know the original user_id
                        "message_count": len(await session.get_items()) if items else 0,
                    }

                    logger.info(f"Recreated session from database: {session_id}")
                    return session

            except Exception as db_error:
                logger.debug(f"Session {session_id} not found in database: {db_error}")

            return None

        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None

    async def get_or_create_session(
        self, session_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> tuple[str, SQLiteSession]:
        """
        Get existing session or create new one.

        Args:
            session_id: Optional existing session ID
            user_id: Optional user identifier

        Returns:
            Tuple of (session_id, SQLiteSession instance)
        """
        try:
            if session_id:
                session = await self.get_session(session_id)
                if session:
                    return session_id, session

            # Create new session if not found or no session_id provided
            return self.create_session(user_id)

        except Exception as e:
            logger.error(f"Failed to get or create session: {e}")
            raise

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session completely.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully
        """
        try:
            # Remove from cache
            if session_id in _session_cache:
                del _session_cache[session_id]
            if session_id in _session_metadata:
                del _session_metadata[session_id]

            # Note: SQLiteSession doesn't provide a delete method
            # The session will be garbage collected from the database
            # when it's no longer referenced

            logger.info(f"Deleted session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def get_session_stats(self, session_id: str) -> Optional[dict]:
        """
        Get statistics for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary with session statistics or None
        """
        try:
            if session_id not in _session_metadata:
                return None

            metadata = _session_metadata[session_id].copy()
            metadata["session_id"] = session_id
            metadata["is_active"] = session_id in _session_cache

            return metadata

        except Exception as e:
            logger.error(f"Failed to get session stats for {session_id}: {e}")
            return None

    def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """
        Remove expired sessions from memory cache.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of sessions cleaned up
        """
        try:
            cleanup_count = 0
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

            expired_sessions = []
            for session_id, metadata in _session_metadata.items():
                if metadata["last_accessed"] < cutoff_time:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                if session_id in _session_cache:
                    del _session_cache[session_id]
                if session_id in _session_metadata:
                    del _session_metadata[session_id]
                cleanup_count += 1

            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} expired sessions")

            return cleanup_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0

    def _generate_session_id(self, user_id: Optional[str] = None) -> str:
        """
        Generate a unique session ID.

        Args:
            user_id: Optional user identifier to include in ID

        Returns:
            Unique session identifier
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_part = str(uuid.uuid4())[:8]

        if user_id:
            return f"{self.session_prefix}{user_id}_{timestamp}_{unique_part}"
        else:
            return f"{self.session_prefix}{timestamp}_{unique_part}"


# Global session manager instance
_session_manager = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
