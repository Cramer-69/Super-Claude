import os
import unittest
from unittest.mock import patch

from conductor.minimal import _provider_for_keys


class MinimalBedrockProviderTests(unittest.TestCase):
    def test_prefers_bedrock_when_region_is_set(self):
        env = {
            "AWS_REGION": "us-east-1",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=True):
            provider, model = _provider_for_keys()

        self.assertEqual(provider, "bedrock")
        self.assertEqual(model, "anthropic.claude-3-5-haiku-20241022-v1:0")

    def test_uses_default_region_variable_for_bedrock(self):
        env = {
            "AWS_DEFAULT_REGION": "us-west-2",
            "AWS_BEDROCK_MODEL_ID": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        }
        with patch.dict(os.environ, env, clear=True):
            provider, model = _provider_for_keys()

        self.assertEqual(provider, "bedrock")
        self.assertEqual(model, "anthropic.claude-3-5-sonnet-20241022-v2:0")


if __name__ == "__main__":
    unittest.main()
