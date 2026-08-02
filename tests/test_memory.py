import os
import unittest
from unittest.mock import patch

from conductor.memory import Mem0Memory


class Mem0MemoryTests(unittest.TestCase):
    def test_fails_open_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            mem = Mem0Memory()

        self.assertFalse(mem.enabled)
        self.assertEqual(mem.search("anything"), "")
        mem.add("hi", "hello")  # must not raise

    def test_default_user_id_is_shared_brain(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Mem0Memory().user_id, "ara-partner")

    def test_rows_handles_list_dict_and_none(self):
        self.assertEqual(Mem0Memory._rows([{"memory": "x"}]), [{"memory": "x"}])
        self.assertEqual(Mem0Memory._rows({"results": [{"memory": "y"}]}), [{"memory": "y"}])
        self.assertEqual(Mem0Memory._rows(None), [])


if __name__ == "__main__":
    unittest.main()
