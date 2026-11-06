"""server/services/common.py 与 utils 层的小工具（之前没人测）。"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cover_pipeline.server.services import common
from cover_pipeline.utils import ffmpeg as ffmpeg_mod


class IsInsideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "sub").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_inside(self):
        self.assertTrue(common.is_inside(self.root / "sub", self.root))
        self.assertTrue(common.is_inside(self.root, self.root))

    def test_outside(self):
        self.assertFalse(common.is_inside(self.root.parent, self.root))
        self.assertFalse(common.is_inside(self.root.parent / "other", self.root))


class GpuUsedTest(unittest.TestCase):
    def test_reads_nvidia_smi(self):
        fake = mock.Mock(stdout="2048\n", returncode=0)
        with mock.patch("subprocess.run", return_value=fake):
            self.assertEqual(common.gpu_used_gb(), 2.0)

    def test_no_gpu_returns_zero(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("no nvidia-smi")):
            self.assertEqual(common.gpu_used_gb(), 0.0)

    def test_garbage_output_returns_zero(self):
        fake = mock.Mock(stdout="", returncode=0)
        with mock.patch("subprocess.run", return_value=fake):
            self.assertEqual(common.gpu_used_gb(), 0.0)


class FfmpegDurationTest(unittest.TestCase):
    def test_delegates_to_ffmpeg(self):
        with mock.patch.object(ffmpeg_mod, "duration", return_value=12.5):
            self.assertEqual(common.ffmpeg_duration(Path("x.wav")), 12.5)


if __name__ == "__main__":
    unittest.main()
