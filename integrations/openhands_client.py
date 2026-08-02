"""
OpenHands agent runtime (https://github.com/All-Hands-AI/OpenHands).

Optional: active when OPENHANDS_API_URL points at a running OpenHands
server (self-hosted or cloud). Lets the conductor hand a coding task to
an OpenHands conversation and read its state back.

Targets OpenHands' `/api/conversations` REST surface. That API is still
moving, so responses are passed through as-is rather than reshaped into a
fixed schema — callers get whatever the server returned, and a failure
returns None instead of raising.
"""

from typing import Any, Dict, List, Optional

import httpx

from config.settings import settings
from utils.logger import logger


class OpenHandsClient:
    """Thin wrapper around the OpenHands conversations API."""

    def __init__(self) -> None:
        base = settings.openhands_base_url()
        self.base_url = base.rstrip("/") if base else None
        self.api_key = settings.openhands_key()

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=settings.plugin_http_timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(
                f"OpenHands {method} {path} failed: {type(e).__name__}: {e}"
            )
            return None

    def start_conversation(
        self,
        task: str,
        repository: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Start a conversation with an initial task. None on failure."""
        payload: Dict[str, Any] = {"initial_user_msg": task}
        if repository:
            payload["repository"] = repository
        result = self._request("POST", "/api/conversations", json=payload)
        return result if isinstance(result, dict) else None

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Read one conversation's state. None on failure."""
        result = self._request("GET", f"/api/conversations/{conversation_id}")
        return result if isinstance(result, dict) else None

    def list_conversations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent conversations. [] on failure."""
        result = self._request("GET", "/api/conversations", params={"limit": limit})
        if isinstance(result, dict):
            result = result.get("results") or result.get("data")
        return result if isinstance(result, list) else []


_openhands_client: Optional[OpenHandsClient] = None


def get_openhands_client() -> OpenHandsClient:
    """Lazily create and cache the process-wide OpenHandsClient."""
    global _openhands_client
    if _openhands_client is None:
        _openhands_client = OpenHandsClient()
    return _openhands_client
