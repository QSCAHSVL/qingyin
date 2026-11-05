import tempfile
import unittest
from pathlib import Path

from cover_pipeline.pipelines import train as train_mod


class TrainPreviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = {"train": {"epochs": 80, "batch_size": 4, "sample_rate": 40000, "clean": True, "command": ""}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_dir_warns(self):
        info = train_mod.preview(self.root, self.cfg)
        self.assertEqual(info["files"], 0)
        self.assertFalse(info["command_configured"])
        self.assertTrue(any("没找到音频" in w for w in info["warnings"]))

    def test_low_epochs_warns(self):
        self.cfg["train"]["epochs"] = 10
        info = train_mod.preview(self.root, self.cfg)
        self.assertTrue(any("少于 20" in w for w in info["warnings"]))

    def test_command_configured_flag(self):
        self.cfg["train"]["command"] = "python x.py"
        info = train_mod.preview(self.root, self.cfg)
        self.assertTrue(info["command_configured"])
        self.assertTrue(info["command_hint"].startswith("python"))


if __name__ == "__main__":
    unittest.main()
