import tempfile
import unittest
from pathlib import Path

from cover_pipeline import models


class ModelRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = {"project": {"models_dir": str(self.root / "models")}}
        self.pth = self.root / "fake.pth"
        self.pth.write_bytes(b"fake weights" * 100)

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_creates_versions_and_activates(self):
        v1 = models.register(self.cfg, "voiceA", self.pth, {"epochs": 80})
        self.assertEqual(v1["version"], "v1")
        v2 = models.register(self.cfg, "voiceA", self.pth, {"epochs": 120})
        self.assertEqual(v2["version"], "v2")

        listed = models.list_models(self.cfg)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["active"], "v2")
        self.assertEqual(len(listed[0]["versions"]), 2)

    def test_activate_old_version(self):
        models.register(self.cfg, "voiceA", self.pth)
        models.register(self.cfg, "voiceA", self.pth)
        models.activate_version(self.cfg, "voiceA", "v1")
        self.assertTrue(models.active_model_path(self.cfg, "voiceA").as_posix().endswith("v1/voiceA.pth"))

    def test_cannot_delete_active(self):
        models.register(self.cfg, "voiceA", self.pth)
        with self.assertRaises(RuntimeError):
            models.delete_version(self.cfg, "voiceA", "v1")

    def test_delete_inactive(self):
        models.register(self.cfg, "voiceA", self.pth)
        models.register(self.cfg, "voiceA", self.pth)
        self.assertTrue(models.delete_version(self.cfg, "voiceA", "v1"))
        self.assertEqual(len(models.list_models(self.cfg)[0]["versions"]), 1)


if __name__ == "__main__":
    unittest.main()