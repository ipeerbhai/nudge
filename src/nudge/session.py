"""MCP session management for Nudge HTTP server."""

import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class Session:
    """Represents an MCP session."""

    session_id: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    client_info: Optional[Dict] = None
    protocol_version: str = "2025-06-18"
    terminated: bool = False

    def touch(self):
        """Update last_used_at timestamp."""
        self.last_used_at = time.time()

    def is_expired(self, ttl_seconds: Optional[float] = None) -> bool:
        """Check if session has expired based on TTL."""
        if ttl_seconds is None:
            return False  # No TTL means never expires
        return (time.time() - self.last_used_at) > ttl_seconds


class SessionManager:
    """Manages MCP sessions for the HTTP server."""

    def __init__(self, session_ttl: Optional[float] = None):
        """
        Initialize session manager.

        Args:
            session_ttl: Optional TTL in seconds for sessions. None means no expiry.
        """
        self._sessions: Dict[str, Session] = {}
        self._session_ttl = session_ttl

    def create_session(
        self,
        client_info: Optional[Dict] = None,
        protocol_version: str = "2025-06-18"
    ) -> Session:
        """
        Create a new session with a cryptographically secure ID.

        The session ID uses only visible ASCII characters (0x21-0x7E)
        as required by the MCP specification.

        Args:
            client_info: Optional client information from initialize request
            protocol_version: Protocol version negotiated with client

        Returns:
            The created Session object
        """
        # Generate cryptographically secure session ID
        # Using URL-safe base64 which uses A-Z, a-z, 0-9, -, _ (all in 0x21-0x7E range)
        session_id = secrets.token_urlsafe(32)

        session = Session(
            session_id=session_id,
            client_info=client_info,
            protocol_version=protocol_version
        )

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            The Session if found and valid, None otherwise
        """
        session = self._sessions.get(session_id)

        if session is None:
            return None

        if session.terminated:
            return None

        if session.is_expired(self._session_ttl):
            # Clean up expired session
            del self._sessions[session_id]
            return None

        # Update last used time
        session.touch()
        return session

    def validate_session(self, session_id: str) -> bool:
        """
        Check if a session ID is valid.

        Args:
            session_id: The session ID to validate

        Returns:
            True if session exists and is valid, False otherwise
        """
        return self.get_session(session_id) is not None

    def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a session.

        Args:
            session_id: The session ID to terminate

        Returns:
            True if session was found and terminated, False otherwise
        """
        session = self._sessions.get(session_id)

        if session is None:
            return False

        session.terminated = True
        return True

    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.

        Returns:
            Number of sessions removed
        """
        if self._session_ttl is None:
            return 0

        expired = [
            sid for sid, session in self._sessions.items()
            if session.is_expired(self._session_ttl) or session.terminated
        ]

        for sid in expired:
            del self._sessions[sid]

        return len(expired)

    @property
    def active_session_count(self) -> int:
        """Return count of active (non-terminated, non-expired) sessions."""
        return sum(
            1 for session in self._sessions.values()
            if not session.terminated and not session.is_expired(self._session_ttl)
        )
