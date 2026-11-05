"""core/pitch.py 的回归测试。

曾经这里有一个只在运行到才炸的 bug：`shift_file()` 用了 `ffmpeg.run(...)`，
但模块只 `from ..utils import log`，没导 ffmpeg —— 整首移调一跑就 NameError。
静态检查（ruff F821）能抓到，这里再加一层行为测试。
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cover_pipeline.core import pitch
from cover_pipeline.utils import ffmpeg as ffmpeg_util


class ShiftFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shift_file_builds_filter_and_calls_ffmpeg(self):
        src = self.root / "vocal.wav"
        src.write_bytes(b"RIFF")
        out = self.root / "out" / "vocal_m2.wav"
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))

        with mock.patch.object(ffmpeg_util, "run", side_effect=fake_run):
            got = pitch.shift_file(src, -2, out)

        self.assertEqual(got, out)
        self.assertTrue(out.parent.is_dir())  # 输出目录会被创建
        self.assertEqual(len(calls), 1)
        args = calls[0][0]
        self.assertEqual(args[0], "ffmpeg")
        self.assertIn(str(src), args)
        self.assertIn(str(out), args)
        filt = args[args.index("-af") + 1]
        ratio = 2 ** (-2 / 12)
        self.assertIn(f"asetrate=44100*{ratio:.6f}", filt)
        self.assertIn(f"atempo={1 / ratio:.6f}", filt)

    def test_zero_semitones_returns_source_without_calling_ffmpeg(self):
        src = self.root / "vocal.wav"
        src.write_bytes(b"RIFF")
        with mock.patch.object(ffmpeg_util, "run") as patched:
            got = pitch.shift_file(src, 0, self.root / "never.wav")
        self.assertEqual(got, src)
        patched.assert_not_called()

    def test_cancel_event_is_forwarded(self):
        src = self.root / "vocal.wav"
        src.write_bytes(b"RIFF")
        seen = {}

        def fake_run(args, **kwargs):
            seen.update(kwargs)

        token = object()
        with mock.patch.object(ffmpeg_util, "run", side_effect=fake_run):
            pitch.shift_file(src, 1, self.root / "o.wav", {"_cancel_event": token})
        self.assertIs(seen.get("cancel_event"), token)


class EstimateShiftTest(unittest.TestCase):
    def test_auto_pitch_off_uses_configured_pitch(self):
        cfg = {"convert": {"auto_pitch": False, "pitch": -2}}
        self.assertEqual(pitch.estimate_shift(Path("x.wav"), cfg), -2)

    def test_analysis_failure_keeps_original_key(self):
        cfg = {"convert": {"auto_pitch": True}}
        with mock.patch.object(pitch, "_median_f0", side_effect=RuntimeError("没装 librosa")):
            self.assertEqual(pitch.estimate_shift(Path("x.wav"), cfg), 0)

    def test_high_pitch_source_goes_down(self):
        cfg = {"convert": {"auto_pitch": True, "auto_pitch_range": [-3, 3]}}
        with mock.patch.object(pitch, "_median_f0", return_value=400.0):
            shift = pitch.estimate_shift(Path("x.wav"), cfg)
        self.assertLess(shift, 0)
        self.assertGreaterEqual(shift, -3)

    def test_low_pitch_source_goes_up(self):
        cfg = {"convert": {"auto_pitch": True, "auto_pitch_range": [-3, 3]}}
        with mock.patch.object(pitch, "_median_f0", return_value=90.0):
            self.assertEqual(pitch.estimate_shift(Path("x.wav"), cfg), 1)


if __name__ == "__main__":
    unittest.main()
