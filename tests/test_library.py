import tempfile
import unittest
from pathlib import Path

from cover_pipeline.library import Library


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = Library(self.root / "lib.db")

    def tearDown(self):
        self.lib.close()
        self.tmp.cleanup()

    def test_pagination_and_count(self):
        for i in range(7):
            path = self.root / f"m{i}.pth"
            path.write_bytes(b"x" * 10)
            self.lib._upsert("model", path)
        self.lib._conn.commit()
        self.assertEqual(self.lib.count("model"), 7)
        self.assertEqual(len(self.lib.list("model", limit=3, page=1)), 3)
        self.assertEqual(len(self.lib.list("model", limit=3, page=3)), 1)

    def test_favorite_roundtrip(self):
        path = self.root / "a.pth"
        path.write_bytes(b"x")
        self.lib._upsert("model", path)
        self.lib._conn.commit()
        self.lib.set_favorite(str(path), True)
        self.assertTrue(self.lib.is_favorite(str(path)))
        self.assertEqual(len(self.lib.favorites()), 1)
        self.lib.set_favorite(str(path), False)
        self.assertFalse(self.lib.is_favorite(str(path)))

    def test_soft_delete_moves_file(self):
        path = self.root / "out.wav"
        path.write_bytes(b"x")
        self.lib._upsert("output", path)
        self.lib._conn.commit()
        moved = self.lib.delete(str(path), self.root / "_trash")
        self.assertIsNotNone(moved)
        self.assertFalse(path.exists())
        self.assertTrue(Path(moved).exists())


if __name__ == "__main__":
    unittest.main()