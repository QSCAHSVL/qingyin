import unittest

from cover_pipeline.plan import Profile
from cover_pipeline.setup import plan_setup, render


def probe(vram=8.0, disk=200.0, rvc=False, uvr=False):
    return {
        "gpu": [{"name": "fake", "vram_gb": vram}] if vram else [],
        "disk": {"free_gb": disk},
        "ffmpeg": {"available": True},
        "memory": {"total_gb": 16, "available_gb": 8},
        "deps": {},
        "assets": {"model_count": 0},
        "local": {"rvc": {"ok": rvc, "dir": ""}, "uvr": {"ok": uvr}},
    }


CFG = {"project": {"models_dir": "./models"}, "download": {"mirror": "https://hf-mirror.com"}}


class SetupPlanTest(unittest.TestCase):
    def test_local_env_still_writes_config_and_verify(self):
        result = plan_setup(probe(rvc=True, uvr=True), Profile(), CFG)
        kinds = [s["kind"] for s in result["steps"]]
        self.assertIn("config", kinds)
        self.assertIn("verify", kinds)
        self.assertNotIn("pip", kinds)
        self.assertEqual(result["total_mb"], 0)

    def test_fresh_gpu_has_pip_and_download(self):
        result = plan_setup(probe(vram=8), Profile(will_train="no"), CFG)
        kinds = [s["kind"] for s in result["steps"]]
        self.assertIn("pip", kinds)
        self.assertIn("download", kinds)
        ids = [s["id"] for s in result["steps"]]
        self.assertIn("download_hubert_base.pt", ids)
        self.assertNotIn("download_f0G40k.pth", ids)

    def test_train_adds_pretrained(self):
        result = plan_setup(probe(vram=8), Profile(will_train="yes"), CFG)
        ids = [s["id"] for s in result["steps"]]
        self.assertIn("download_f0G40k.pth", ids)
        self.assertIn("download_f0D40k.pth", ids)

    def test_cpu_picks_cpu_torch(self):
        result = plan_setup(probe(vram=0), Profile(), CFG)
        pip = [s for s in result["steps"] if s["kind"] == "pip"]
        self.assertTrue(any("whl/cpu" in " ".join(s["commands"]) for s in pip))

    def test_render_lines(self):
        result = plan_setup(probe(vram=8), Profile(), CFG)
        lines = render(result)
        self.assertTrue(any("步" in line for line in lines))


class SeparationChoiceTest(unittest.TestCase):
    def test_demucs_choice_installs_demucs_only(self):
        result = plan_setup(probe(vram=8), Profile(will_train="no"), CFG, separation="demucs")
        ids = [s["id"] for s in result["steps"]]
        self.assertIn("pip_demucs", ids)
        self.assertNotIn("pip_separator", ids)
        self.assertEqual(result["separation"], "demucs")

    def test_auto_prefers_demucs_when_disk_tight(self):
        result = plan_setup(probe(vram=8, disk=4.0), Profile(will_train="no"), CFG, separation="auto")
        self.assertEqual(result["separation"], "demucs")

    def test_auto_uses_uvr_when_local_uvr_present(self):
        result = plan_setup(probe(vram=8, rvc=True, uvr=True), Profile(), CFG, separation="auto")
        self.assertEqual(result["separation"], "uvr")
        self.assertNotIn("pip_separator", [s["id"] for s in result["steps"]])

    def test_both_installs_both(self):
        result = plan_setup(probe(vram=8), Profile(), CFG, separation="both")
        ids = [s["id"] for s in result["steps"]]
        self.assertIn("pip_demucs", ids)
        self.assertIn("pip_separator", ids)


if __name__ == "__main__":
    unittest.main()