import unittest
from unittest.mock import MagicMock, patch

from conductor.minimal import MinimalConductor


class MinimalConductorWebContextTests(unittest.TestCase):
    def _make_conductor(self):
        with (
            patch(
                "conductor.minimal._provider_for_keys",
                return_value=("openai", "gpt-4o-mini"),
            ),
            patch("conductor.minimal.get_memory_store") as mock_get_store,
        ):
            mock_memory = MagicMock()
            mock_memory.search.return_value = []
            mock_get_store.return_value = mock_memory
            conductor = MinimalConductor()
        return conductor

    def test_fetched_page_is_folded_into_system_prompt_and_sources(self):
        conductor = self._make_conductor()
        page = {
            "url": "https://example.com",
            "title": "Example",
            "content": "the page body",
        }

        with patch("conductor.minimal.web_context_for_query", return_value=[page]), \
             patch.object(conductor, "_call_openai", return_value="ok") as mock_call:
            result = conductor.chat("summarize https://example.com", user_id="u1")

        system_prompt = mock_call.call_args.args[1]
        self.assertIn("the page body", system_prompt)
        self.assertIn("untrusted", system_prompt)
        self.assertEqual(
            result["sources"],
            [{"platform": "web", "title": "Example", "url": "https://example.com"}],
        )
        self.assertEqual(result["context_used"], len("the page body"))

    def test_untitled_page_falls_back_to_its_url_as_the_source_title(self):
        conductor = self._make_conductor()
        page = {"url": "https://example.com/a", "title": "", "content": "body"}

        with patch("conductor.minimal.web_context_for_query", return_value=[page]), \
             patch.object(conductor, "_call_openai", return_value="ok"):
            result = conductor.chat("summarize https://example.com/a", user_id="u1")

        self.assertEqual(result["sources"][0]["title"], "https://example.com/a")

    def test_no_web_context_leaves_prompt_and_sources_untouched(self):
        conductor = self._make_conductor()

        with patch("conductor.minimal.web_context_for_query", return_value=[]), \
             patch.object(conductor, "_call_openai", return_value="ok") as mock_call:
            result = conductor.chat("hello", user_id="u1")

        self.assertNotIn("untrusted", mock_call.call_args.args[1])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["context_used"], 0)

    def test_explicit_web_request_searches_once_with_three_result_cap(self):
        conductor = self._make_conductor()
        result_page = {
            "url": "https://platform.openai.com/docs/models",
            "title": "Models",
            "content": "Current official model list",
        }
        firecrawl = MagicMock()
        firecrawl.enabled = True
        firecrawl.search.return_value = [result_page]

        with patch("conductor.minimal.web_context_for_query", return_value=[]), \
             patch("conductor.minimal.get_firecrawl_client", return_value=firecrawl), \
             patch.object(conductor, "_call_openai", return_value="ok") as mock_call:
            result = conductor.chat(
                "Search the web for current official OpenAI models",
                user_id="u1",
            )

        firecrawl.search.assert_called_once_with(
            "Search the web for current official OpenAI models", limit=3
        )
        self.assertIn("Current official model list", mock_call.call_args.args[1])
        self.assertEqual(result["sources"][0]["url"], result_page["url"])

    def test_normal_chat_does_not_spend_a_search_credit(self):
        conductor = self._make_conductor()
        firecrawl = MagicMock()
        firecrawl.enabled = True

        with patch("conductor.minimal.web_context_for_query", return_value=[]), \
             patch("conductor.minimal.get_firecrawl_client", return_value=firecrawl), \
             patch.object(conductor, "_call_openai", return_value="ok"):
            conductor.chat("hello", user_id="u1")

        firecrawl.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
