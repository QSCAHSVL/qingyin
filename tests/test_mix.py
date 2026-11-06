"""core/mix.py：增益换算与混音编排（ffmpeg 全部打桩，不真跑）。"""
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cover_pipeline.core import mix as mix_mod
from cover_pipeline.utils import ffmpeg as ffmpeg_mod


class ToDbTest(unittest.TestCase):
    def test_linear_to_db(self):
        self.assertAlmostEqual(mix_mod._to_db({"vocal_gain": 2.5}, "vocal_gain", "vocal_gain_db"), 7.96, places=2)
        self.assertEqual(mix_mod._to_db({"vocal_gain": 1.0}, "vocal_gain", "vocal_gain_db"), 0.0)

    def test_db_key_wins(self):
        conf = {"vocal_gain": 2.5, "vocal_gain_db": +8}
        self.assertEqual(mix_mod._to_db(conf, "vocal_gain", "vocal_gain_db"), 8.0)

    def test_missing_and_invalid(self):
        self.assertEqual(mix_mod._to_db({}, "vocal_gain", "vocal_gain_db"), 0.0)
        self.assertEqual(mix_mod._to_db({"vocal_gain": 0}, "vocal_gain", "vocal_gain_db"), 0.0)
        self.assertEqual(mix_mod._to_db({"vocal_gain": -3}, "vocal_gain", "vocal_gain_db"), 0.0)


class MixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vocal = self.root / "vocal.wav"
        self.vocal.write_bytes(b"RIFF")
        self.backing = self.root / "inst.wav"
        self.backing.write_bytes(b"RIFF")
        self.out = self.root / "out" / "mixed.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_backing_just_converts(self):
        with mock.patch.object(ffmpeg_mod, "to_wav", return_value=self.out) as patched:
            got = mix_mod.mix(self.vocal, None, self.out, {"mix": {}})
        self.assertEqual(got, self.out)
        patched.assert_called_once()
        self.assertEqual(patched.call_args.args[0], self.vocal)

    def test_amix_and_normalize_called(self):
        seen = {}

        def fake_amix(vocal, backing, out_path, vocal_db, backing_db, warmth_db, limiter, cfg):
            seen.update(vocal_db=vocal_db, backing_db=backing_db, warmth=warmth_db, limiter=limiter)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"RIFF")

        with mock.patch.object(mix_mod, "_amix", side_effect=fake_amix), \
                mock.patch.object(mix_mod, "_normalize") as norm:
            mix_mod.mix(self.vocal, self.backing, self.out, {
                "mix": {"vocal_gain": 2.0, "backing_gain_db": -6, "warmth_db": 1.5, "limiter": True,
                        "normalize": True, "target_lufs": -14}
            })
        self.assertAlmostEqual(seen["vocal_db"], round(20 * math.log10(2.0), 2), places=3)
        self.assertEqual(seen["backing_db"], -6.0)
        self.assertEqual(seen["warmth"], 1.5)
        self.assertTrue(seen["limiter"])
        norm.assert_called_once()
        self.assertEqual(norm.call_args.args[1], -14.0)

    def test_normalize_can_be_disabled(self):
        def fake_amix(vocal, backing, out_path, *args):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"RIFF")

        with mock.patch.object(mix_mod, "_amix", side_effect=fake_amix), \
                mock.patch.object(mix_mod, "_normalize") as norm:
            mix_mod.mix(self.vocal, self.backing, self.out, {"mix": {"normalize": False}})
        norm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
