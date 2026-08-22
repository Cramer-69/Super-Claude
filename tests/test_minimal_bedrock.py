import os
import unittest
from unittest.mock import MagicMock, patch

from conductor.minimal import _provider_for_keys, _use_key


class MinimalProviderSelectionTests(unittest.TestCase):
    def test_explicit_openai_primary_wins_when_other_keys_exist(self):
        mock_settings = MagicMock()
        mock_settings.conductor_primary_provider = "openai"
        mock_settings.openai_api_key = "sk-openai"
        mock_settings.openai_model = "gpt-5.6-terra"
        mock_settings.anthropic_api_key = "sk-ant-test"
        mock_settings.xai_api_key = "xai-test"

        with patch.dict(os.environ, {}, clear=True), \
             patch("conductor.minimal.settings", mock_settings):
            provider, model = _provider_for_keys()

        self.assertEqual((provider, model), ("openai", "gpt-5.6-terra"))

    def test_missing_primary_key_does_not_implicitly_switch_provider(self):
        mock_settings = MagicMock()
        mock_settings.conductor_primary_provider = "openai"
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = "sk-ant-test"

        with patch.dict(os.environ, {}, clear=True), \
             patch("conductor.minimal.settings", mock_settings):
            provider, model = _provider_for_keys()

        self.assertEqual((provider, model), ("none", "minimal"))

    def test_bedrock_is_selected_only_when_explicitly_primary_and_enabled(self):
        mock_settings = MagicMock()
        mock_settings.conductor_primary_provider = "bedrock"
        mock_settings.bedrock_configured.return_value = True
        mock_settings.bedrock_model.return_value = "bedrock-model"

        with patch.dict(os.environ, {}, clear=True), \
             patch("conductor.minimal.settings", mock_settings):
            provider, model = _provider_for_keys()

        self.assertEqual((provider, model), ("bedrock", "bedrock-model"))

    def test_env_placeholder_falls_back_to_settings_value(self):
        # A placeholder left in the live environment (e.g. an injected
        # default) must not shadow a real key available via settings/.env —
        # each source is checked for a placeholder independently.
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "your_anthropic_api_key_here"},
            clear=True,
        ):
            key = _use_key("ANTHROPIC_API_KEY", "sk-ant-from-dotenv")
            # The downstream _call_<provider> methods read os.environ[...]
            # directly, so the real value must overwrite the placeholder
            # while still inside the patched environment.
            self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "sk-ant-from-dotenv")

        self.assertEqual(key, "sk-ant-from-dotenv")

    def test_placeholder_in_both_sources_is_unconfigured(self):
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "your_anthropic_api_key_here"},
            clear=True,
        ):
            key = _use_key("ANTHROPIC_API_KEY", "your_anthropic_api_key_here")

        self.assertIsNone(key)


if __name__ == "__main__":
    unittest.main()
