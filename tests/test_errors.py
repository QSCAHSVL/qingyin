import unittest

from cover_pipeline.utils import errors


class ErrorExplainTest(unittest.TestCase):
    def test_cuda_oom(self):
        info = errors.explain(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
        self.assertIn("显存", info["title"])

    def test_missing_module(self):
        info = errors.explain(ModuleNotFoundError("No module named 'audio_separator'"))
        self.assertIn("依赖", info["title"])

    def test_unknown_falls_back(self):
        info = errors.explain(ValueError("something odd"))
        self.assertEqual(info["title"], "出错了")
        self.assertIn("日志", info["hint"])


if __name__ == "__main__":
    unittest.main()