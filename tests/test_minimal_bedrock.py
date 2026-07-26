import os
import unittest
from unittest.mock import patch

from conductor.minimal import _provider_for_keys


class MinimalProviderPrecedenceTests(unittest.TestCase):
    def test_prefers_anthropic_direct_over_bedrock(self):
        # Claude's "home field" (the Anthropic API) wins even when AWS
        # credentials/region are present, so having AWS configured does not
        # silently route Claude through Bedrock.
        env = {
            "AWS_REGION": "us-east-1",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }
        with patch.dict(os.environ, env, clear=True):
            provider, model = _provider_for_keys()

        self.assertEqual(provider, "anthropic")
        self.assertEqual(model, "claude-3-5-haiku-latest")

    def test_prefers_xai_direct_over_bedrock(self):
        env = {
            "AWS_REGION": "us-east-1",
            "XAI_API_KEY": "xai-test",
        }
        with patch.dict(os.environ, env, clear=True):
            provider, model = _provider_for_keys()

        self.assertEqual(provider, "xai")
        self.assertEqual(model, "grok-2-latest")

    def test_bedrock_only_when_no_direct_key(self):
        # Bedrock is the last-resort provider: used only when no direct
        # provider key is configured.
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
