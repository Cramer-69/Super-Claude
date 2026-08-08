import unittest
from unittest.mock import MagicMock, patch

from integrations.livekit_client import LiveKitClient, is_valid_name


class ValidNameTests(unittest.TestCase):
    def test_accepts_ordinary_identities_and_rooms(self):
        for name in ("user-1", "ara_room", "u:42", "a.b-c"):
            self.assertTrue(is_valid_name(name), name)

    def test_rejects_empty_oversized_and_unsafe_names(self):
        for name in ("", " ", "a" * 129, "room name", "room/../admin", "ro\nom", "üser"):
            self.assertFalse(is_valid_name(name), repr(name))


class LiveKitClientTests(unittest.TestCase):
    def _client(self, credentials=("wss://x.livekit.cloud", "key", "secret"), available=True):
        with patch("integrations.livekit_client.LIVEKIT_AVAILABLE", available), \
             patch("integrations.livekit_client.settings") as mock_settings:
            mock_settings.livekit_credentials.return_value = credentials
            return LiveKitClient()

    def test_disabled_without_credentials(self):
        client = self._client(credentials=None)

        self.assertFalse(client.enabled)
        self.assertIsNone(client.access_token("u1", "r1"))

    def test_disabled_without_the_sdk(self):
        self.assertFalse(self._client(available=False).enabled)

    def test_mints_a_narrow_join_grant(self):
        client = self._client()
        access_token = MagicMock()
        access_token.with_identity.return_value = access_token
        access_token.with_grants.return_value = access_token
        access_token.with_ttl.return_value = access_token
        access_token.to_jwt.return_value = "jwt-value"

        sdk = MagicMock()
        sdk.AccessToken.return_value = access_token

        with patch("integrations.livekit_client.livekit_api", sdk), \
             patch("integrations.livekit_client.settings") as mock_settings:
            mock_settings.livekit_token_ttl_seconds = 600
            grant = client.access_token("u1", "r1")

        sdk.AccessToken.assert_called_once_with("key", "secret")
        access_token.with_identity.assert_called_once_with("u1")
        video_grants = sdk.VideoGrants.call_args.kwargs
        self.assertEqual(video_grants["room"], "r1")
        self.assertTrue(video_grants["room_join"])
        # No admin/create rights: a leaked browser token can't reshape the
        # deployment, only join the one room it names.
        self.assertNotIn("room_admin", video_grants)
        self.assertNotIn("room_create", video_grants)
        self.assertEqual(
            grant,
            {
                "token": "jwt-value",
                "url": "wss://x.livekit.cloud",
                "room": "r1",
                "identity": "u1",
                "expires_in": 600,
            },
        )

    def test_invalid_names_are_refused_before_signing(self):
        client = self._client()
        sdk = MagicMock()

        with patch("integrations.livekit_client.livekit_api", sdk):
            self.assertIsNone(client.access_token("bad identity", "r1"))
            self.assertIsNone(client.access_token("u1", "../admin"))

        sdk.AccessToken.assert_not_called()

    def test_signing_failure_is_swallowed(self):
        client = self._client()
        sdk = MagicMock()
        sdk.AccessToken.side_effect = RuntimeError("boom")

        with patch("integrations.livekit_client.livekit_api", sdk), \
             patch("integrations.livekit_client.settings") as mock_settings:
            mock_settings.livekit_token_ttl_seconds = 600
            self.assertIsNone(client.access_token("u1", "r1"))


if __name__ == "__main__":
    unittest.main()
