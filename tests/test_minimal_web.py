import unittest
from unittest.mock import MagicMock, patch

from conductor.minimal import MinimalConductor


class MinimalConductorWebContextTests(unittest.TestCase):
    def _make_conductor(self):
        with patch("conductor.minimal._provider_for_keys", return_value=("openai", "gpt-4o-mini")), \
             patch("conductor.minimal.get_memory_store") as mock_get_store:
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


if __name__ == "__main__":
    unittest.main()
