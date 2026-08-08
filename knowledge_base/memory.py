"""
Durable, cross-session memory backed by mem0 (https://github.com/mem0ai/mem0).

Optional, with two backends:

  * "platform" — the hosted mem0 API, used when MEM0_API_KEY is set.
    Nothing else is required; mem0 runs the LLM/embedder server-side.
  * "oss"      — the self-hosted client, used when MEM0_ENABLED=true
    without a platform key. Needs an OpenAI key for mem0's own
    LLM/embedder calls, and stores vectors on the local disk.

Any failure here must never break a chat request, so every public method
swallows errors and logs instead of raising.
"""

from typing import Any, Dict, List, Optional

from config.settings import settings
from utils.logger import logger

try:
    from mem0 import Memory
except Exception:
    # Broad on purpose: an installed-but-broken mem0 (missing native deps,
    # incompatible runtime, etc.) must disable memory, not crash app startup.
    Memory = None

try:
    from mem0 import MemoryClient
except Exception:
    MemoryClient = None

MEM0_AVAILABLE = Memory is not None or MemoryClient is not None

MAX_MEMORY_TEXT_LENGTH = 500


def sanitize_memory_text(text: str) -> str:
    """Collapse whitespace/newlines and cap length before a stored memory is
    interpolated into a prompt, so it can't break out of the surrounding
    structure (bullet list, context block header, etc.)."""
    collapsed = " ".join(text.split())
    return collapsed[:MAX_MEMORY_TEXT_LENGTH]


class MemoryStore:
    """Thin wrapper around mem0's Memory client."""

    def __init__(self) -> None:
        self.client = None
        self.backend: Optional[str] = None
        if not MEM0_AVAILABLE:
            logger.info("mem0 not installed; durable memory disabled.")
            return
        if not settings.mem0_configured():
            return

        platform_key = settings.mem0_platform_key()
        try:
            if platform_key:
                # Never silently fall back to the OSS client here: the user
                # opted into the hosted platform, and the OSS backend spends
                # OpenAI credits and writes vectors to local disk instead.
                if MemoryClient is None:
                    logger.warning(
                        "MEM0_API_KEY is set but mem0's MemoryClient could not "
                        "be imported; durable memory disabled. Upgrade mem0ai "
                        "or unset MEM0_API_KEY to use the OSS backend."
                    )
                    return
                self.client = MemoryClient(api_key=platform_key)
                self.backend = "platform"
            elif Memory is not None:
                self.client = Memory()
                self.backend = "oss"
            else:
                logger.warning(
                    "mem0 is configured but no usable client class was "
                    "importable; durable memory disabled."
                )
        except Exception as e:
            logger.warning(f"Could not initialize mem0 client: {e}")
            self.client = None
            self.backend = None
        else:
            if self.client is not None:
                logger.info(f"mem0 durable memory enabled (backend={self.backend}).")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def add(self, text: str, user_id: str, role: str = "user") -> None:
        if not self.enabled:
            return
        try:
            self.client.add([{"role": role, "content": text}], user_id=user_id)
        except Exception as e:
            logger.warning(f"mem0 add() failed: {e}")

    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            result = self.client.search(query, user_id=user_id, limit=limit)
            items = result.get("results", []) if isinstance(result, dict) else list(result)
            return [item if isinstance(item, dict) else {"memory": str(item)} for item in items]
        except Exception as e:
            logger.warning(f"mem0 search() failed: {e}")
            return []


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    """Lazily create and cache the process-wide MemoryStore."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
