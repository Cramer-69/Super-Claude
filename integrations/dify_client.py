"""
Dify app backend (https://dify.ai).

Optional: active when DIFY_API_KEY is set. A Dify app key scopes the
client to exactly one published app, so the whole integration is "send a
message to that app and get its answer back".

Uses httpx (already a core dependency) rather than an SDK, so there is no
optional package to install. Same contract as the other plugins: inert
unless configured, and failures are logged, not raised.
"""

from typing import Any, Dict, List, Optional

import httpx

from config.settings import settings
from utils.logger import logger

MAX_ANSWER_CHARS = 20_000


class DifyClient:
    """Thin wrapper around Dify's /chat-messages endpoint."""

    def __init__(self) -> None:
        self.api_key = settings.dify_key()
        self.base_url = (settings.dify_api_url or "").rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        query: str,
        user: str,
        conversation_id: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a message to the Dify app and return its answer.

        `conversation_id` continues an existing Dify conversation; omit it
        to start a new one. Returns None on any failure.
        """
        if not self.enabled:
            return None

        payload: Dict[str, Any] = {
            "query": query,
            "user": user,
            "inputs": inputs or {},
            # Blocking mode keeps this a single request/response; the
            # streaming mode would need an SSE reader on the caller side.
            "response_mode": "blocking",
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            response = httpx.post(
                f"{self.base_url}/chat-messages",
                json=payload,
                headers=self._headers(),
                timeout=settings.plugin_http_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"Dify chat request failed: {type(e).__name__}: {e}")
            return None

        answer = str(data.get("answer") or "")[:MAX_ANSWER_CHARS]
        return {
            "answer": answer,
            "conversation_id": data.get("conversation_id"),
            "message_id": data.get("id") or data.get("message_id"),
        }

    def conversations(self, user: str, limit: int = 20) -> List[Dict[str, Any]]:
        """List the user's Dify conversations. Returns [] on any failure."""
        if not self.enabled:
            return []
        try:
            response = httpx.get(
                f"{self.base_url}/conversations",
                params={"user": user, "limit": limit},
                headers=self._headers(),
                timeout=settings.plugin_http_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"Dify conversations request failed: {type(e).__name__}: {e}")
            return []
        items = data.get("data") if isinstance(data, dict) else data
        return items if isinstance(items, list) else []


_dify_client: Optional[DifyClient] = None


def get_dify_client() -> DifyClient:
    """Lazily create and cache the process-wide DifyClient."""
    global _dify_client
    if _dify_client is None:
        _dify_client = DifyClient()
    return _dify_client
