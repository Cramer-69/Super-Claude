"""
Realtime voice rooms via LiveKit (https://livekit.io).

Optional: only active when the `livekit-api` package is installed and
LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are all set. Minting a
join token is the one operation the web/voice client needs from the
server; the media path itself goes browser <-> LiveKit directly.

Same contract as the other plugins: inert unless configured, and every
public method logs and returns a falsy value instead of raising.
"""

import re
from typing import Any, Dict, Optional

from config.settings import settings
from utils.logger import logger

try:
    from livekit import api as livekit_api
    LIVEKIT_AVAILABLE = True
except Exception:
    # Broad on purpose: an installed-but-broken SDK must disable voice
    # rooms, not crash app startup.
    livekit_api = None
    LIVEKIT_AVAILABLE = False

# LiveKit identities and room names end up in JWT claims and room URLs.
# Keep them to characters that can't confuse either.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def is_valid_name(value: str) -> bool:
    """Whether `value` is usable as a room name or participant identity."""
    return bool(value and _SAFE_NAME.match(value))


class LiveKitClient:
    """Mints LiveKit access tokens for the browser client."""

    def __init__(self) -> None:
        self.url: Optional[str] = None
        self._key: Optional[str] = None
        self._secret: Optional[str] = None
        if not LIVEKIT_AVAILABLE:
            logger.info("livekit-api not installed; voice rooms disabled.")
            return
        credentials = settings.livekit_credentials()
        if not credentials:
            return
        self.url, self._key, self._secret = credentials

    @property
    def enabled(self) -> bool:
        return bool(self.url and self._key and self._secret)

    def access_token(
        self,
        identity: str,
        room: str,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mint a room-join token. Returns None on any failure.

        The grant is deliberately narrow: join the one named room, publish
        and subscribe there, nothing else. No room-admin or room-create
        rights — a leaked browser token then can't reshape the deployment.
        """
        if not self.enabled:
            return None
        if not is_valid_name(identity) or not is_valid_name(room):
            logger.warning("Refusing to mint a LiveKit token for an invalid identity/room")
            return None

        ttl = ttl_seconds or settings.livekit_token_ttl_seconds
        try:
            from datetime import timedelta

            grants = livekit_api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
            token = (
                livekit_api.AccessToken(self._key, self._secret)
                .with_identity(identity)
                .with_grants(grants)
                .with_ttl(timedelta(seconds=ttl))
                .to_jwt()
            )
        except Exception as e:
            logger.warning(f"Could not mint LiveKit token: {e}")
            return None

        return {
            "token": token,
            "url": self.url,
            "room": room,
            "identity": identity,
            "expires_in": ttl,
        }


_livekit_client: Optional[LiveKitClient] = None


def get_livekit_client() -> LiveKitClient:
    """Lazily create and cache the process-wide LiveKitClient."""
    global _livekit_client
    if _livekit_client is None:
        _livekit_client = LiveKitClient()
    return _livekit_client
