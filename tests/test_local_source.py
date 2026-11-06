"""sources/local_file.py：本地音源解析（给文件、给目录、给歌名模糊匹配）。"""
import tempfile
import unittest
from pathlib import Path

from cover_pipeline.sources import SourceNotFound
from cover_pipeline.sources.local_file import LocalFileSource, _normalize, _score


class ScoreTest(unittest.TestCase):
    def test_exact_and_prefix(self):
        self.assertEqual(_score("abc", "abc"), 1.0)
        self.assertEqual(_score("abc", "abcdef"), 0.9)
        self.assertEqual(_score("abcdef", "abc"), 0.9)

    def test_contains(self):
        self.assertEqual(_score("abc", "xxabcxx"), 0.8)
        self.assertEqual(_score("xxabcxx", "abc"), 0.7)

    def test_partial_coverage(self):
        value = _score("abcd", "axcx")
        self.assertGreater(value, 0.0)
        self.assertLess(value, 0.7)

    def test_empty(self):
        self.assertEqual(_score("", "abc"), 0.0)
        self.assertEqual(_score("abc", ""), 0.0)

    def test_normalize_strips_punctuation(self):
        self.assertEqual(_normalize("千 年-食_谱·颂(cover)"), "千年食谱颂cover")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.music = self.root / "music"
        self.music.mkdir()
        self.song = self.music / "千年食谱颂 - 洛天依.flac"
        self.song.write_bytes(b"FLAC")
        (self.music / "笔记.txt").write_text("不是音频", encoding="utf-8")
        self.source = LocalFileSource()

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_file(self):
        got = self.source.resolve(str(self.song), self.root, {})
        self.assertEqual(got, self.song.resolve())

    def test_rejects_non_audio_suffix(self):
        with self.assertRaises(SourceNotFound):
            self.source.resolve(str(self.music / "笔记.txt"), self.root, {})

    def test_search_dirs_fuzzy_match(self):
        cfg = {"source": {"search_dirs": [str(self.music)]}}
        got = self.source.resolve("千年食谱颂", self.root, cfg)
        self.assertEqual(got, self.song.resolve())

    def test_directory_with_single_track_is_used(self):
        got = self.source.resolve(str(self.music), self.root, {})
        self.assertEqual(got, self.song.resolve())

    def test_directory_with_several_tracks_asks_for_specific_file(self):
        second = self.music / "另一首.mp3"
        second.write_bytes(b"ID3")
        with self.assertRaises(SourceNotFound) as ctx:
            self.source.resolve(str(self.music), self.root, {})
        self.assertIn("2 首", str(ctx.exception))

    def test_directory_without_audio_raises(self):
        empty = self.root / "empty"
        empty.mkdir()
        (empty / "说明.txt").write_text("没有音频", encoding="utf-8")
        with self.assertRaises(SourceNotFound) as ctx:
            self.source.resolve(str(empty), self.root, {})
        self.assertIn("没有能用的音频", str(ctx.exception))

    def test_no_match_raises(self):
        cfg = {"source": {"search_dirs": [str(self.music)]}}
        with self.assertRaises(SourceNotFound):
            self.source.resolve("完全不存在的歌", self.root, cfg)

    def test_no_search_dirs_raises_with_hint(self):
        with self.assertRaises(SourceNotFound) as ctx:
            self.source.resolve("某首歌", self.root, {})
        self.assertIn("search_dirs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
