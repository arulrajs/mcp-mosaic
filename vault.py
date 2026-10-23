"""
Session-scoped ephemeral token vault.

Core novelty: deterministic within a session (same real value → same token always),
so the LLM can reason relationally across turns without seeing real values.
Vault lives only in memory and expires; it is never logged or persisted.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any


class TokenVault:
    """
    Maps real sensitive values ↔ opaque LLM-semantic tokens.

    Token format: [TYPE:hash4]
      e.g. [IP:a3f2], [UID:7b1c], [KEY:d9e3]

    The type label lets the LLM understand what kind of value it holds
    (for correct reasoning) without exposing the actual value.
    The 4-char hash is deterministic per (session_id, real_value) so the
    same real value always produces the same token within a session.
    """

    def __init__(self, session_id: str, ttl_minutes: int = 60):
        self.session_id = session_id
        self._expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=ttl_minutes)
        self._real_to_token: dict[str, str] = {}
        self._token_to_real: dict[str, str] = {}

    def is_expired(self) -> bool:
        return datetime.now(tz=timezone.utc) > self._expires_at

    def tokenize(self, real_value: str, type_label: str) -> str:
        """Return existing token or mint a new one. Deterministic per session."""
        if real_value in self._real_to_token:
            return self._real_to_token[real_value]

        digest = hashlib.sha256(
            f"{self.session_id}\x00{real_value}".encode()
        ).hexdigest()[:4]
        token = f"[{type_label}:{digest}]"

        # Collision guard: extend hash until unique
        suffix = 4
        while token in self._token_to_real and self._token_to_real[token] != real_value:
            suffix += 1
            digest = hashlib.sha256(
                f"{self.session_id}\x00{real_value}".encode()
            ).hexdigest()[:suffix]
            token = f"[{type_label}:{digest}]"

        self._real_to_token[real_value] = token
        self._token_to_real[token] = real_value
        return token

    def detokenize(self, token: str) -> str | None:
        return self._token_to_real.get(token)

    def detokenize_text(self, text: str) -> str:
        """Replace all known tokens in text with their real values."""
        for token, real in self._token_to_real.items():
            text = text.replace(token, real)
        return text

    def stats(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "tokens_minted": len(self._real_to_token),
            "expires_at": self._expires_at.isoformat(),
            "expired": self.is_expired(),
        }
