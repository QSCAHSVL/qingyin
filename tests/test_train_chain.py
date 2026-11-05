import tempfile
import unittest
from pathlib import Path

from cover_pipeline import models
from cover_pipeline.pipelines import train as train_mod


class TrainChainTest(unittest.TestCase):
    """验证「训练产出 .pth → 自动登记版本 → 可切回旧版」这条链路。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = {
            "project": {
                "work_dir": str(self.root / "work"),
                "models_dir": str(self.root / "models"),
            }
        }
        self.work = self.root / "work" / "demo"
        self.work.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_after_training(self):
        out = self.work / "fake_out"
        out.mkdir(parents=True, exist_ok=True)
        pth = out / "demo.pth"
        pth.write_bytes(b"FAKE" * 2048)

        info = train_mod._register_result("demo", self.cfg, {"output_dir": str(out), "epochs": 80})
        self.assertIsNotNone(info)
        self.assertEqual(info["version"], "v1")
        voices = models.list_models(self.cfg)
        self.assertEqual(voices[0]["voice"], "demo")
        self.assertEqual(voices[0]["active"], "v1")

    def test_second_training_creates_v2_and_can_rollback(self):
        for _ in range(2):
            out = self.work / f"out{_}"
            out.mkdir(parents=True, exist_ok=True)
            (out / "demo.pth").write_bytes(b"FAKE" * 2048)
            train_mod._register_result("demo", self.cfg, {"output_dir": str(out)})

        versions = models.list_models(self.cfg)[0]["versions"]
        self.assertEqual(len(versions), 2)
        self.assertEqual(models.list_models(self.cfg)[0]["active"], "v2")

        models.activate_version(self.cfg, "demo", "v1")
        active = models.active_model_path(self.cfg, "demo")
        self.assertIn("v1", str(active))

    def test_missing_output_returns_none(self):
        info = train_mod._register_result("demo", self.cfg, {"output_dir": str(self.root / "nope")})
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()