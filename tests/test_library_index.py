"""资源库索引（library/index.py）：扫描、查询、收藏、软删除、统计。

这块是界面「资源库」页的数据源，之前完全没有测试；用临时目录跑，不碰真库。
"""
import tempfile
import unittest
from pathlib import Path

from cover_pipeline.library.index import Library, human_size


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.out = self.root / "output"
        self.models = self.root / "models"
        self.src = self.root / "music"
        for d in (self.work, self.out, self.models, self.src):
            d.mkdir(parents=True)

        # 一首「歌」：work/<歌名>/1-源文件/原始.wav，外加一个下划线开头的缓存目录（应被跳过）
        song = self.work / "测试歌"
        (song / "1-源文件").mkdir(parents=True)
        (song / "1-源文件" / "原始.wav").write_bytes(b"RIFF" * 100)
        cache = self.work / "_cache"
        cache.mkdir()
        (cache / "x.wav").write_bytes(b"RIFF")

        (self.out / "成品.wav").write_bytes(b"RIFF" * 200)
        (self.models / "yuzhou.pth").write_bytes(b"PTH" * 300)
        (self.src / "别人的歌.flac").write_bytes(b"FLAC" * 100)

        self.cfg = {
            "project": {
                "models_dir": str(self.models),
                "work_dir": str(self.work),
                "output_dir": str(self.out),
            },
            "source": {"search_dirs": [str(self.src)]},
        }
        self.lib = Library(self.root / "library.db")

    def tearDown(self):
        self.lib.close()
        self.tmp.cleanup()

    def test_scan_counts_each_kind(self):
        counts = self.lib.scan(self.cfg)
        self.assertEqual(counts["model"], 1)
        self.assertEqual(counts["song"], 1)       # _cache 被跳过
        self.assertEqual(counts["output"], 1)
        self.assertEqual(counts["source"], 1)

    def test_scan_is_idempotent(self):
        self.lib.scan(self.cfg)
        self.lib.scan(self.cfg)                    # 再扫一遍不该重复插入
        self.assertEqual(self.lib.count("model"), 1)
        self.assertEqual(self.lib.count("song"), 1)

    def test_list_filters_and_paginates(self):
        self.lib.scan(self.cfg)
        songs = self.lib.list(kind="song")
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0]["name"], "测试歌")
        self.assertGreater(songs[0]["size_bytes"], 0)
        self.assertEqual(self.lib.list(kind="song", limit=1, page=2), [])

    def test_query_matches_name(self):
        self.lib.scan(self.cfg)
        self.assertEqual(len(self.lib.list(query="测试")), 1)
        self.assertEqual(self.lib.list(query="不存在的"), [])

    def test_favorites_roundtrip(self):
        self.lib.scan(self.cfg)
        path = self.lib.list(kind="song")[0]["path"]
        self.assertFalse(self.lib.is_favorite(path))
        self.assertTrue(self.lib.set_favorite(path, True))
        self.assertTrue(self.lib.is_favorite(path))
        self.assertEqual(len(self.lib.favorites()), 1)
        self.assertEqual(self.lib.list(kind="song")[0]["favorite"], 1)
        self.lib.set_favorite(path, False)
        self.assertFalse(self.lib.is_favorite(path))

    def test_delete_moves_to_trash_and_drops_row(self):
        self.lib.scan(self.cfg)
        item = self.lib.list(kind="output")[0]
        trash = self.root / "work" / "_trash"
        moved = self.lib.delete(item["path"], trash)
        self.assertIsNotNone(moved)
        self.assertTrue(Path(moved).exists())
        self.assertFalse(Path(item["path"]).exists())
        self.assertEqual(self.lib.count("output"), 0)

    def test_delete_missing_returns_none(self):
        self.assertIsNone(self.lib.delete(str(self.root / "没有这个文件.wav"), self.root / "_trash"))

    def test_remove_by_key(self):
        self.lib.scan(self.cfg)
        item = self.lib.list(kind="model")[0]
        self.assertTrue(self.lib.remove("model", item["path"]))
        self.assertFalse(self.lib.remove("model", item["path"]))
        self.assertEqual(self.lib.count("model"), 0)

    def test_stats_sums_bytes(self):
        self.lib.scan(self.cfg)
        stats = self.lib.stats()
        self.assertEqual(stats["items"], 4)
        self.assertGreater(stats["total_bytes"], 0)
        self.assertEqual(stats["by_kind"]["song"]["count"], 1)

    def test_detail_returns_extra(self):
        self.lib.scan(self.cfg)
        path = self.lib.list(kind="song")[0]["path"]
        detail = self.lib.detail(path)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["kind"], "song")
        self.assertIsNone(self.lib.detail(str(self.root / "nope")))


class HumanSizeTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(human_size(0), "0.0B")
        self.assertEqual(human_size(999), "999.0B")
        self.assertEqual(human_size(1024), "1.0KB")
        self.assertEqual(human_size(1024 ** 2 * 2.5), "2.5MB")
        self.assertEqual(human_size(1024 ** 3 * 3), "3.0GB")


if __name__ == "__main__":
    unittest.main()
