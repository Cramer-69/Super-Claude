import unittest
from unittest.mock import MagicMock, patch

from conductor.minimal import MinimalConductor


class MinimalConductorMemoryTests(unittest.TestCase):
    def _make_conductor(self):
        with patch("conductor.minimal._provider_for_keys", return_value=("openai", "gpt-4o-mini")), \
             patch("conductor.minimal.get_memory_store") as mock_get_store:
            mock_memory = MagicMock()
            mock_get_store.return_value = mock_memory
            conductor = MinimalConductor()
        return conductor, mock_memory

    def test_memories_are_folded_into_system_prompt(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = [{"memory": "likes coffee"}]

        with patch.object(conductor, "_call_openai", return_value="ok") as mock_call:
            conductor.chat("what do I like?", user_id="u1")

        mock_memory.search.assert_called_once_with("what do I like?", user_id="u1")
        system_prompt = mock_call.call_args.args[1]
        self.assertIn("likes coffee", system_prompt)

    def test_memory_not_written_on_provider_failure(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = []

        with patch.object(conductor, "_call_openai", side_effect=RuntimeError("boom")):
            result = conductor.chat("hello", user_id="u1")

        self.assertIn("boom", result["response"])
        mock_memory.add.assert_not_called()

    def test_memory_written_on_provider_success(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = []

        with patch.object(conductor, "_call_openai", return_value="hi there"):
            conductor.chat("hello", user_id="u1")

        mock_memory.add.assert_any_call("hello", user_id="u1", role="user")
        mock_memory.add.assert_any_call("hi there", user_id="u1", role="assistant")
        self.assertEqual(mock_memory.add.call_count, 2)

    def test_warns_when_mem0_enabled_without_explicit_user_id(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = []

        with patch("conductor.minimal.settings.mem0_enabled", True), \
             patch("conductor.minimal.logger") as mock_logger, \
             patch.object(conductor, "_call_openai", return_value="ok"):
            conductor.chat("hello")

        mock_logger.warning.assert_called_once()

    def test_no_warning_when_user_id_is_explicit(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = []

        with patch("conductor.minimal.settings.mem0_enabled", True), \
             patch("conductor.minimal.logger") as mock_logger, \
             patch.object(conductor, "_call_openai", return_value="ok"):
            conductor.chat("hello", user_id="u1")

        mock_logger.warning.assert_not_called()

    def test_no_warning_when_mem0_disabled(self):
        conductor, mock_memory = self._make_conductor()
        mock_memory.search.return_value = []

        with patch("conductor.minimal.settings.mem0_enabled", False), \
             patch("conductor.minimal.logger") as mock_logger, \
             patch.object(conductor, "_call_openai", return_value="ok"):
            conductor.chat("hello")

        mock_logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
