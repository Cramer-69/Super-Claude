import asyncio
import unittest
from unittest.mock import MagicMock, patch

from api.server import (
    ChatMessage,
    MAX_TRANSCRIPT_CHARS,
    _flatten_messages,
    _require_conductor_key,
    _startup_log_config,
    _stream_completion,
)
from fastapi import HTTPException


class FlattenMessagesTests(unittest.TestCase):
    def test_single_message_is_the_query(self):
        self.assertEqual(
            _flatten_messages([ChatMessage(role="user", content=" hello ")]), "hello"
        )

    def test_history_is_replayed_above_the_latest_message(self):
        result = _flatten_messages([
            ChatMessage(role="system", content="be terse"),
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="hello"),
            ChatMessage(role="user", content="what did I say?"),
        ])

        self.assertIn("system: be terse", result)
        self.assertIn("assistant: hello", result)
        self.assertTrue(result.endswith("what did I say?"))

    def test_empty_message_list_is_empty(self):
        self.assertEqual(_flatten_messages([]), "")

    def test_long_history_is_trimmed_from_the_front(self):
        history = [ChatMessage(role="user", content="x" * 1000) for _ in range(50)]
        history.append(ChatMessage(role="user", content="the latest question"))

        result = _flatten_messages(history)

        # The newest turns and the final message survive; the oldest don't.
        self.assertLess(len(result), MAX_TRANSCRIPT_CHARS + 2000)
        self.assertTrue(result.endswith("the latest question"))
        self.assertIn("...", result)


class RequireConductorKeyTests(unittest.TestCase):
    def test_open_when_no_key_is_configured(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            _require_conductor_key(None)  # must not raise

    def test_correct_bearer_token_is_accepted(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            _require_conductor_key("Bearer secret")
            _require_conductor_key("bearer secret")  # header casing varies

    def test_missing_or_wrong_token_is_rejected(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            for header in (None, "", "secret", "Bearer ", "Bearer wrong"):
                with self.assertRaises(HTTPException) as caught:
                    _require_conductor_key(header)
                self.assertEqual(caught.exception.status_code, 401)


class CloudStartupTests(unittest.TestCase):
    def test_cloud_startup_refuses_missing_conductor_key(self):
        with patch("api.server._is_cloud", return_value=True), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            mock_settings.configured_providers.return_value = ["openai"]

            with self.assertRaisesRegex(RuntimeError, "CONDUCTOR_API_KEY"):
                asyncio.run(_startup_log_config())

    def test_cloud_startup_accepts_conductor_key(self):
        with patch("api.server._is_cloud", return_value=True), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            mock_settings.configured_providers.return_value = ["openai"]

            asyncio.run(_startup_log_config())


class StreamCompletionTests(unittest.TestCase):
    def test_stream_is_well_formed_sse_ending_in_done(self):
        chunks = list(_stream_completion(lambda: "hello world", "conductor", "chatcmpl-1"))

        self.assertTrue(all(c.startswith("data: ") for c in chunks))
        self.assertEqual(chunks[-1], "data: [DONE]\n\n")
        self.assertIn('"role": "assistant"', chunks[0])
        self.assertIn('"finish_reason": "stop"', chunks[-2])

    def test_first_chunk_is_emitted_before_generation_runs(self):
        # The point of deferring generation into the iterator: the client
        # gets headers and an opening event immediately, so a slow provider
        # can't stall the response into an idle timeout.
        called = []
        stream = _stream_completion(
            lambda: called.append("generate") or "done", "conductor", "chatcmpl-1"
        )

        first = next(stream)

        self.assertIn('"role": "assistant"', first)
        self.assertEqual(called, [])  # generation hasn't started yet

        list(stream)
        self.assertEqual(called, ["generate"])

    def test_generation_failure_is_reported_inside_the_stream(self):
        def explode():
            raise RuntimeError("provider exploded")

        chunks = list(_stream_completion(explode, "conductor", "chatcmpl-1"))

        self.assertIn("upstream provider request failed", "".join(chunks))
        self.assertNotIn("provider exploded", "".join(chunks))
        self.assertEqual(chunks[-1], "data: [DONE]\n\n")

    def test_whole_answer_survives_chunking(self):
        import json

        text = "x" * 500
        chunks = list(_stream_completion(lambda: text, "conductor", "chatcmpl-1"))
        content = ""
        for chunk in chunks[:-1]:
            payload = json.loads(chunk[len("data: "):])
            content += payload["choices"][0]["delta"].get("content", "")

        self.assertEqual(content, text)


class ChatCompletionsEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from api.server import app

        return TestClient(app)

    def test_completion_has_openai_shape(self):
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "the answer", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={"model": "conductor", "messages": [{"role": "user", "content": "hi"}]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["object"], "chat.completion")
        self.assertEqual(body["choices"][0]["message"]["content"], "the answer")
        self.assertEqual(body["choices"][0]["finish_reason"], "stop")
        self.assertTrue(body["id"].startswith("chatcmpl-"))
        conductor.chat.assert_called_once_with(query="hi", user_id=None, url_source="hi")

    def test_completion_includes_structured_and_visible_sources(self):
        conductor = MagicMock()
        conductor.chat.return_value = {
            "response": "the answer",
            "sources": [{
                "platform": "web",
                "title": "Official models",
                "url": "https://platform.openai.com/docs/models",
            }],
        }

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "search the web"}]},
            )

        body = response.json()
        content = body["choices"][0]["message"]["content"]
        self.assertEqual(body["sources"], conductor.chat.return_value["sources"])
        self.assertIn("Sources:", content)
        self.assertIn("[Official models](https://platform.openai.com/docs/models)", content)

    def test_sampling_parameters_are_accepted_and_ignored(self):
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "ok", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "frequency_penalty": 1,
                },
            )

        self.assertEqual(response.status_code, 200)

    def test_user_is_passed_through_as_the_memory_scope(self):
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "ok", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            self._client().post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "user": "u42"},
            )

        conductor.chat.assert_called_once_with(query="hi", user_id="u42", url_source="hi")

    def test_empty_messages_are_rejected(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post("/v1/chat/completions", json={"messages": []})

        self.assertEqual(response.status_code, 400)

    def test_streaming_returns_sse(self):
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "streamed", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn("streamed", response.text)
        self.assertTrue(response.text.rstrip().endswith("data: [DONE]"))

    def test_streaming_appends_visible_sources(self):
        conductor = MagicMock()
        conductor.chat.return_value = {
            "response": "streamed",
            "sources": [{"title": "Example", "url": "https://example.com"}],
        }

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "search the web"}],
                    "stream": True,
                },
            )

        self.assertIn("Sources:", response.text)
        self.assertIn("https://example.com", response.text)

    def test_only_the_latest_message_drives_url_auto_fetch(self):
        # History is replayed for the model, but a link from a turn already
        # answered must not be re-scraped every round.
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "ok", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            self._client().post(
                "/v1/chat/completions",
                json={"messages": [
                    {"role": "user", "content": "read https://old-one.com"},
                    {"role": "assistant", "content": "done"},
                    {"role": "user", "content": "now read https://new-one.com"},
                ]},
            )

        kwargs = conductor.chat.call_args.kwargs
        self.assertEqual(kwargs["url_source"], "now read https://new-one.com")
        self.assertIn("https://old-one.com", kwargs["query"])  # still visible as text

    def test_response_reports_the_served_model_not_the_requested_one(self):
        # The conductor routes to whichever provider is configured, so
        # echoing "gpt-4" back would misattribute the answer.
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "ok", "sources": []}

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            )

        self.assertEqual(response.json()["model"], "conductor")

    def test_streaming_provider_failure_is_returned_as_gateway_error(self):
        conductor = MagicMock()
        conductor.chat.side_effect = RuntimeError("provider exploded")

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Upstream provider request failed")

    def test_non_stream_provider_failures_preserve_gateway_status(self):
        cases = [
            ("RateLimitError", 429, 429),
            ("APITimeoutError", None, 504),
            ("ProviderError", None, 502),
        ]
        for class_name, provider_status, expected in cases:
            error_type = type(class_name, (RuntimeError,), {})
            error = error_type("provider failed")
            if provider_status is not None:
                error.status_code = provider_status
            conductor = MagicMock()
            conductor.chat.side_effect = error

            with self.subTest(class_name=class_name), \
                 patch("api.server.get_conductor", return_value=conductor), \
                 patch("api.server.settings") as mock_settings:
                mock_settings.conductor_key.return_value = None
                response = self._client().post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                )

            self.assertEqual(response.status_code, expected)

    def test_models_endpoint_lists_the_conductor(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().get("/v1/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["id"], "conductor")

    def test_endpoints_are_locked_when_a_key_is_configured(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            client = self._client()
            unauthorized = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            models = client.get("/v1/models")

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(models.status_code, 401)

    def test_liveness_is_process_only_and_readiness_is_sanitized(self):
        memory = MagicMock(enabled=True, backend="platform")
        firecrawl = MagicMock(enabled=True)
        with patch("api.server.settings") as mock_settings, \
             patch("api.server.get_memory_store", return_value=memory), \
             patch("api.server.get_firecrawl_client", return_value=firecrawl):
            mock_settings.conductor_primary_provider = "openai"
            mock_settings.configured_providers.return_value = ["openai"]
            mock_settings.conductor_key.return_value = "secret"
            mock_settings.mem0_configured.return_value = True
            mock_settings.firecrawl_configured.return_value = True
            client = self._client()
            live = client.get("/health/live")
            ready = client.get("/health/ready")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ready")
        self.assertNotIn("secret", ready.text)

    def test_readiness_is_503_when_required_service_is_missing(self):
        memory = MagicMock(enabled=False, backend=None)
        firecrawl = MagicMock(enabled=False)
        with patch("api.server.settings") as mock_settings, \
             patch("api.server.get_memory_store", return_value=memory), \
             patch("api.server.get_firecrawl_client", return_value=firecrawl):
            mock_settings.conductor_primary_provider = "openai"
            mock_settings.configured_providers.return_value = ["openai"]
            mock_settings.conductor_key.return_value = "secret"
            mock_settings.mem0_configured.return_value = True
            mock_settings.firecrawl_configured.return_value = True
            response = self._client().get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "not_ready")


class LegacyChatEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from api.server import app

        return TestClient(app)

    def test_legacy_chat_is_locked_when_a_key_is_configured(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            response = self._client().post("/api/chat", json={"query": "hello"})

        self.assertEqual(response.status_code, 401)

    def test_voice_credit_routes_are_locked_when_a_key_is_configured(self):
        with patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = "secret"
            client = self._client()
            voice_chat = client.post(
                "/api/voice-chat",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )
            transcribe = client.post(
                "/api/transcribe",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )
            synthesize = client.post("/api/synthesize", params={"text": "hello"})

        self.assertEqual(voice_chat.status_code, 401)
        self.assertEqual(transcribe.status_code, 401)
        self.assertEqual(synthesize.status_code, 401)

    def test_legacy_chat_maps_provider_errors_without_exposing_details(self):
        conductor = MagicMock()
        conductor.chat.side_effect = RuntimeError("private upstream detail")

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings:
            mock_settings.conductor_key.return_value = None
            response = self._client().post("/api/chat", json={"query": "hello"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Upstream provider request failed")
        self.assertNotIn("private upstream detail", response.text)

    def test_legacy_chat_never_logs_the_prompt(self):
        conductor = MagicMock()
        conductor.chat.return_value = {"response": "ok", "sources": [], "usage": {}}
        prompt = "private-plan-should-never-enter-logs"

        with patch("api.server.get_conductor", return_value=conductor), \
             patch("api.server.settings") as mock_settings, \
             patch("api.server.logger") as mock_logger:
            mock_settings.conductor_key.return_value = None
            response = self._client().post("/api/chat", json={"query": prompt})

        self.assertEqual(response.status_code, 200)
        rendered_calls = repr(mock_logger.method_calls)
        self.assertNotIn(prompt, rendered_calls)


if __name__ == "__main__":
    unittest.main()
