import os
import unittest
from unittest.mock import MagicMock, patch

from conductor.minimal import MinimalConductor


class OpenAIResponsesTests(unittest.TestCase):
    def test_openai_uses_responses_api_with_bounded_client(self):
        with patch(
            "conductor.minimal._provider_for_keys",
            return_value=("openai", "gpt-5.6-terra"),
        ), patch("conductor.minimal.get_memory_store") as get_memory:
            get_memory.return_value = MagicMock()
            conductor = MinimalConductor()

        response = MagicMock(output_text="answer")
        client = MagicMock()
        client.responses.create.return_value = response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}), \
             patch("openai.OpenAI", return_value=client) as openai:
            text = conductor._call_openai("question", "instructions")

        openai.assert_called_once_with(
            api_key="sk-test",
            timeout=45.0,
            max_retries=1,
        )
        client.responses.create.assert_called_once_with(
            model="gpt-5.6-terra",
            instructions="instructions",
            input="question",
            max_output_tokens=800,
        )
        self.assertEqual(text.text, "answer")


if __name__ == "__main__":
    unittest.main()
