"""Persistent memory for the conductor / Ara agent via Mem0.

Search before reply, write after. Uses a stable ``user_id`` so the text
side (TypingMind) and the voice side (LiveKit) share one brain.

Design rules (from the owner):
- Never block on key drama. If ``MEM0_API_KEY`` is unset or ``mem0ai`` is
  not installed, this degrades to a silent no-op instead of raising.
- Never require copy/pasting a key from a browser. The key is read from the
  environment (populated by ``.env`` / keychain / ``ara keys auto``).
- Values are never logged.
"""

from __future__ import annotations

import os

from utils.logger import logger

# Same default user_id as the memory hub so both surfaces share memory.
DEFAULT_USER_ID = "ara-partner"


class Mem0Memory:
    """Thin, fail-open wrapper around the hosted Mem0 client."""

    def __init__(self, user_id: str | None = None) -> None:
        # Resolve config at construction, not import, so env overrides (and
        # tests that patch the environment) are honored.
        self.user_id = user_id or os.getenv("ARA_MEMORY_USER_ID", DEFAULT_USER_ID)
        self.search_limit = int(os.getenv("MEM0_SEARCH_LIMIT", "5"))
        self._client = self._build_client()

    @staticmethod
    def _build_client():
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            logger.debug("Mem0 disabled (no MEM0_API_KEY); memory is a no-op.")
            return None
        try:
            from mem0 import MemoryClient
        except ImportError:
            logger.debug("Mem0 disabled (mem0ai not installed); memory is a no-op.")
            return None
        try:
            client = MemoryClient(api_key=api_key)
            logger.info("Mem0 memory enabled.")
            return client
        except Exception as exc:  # noqa: BLE001 - never let memory break a reply
            logger.warning(f"Mem0 init failed ({type(exc).__name__}); memory disabled.")
            return None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @staticmethod
    def _rows(result) -> list:
        # Mem0 has returned both a bare list and {"results": [...]} over versions.
        if isinstance(result, dict):
            return result.get("results", []) or []
        return result or []

    def search(self, query: str, *, user_id: str | None = None) -> str:
        """Return a newline-joined memory context, or '' if none/disabled."""
        if not self._client or not query.strip():
            return ""
        try:
            rows = self._rows(
                self._client.search(
                    query, user_id=user_id or self.user_id, limit=self.search_limit
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Mem0 search failed ({type(exc).__name__}); skipping.")
            return ""
        memories = [str(r.get("memory", "")).strip() for r in rows if r.get("memory")]
        return "\n".join(f"- {m}" for m in memories if m)

    def add(
        self, user_message: str, assistant_reply: str, *, user_id: str | None = None
    ) -> None:
        """Persist the exchange. Silent on any failure."""
        if not self._client:
            return
        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_reply},
        ]
        try:
            self._client.add(messages, user_id=user_id or self.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Mem0 add failed ({type(exc).__name__}); not stored.")
