import os
import unittest
from unittest.mock import patch

from conductor.minimal import _provider_for_keys, _use_key


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

    def test_env_placeholder_falls_back_to_settings_value(self):
        # A placeholder left in the live environment (e.g. an injected
        # default) must not shadow a real key available via settings/.env —
        # each source is checked for a placeholder independently.
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "your_anthropic_api_key_here"}, clear=True):
            key = _use_key("ANTHROPIC_API_KEY", "sk-ant-from-dotenv")
            # The downstream _call_<provider> methods read os.environ[...]
            # directly, so the real value must overwrite the placeholder
            # while still inside the patched environment.
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-ant-from-dotenv")

        self.assertEqual(key, "sk-ant-from-dotenv")

    def test_placeholder_in_both_sources_is_unconfigured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "your_anthropic_api_key_here"}, clear=True):
            key = _use_key("ANTHROPIC_API_KEY", "your_anthropic_api_key_here")

        self.assertIsNone(key)


if __name__ == "__main__":
    unittest.main()
