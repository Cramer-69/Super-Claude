import unittest

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

    def test_self_hosted_url_is_enough(self):
        settings = Settings(_env_file=None, firecrawl_api_url="http://localhost:3002")

        self.assertTrue(settings.firecrawl_configured())
        self.assertIsNone(settings.firecrawl_key())


if __name__ == "__main__":
    unittest.main()
