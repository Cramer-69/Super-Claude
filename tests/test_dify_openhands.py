import unittest
from unittest.mock import MagicMock, patch

from integrations.dify_client import DifyClient
from integrations.openhands_client import OpenHandsClient


def _response(payload, status_ok=True):
    response = MagicMock()
    response.json.return_value = payload
    if not status_ok:
        response.raise_for_status.side_effect = RuntimeError("500")
    return response


class DifyClientTests(unittest.TestCase):
    def _client(self, key="app-key", url="https://api.dify.ai/v1"):
        with patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.dify_key.return_value = key
            mock_settings.dify_api_url = url
            return DifyClient()

    def test_disabled_without_a_key(self):
        client = self._client(key=None)

        self.assertFalse(client.enabled)
        self.assertIsNone(client.chat("hi", user="u1"))
        self.assertEqual(client.conversations(user="u1"), [])

    def test_chat_posts_a_blocking_request_and_normalizes_the_answer(self):
        client = self._client()
        payload = {"answer": "hello there", "conversation_id": "c1", "id": "m1"}

        with patch("integrations.dify_client.httpx.post", return_value=_response(payload)) as mock_post, \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            result = client.chat("hi", user="u1")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.dify.ai/v1/chat-messages")
        self.assertEqual(kwargs["json"]["response_mode"], "blocking")
        self.assertEqual(kwargs["json"]["user"], "u1")
        self.assertNotIn("conversation_id", kwargs["json"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer app-key")
        self.assertEqual(
            result, {"answer": "hello there", "conversation_id": "c1", "message_id": "m1"}
        )

    def test_conversation_id_continues_an_existing_thread(self):
        client = self._client()

        with patch("integrations.dify_client.httpx.post", return_value=_response({"answer": "ok"})) as mock_post, \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            client.chat("hi", user="u1", conversation_id="c9")

        self.assertEqual(mock_post.call_args.kwargs["json"]["conversation_id"], "c9")

    def test_trailing_slash_in_base_url_does_not_double_up(self):
        client = self._client(url="https://dify.internal/v1/")

        with patch("integrations.dify_client.httpx.post", return_value=_response({"answer": "ok"})) as mock_post, \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            client.chat("hi", user="u1")

        self.assertEqual(mock_post.call_args.args[0], "https://dify.internal/v1/chat-messages")

    def test_request_failure_is_swallowed(self):
        client = self._client()

        with patch("integrations.dify_client.httpx.post", side_effect=RuntimeError("boom")), \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            self.assertIsNone(client.chat("hi", user="u1"))

    def test_http_error_status_is_swallowed(self):
        client = self._client()

        with patch("integrations.dify_client.httpx.post", return_value=_response({}, status_ok=False)), \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            self.assertIsNone(client.chat("hi", user="u1"))

    def test_oversized_answers_are_capped(self):
        client = self._client()

        with patch("integrations.dify_client.httpx.post", return_value=_response({"answer": "a" * 50_000})), \
             patch("integrations.dify_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            result = client.chat("hi", user="u1")

        self.assertEqual(len(result["answer"]), 20_000)


class OpenHandsClientTests(unittest.TestCase):
    def _client(self, url="https://openhands.internal", key=None):
        with patch("integrations.openhands_client.settings") as mock_settings:
            mock_settings.openhands_base_url.return_value = url
            mock_settings.openhands_key.return_value = key
            return OpenHandsClient()

    def test_disabled_without_a_base_url(self):
        client = self._client(url=None)

        self.assertFalse(client.enabled)
        self.assertIsNone(client.start_conversation("do a thing"))
        self.assertIsNone(client.get_conversation("c1"))
        self.assertEqual(client.list_conversations(), [])

    def test_start_conversation_posts_the_task(self):
        client = self._client(key="oh-key")

        with patch("integrations.openhands_client.httpx.request", return_value=_response({"conversation_id": "c1"})) as mock_request, \
             patch("integrations.openhands_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            result = client.start_conversation("fix the bug", repository="o/r")

        args, kwargs = mock_request.call_args
        self.assertEqual(args, ("POST", "https://openhands.internal/api/conversations"))
        self.assertEqual(kwargs["json"], {"initial_user_msg": "fix the bug", "repository": "o/r"})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer oh-key")
        self.assertEqual(result, {"conversation_id": "c1"})

    def test_api_key_header_is_omitted_when_unset(self):
        client = self._client()

        with patch("integrations.openhands_client.httpx.request", return_value=_response({})) as mock_request, \
             patch("integrations.openhands_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            client.get_conversation("c1")

        self.assertNotIn("Authorization", mock_request.call_args.kwargs["headers"])

    def test_list_unwraps_either_envelope(self):
        client = self._client()

        for payload in ({"results": [{"id": "c1"}]}, {"data": [{"id": "c1"}]}, [{"id": "c1"}]):
            with patch("integrations.openhands_client.httpx.request", return_value=_response(payload)), \
                 patch("integrations.openhands_client.settings") as mock_settings:
                mock_settings.plugin_http_timeout = 30.0
                self.assertEqual(client.list_conversations(), [{"id": "c1"}], payload)

    def test_request_failure_is_swallowed(self):
        client = self._client()

        with patch("integrations.openhands_client.httpx.request", side_effect=RuntimeError("boom")), \
             patch("integrations.openhands_client.settings") as mock_settings:
            mock_settings.plugin_http_timeout = 30.0
            self.assertIsNone(client.start_conversation("task"))
            self.assertEqual(client.list_conversations(), [])


if __name__ == "__main__":
    unittest.main()
