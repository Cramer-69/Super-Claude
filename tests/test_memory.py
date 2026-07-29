import unittest
from unittest.mock import MagicMock, patch

from knowledge_base.memory import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_disabled_by_default_returns_no_memories(self):
        with patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = False
            store = MemoryStore()

        self.assertFalse(store.enabled)
        self.assertEqual(store.search("hi", user_id="u1"), [])
        # add() on a disabled store must be a silent no-op, never raise.
        store.add("hi", user_id="u1")

    def test_missing_mem0_package_disables_store(self):
        with patch("knowledge_base.memory.MEM0_AVAILABLE", False), \
             patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = True
            store = MemoryStore()

        self.assertFalse(store.enabled)

    def test_enabled_store_delegates_to_mem0_client(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": [{"memory": "likes coffee"}]}

        with patch("knowledge_base.memory.MEM0_AVAILABLE", True), \
             patch("knowledge_base.memory.Memory", return_value=mock_client), \
             patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = True
            store = MemoryStore()

        self.assertTrue(store.enabled)

        store.add("I like coffee", user_id="u1", role="user")
        mock_client.add.assert_called_once_with(
            [{"role": "user", "content": "I like coffee"}], user_id="u1"
        )

        results = store.search("coffee", user_id="u1")
        mock_client.search.assert_called_once_with("coffee", user_id="u1", limit=5)
        self.assertEqual(results, [{"memory": "likes coffee"}])

    def test_search_normalizes_non_dict_items(self):
        mock_client = MagicMock()
        mock_client.search.return_value = ["likes coffee", "works remotely"]

        with patch("knowledge_base.memory.MEM0_AVAILABLE", True), \
             patch("knowledge_base.memory.Memory", return_value=mock_client), \
             patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = True
            store = MemoryStore()

        results = store.search("coffee", user_id="u1")

        self.assertEqual(
            results,
            [{"memory": "likes coffee"}, {"memory": "works remotely"}],
        )
        for item in results:
            # Downstream callers rely on dict.get() never raising.
            self.assertIsNone(item.get("nonexistent_key"))

    def test_search_failure_is_swallowed(self):
        mock_client = MagicMock()
        mock_client.search.side_effect = RuntimeError("boom")

        with patch("knowledge_base.memory.MEM0_AVAILABLE", True), \
             patch("knowledge_base.memory.Memory", return_value=mock_client), \
             patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = True
            store = MemoryStore()

        self.assertEqual(store.search("coffee", user_id="u1"), [])

    def test_client_init_failure_disables_store(self):
        with patch("knowledge_base.memory.MEM0_AVAILABLE", True), \
             patch("knowledge_base.memory.Memory", side_effect=RuntimeError("no key")), \
             patch("knowledge_base.memory.settings") as mock_settings:
            mock_settings.mem0_enabled = True
            store = MemoryStore()

        self.assertFalse(store.enabled)


if __name__ == "__main__":
    unittest.main()
