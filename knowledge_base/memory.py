"""
Durable, cross-session memory backed by mem0 (https://github.com/mem0ai/mem0).

Optional: only active when the `mem0ai` package is installed and an
OpenAI key is configured (mem0's default LLM/embedder). Any failure here
must never break a chat request, so every public method swallows errors
and logs instead of raising.
"""

from typing import Any, Dict, List, Optional

from config.settings import settings
from utils.logger import logger

try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    Memory = None
    MEM0_AVAILABLE = False


class MemoryStore:
    """Thin wrapper around mem0's Memory client."""

    def __init__(self) -> None:
        self.client = None
        if not MEM0_AVAILABLE:
            logger.info("mem0 not installed; durable memory disabled.")
            return
        if not settings.mem0_enabled:
            return
        try:
            self.client = Memory()
        except Exception as e:
            logger.warning(f"Could not initialize mem0 Memory client: {e}")
            self.client = None

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
            return result.get("results", []) if isinstance(result, dict) else list(result)
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
