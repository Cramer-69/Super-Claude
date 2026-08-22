import os
import unittest
from unittest.mock import patch

from config.settings import Settings


class Mem0SettingsTests(unittest.TestCase):
    def test_off_by_default(self):
        settings = Settings(_env_file=None)

        self.assertFalse(settings.mem0_configured())
        self.assertIsNone(settings.mem0_platform_key())

    def test_platform_key_alone_enables_memory(self):
        settings = Settings(_env_file=None, mem0_api_key="m0-real")

        self.assertTrue(settings.mem0_configured())
        self.assertEqual(settings.mem0_platform_key(), "m0-real")

    def test_placeholder_key_is_ignored(self):
        settings = Settings(_env_file=None, mem0_api_key="your_mem0_api_key_here")

        self.assertFalse(settings.mem0_configured())
        self.assertIsNone(settings.mem0_platform_key())

    def test_whitespace_only_key_is_not_a_key(self):
        settings = Settings(_env_file=None, mem0_api_key="   ")

        self.assertFalse(settings.mem0_configured())
        self.assertIsNone(settings.mem0_platform_key())

    def test_surrounding_whitespace_is_stripped(self):
        settings = Settings(_env_file=None, mem0_api_key="  m0-real\n")

        self.assertEqual(settings.mem0_platform_key(), "m0-real")

    def test_oss_backend_needs_the_explicit_flag(self):
        settings = Settings(_env_file=None, mem0_enabled=True)

        self.assertTrue(settings.mem0_configured())
        self.assertIsNone(settings.mem0_platform_key())


class FirecrawlSettingsTests(unittest.TestCase):
    def test_off_by_default(self):
        settings = Settings(_env_file=None)

        self.assertFalse(settings.firecrawl_configured())
        self.assertIsNone(settings.firecrawl_key())

    def test_api_key_enables_firecrawl(self):
        settings = Settings(_env_file=None, firecrawl_api_key="fc-real")

        self.assertTrue(settings.firecrawl_configured())
        self.assertEqual(settings.firecrawl_key(), "fc-real")

    def test_placeholder_key_is_ignored(self):
        settings = Settings(_env_file=None, firecrawl_api_key="your_firecrawl_api_key_here")

        self.assertFalse(settings.firecrawl_configured())

    def test_whitespace_only_key_is_not_a_key(self):
        settings = Settings(_env_file=None, firecrawl_api_key=" ")

        self.assertFalse(settings.firecrawl_configured())
        self.assertIsNone(settings.firecrawl_key())

    def test_self_hosted_url_is_enough(self):
        settings = Settings(_env_file=None, firecrawl_api_url="http://localhost:3002")

        self.assertTrue(settings.firecrawl_configured())
        self.assertIsNone(settings.firecrawl_key())


class BedrockSettingsTests(unittest.TestCase):
    def test_region_alone_does_not_enable_bedrock(self):
        with patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.bedrock_configured())

    def test_bedrock_requires_explicit_opt_in_and_region(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                bedrock_enabled=True,
                aws_region="us-west-2",
            )

        self.assertTrue(settings.bedrock_configured())


class ConductorSettingsTests(unittest.TestCase):
    def test_aws_cutover_defaults_are_bounded_and_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.conductor_primary_provider, "openai")
        self.assertEqual(settings.openai_model, "gpt-5.6-terra")
        self.assertEqual(settings.conductor_fallback_provider_names(), [])
        self.assertEqual(settings.conductor_max_fallbacks, 1)
        self.assertEqual(settings.openai_max_output_tokens, 800)
        self.assertEqual(settings.provider_timeout_seconds, 45.0)
        self.assertEqual(settings.provider_max_retries, 1)
        self.assertEqual(settings.mem0_default_user_id, "john")


if __name__ == "__main__":
    unittest.main()
