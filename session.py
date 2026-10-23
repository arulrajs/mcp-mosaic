"""
Session manager: one vault + proxy pair per agent session.
Sessions are ephemeral and expire automatically.
"""
import secrets
from typing import Optional

from mcp_mosaic.vault import TokenVault
from mcp_mosaic.proxy import MosaicProxy


class MosaicSession:
    def __init__(self, session_id: str, ttl_minutes: int = 60):
        self.session_id = session_id
        self.vault = TokenVault(session_id, ttl_minutes)
        self.proxy = MosaicProxy(self.vault)

    @property
    def expired(self) -> bool:
        return self.vault.is_expired()


class MosaicSessionManager:
    """
    Lifecycle owner for MosaicSession objects.

    One session per user/agent interaction; sessions are never shared across
    users. Expired sessions are evicted lazily on next access.
    """

    def __init__(self, ttl_minutes: int = 60):
        self._ttl = ttl_minutes
        self._sessions: dict[str, MosaicSession] = {}

    def get_or_create(self, session_id: Optional[str] = None) -> MosaicSession:
        if session_id is None:
            session_id = secrets.token_hex(16)

        existing = self._sessions.get(session_id)
        if existing and not existing.expired:
            return existing

        session = MosaicSession(session_id, self._ttl)
        self._sessions[session_id] = session
        return session

    def invalidate(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _evict_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.expired]
        for sid in expired:
            del self._sessions[sid]
