"""The plugin routes spend money or act with the server's credentials, so
they must honor CONDUCTOR_API_KEY exactly like the /v1 endpoints do."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.server import app

PROTECTED_ROUTES = [
    ("POST", "/api/web/scrape", {"url": "https://example.com"}),
    ("POST", "/api/web/search", {"query": "hi"}),
    ("POST", "/api/livekit/token", {"identity": "u1", "room": "r1"}),
    ("POST", "/api/dify/chat", {"query": "hi", "user": "u1"}),
    ("POST", "/api/openhands/conversations", {"task": "do it"}),
    ("GET", "/api/openhands/conversations/c1", None),
]


class PluginRouteAuthTests(unittest.TestCase):
    def _call(self, method, path, payload, headers=None):
        client = TestClient(app)
        if method == "GET":
            return client.get(path, headers=headers or {})
        return client.post(path, json=payload, headers=headers or {})

    def test_every_plugin_route_401s_without_the_key(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            for method, path, payload in PROTECTED_ROUTES:
                response = self._call(method, path, payload)
                self.assertEqual(response.status_code, 401, f"{method} {path}")

    def test_wrong_key_is_rejected(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            for method, path, payload in PROTECTED_ROUTES:
                response = self._call(
                    method, path, payload, headers={"Authorization": "Bearer wrong"}
                )
                self.assertEqual(response.status_code, 401, f"{method} {path}")

    def test_auth_runs_before_the_plugin_client_is_touched(self):
        # A rejected caller must not reach the SDK — otherwise the 401 would
        # still have cost a Firecrawl credit or minted a LiveKit token.
        firecrawl = MagicMock()
        livekit = MagicMock()

        with patch("api.server.settings") as mock_settings, \
             patch("api.server.get_firecrawl_client", return_value=firecrawl), \
             patch("api.server.get_livekit_client", return_value=livekit):
            mock_settings.conductor_key.return_value = "secret"
            self._call("POST", "/api/web/scrape", {"url": "https://example.com"})
            self._call("POST", "/api/livekit/token", {"identity": "u1", "room": "r1"})

        firecrawl.scrape.assert_not_called()
        livekit.access_token.assert_not_called()

    def test_correct_key_reaches_the_handler(self):
        firecrawl = MagicMock()
        firecrawl.enabled = True
        firecrawl.scrape.return_value = {
            "url": "https://example.com",
            "title": "Example",
            "content": "body",
        }

        with patch("api.server.settings") as mock_settings, \
             patch("api.server.get_firecrawl_client", return_value=firecrawl):
            mock_settings.conductor_key.return_value = "secret"
            response = self._call(
                "POST",
                "/api/web/scrape",
                {"url": "https://example.com"},
                headers={"Authorization": "Bearer secret"},
            )

        self.assertEqual(response.status_code, 200)
        firecrawl.scrape.assert_called_once_with("https://example.com")

    def test_routes_stay_open_when_no_key_is_configured(self):
        # Unset means open, matching /api/chat and the existing web UI: an
        # unconfigured plugin answers 503, not 401.
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            mock_settings.firecrawl_configured.return_value = False
            response = self._call("POST", "/api/dify/chat", {"query": "hi", "user": "u1"})

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
