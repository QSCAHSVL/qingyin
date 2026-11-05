import unittest

from cover_pipeline.plan import Profile, recommend, recommend_assets


def probe(vram=8.0, disk=200.0, rvc=False, uvr=False):
    return {
        "gpu": [{"name": "fake", "vram_gb": vram}] if vram else [],
        "disk": {"free_gb": disk},
        "ffmpeg": {"available": True},
        "memory": {"total_gb": 16, "available_gb": 8},
        "deps": {},
        "assets": {"model_count": 0},
        "local": {
            "rvc": {"ok": rvc},
            "uvr": {"ok": uvr},
        },
    }


class AssetRecommendTest(unittest.TestCase):
    def test_local_env_reuses_nothing(self):
        result = recommend_assets(probe(rvc=True, uvr=True), Profile())
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_mb"], 0)
        self.assertEqual(result["bundle"]["id"], "reuse_local")

    def test_cpu_only_bundle(self):
        result = recommend_assets(probe(vram=0), Profile())
        ids = {item["id"] for item in result["items"]}
        self.assertIn("torch_cpu", ids)
        self.assertNotIn("torch_cuda", ids)
        self.assertLess(result["total_mb"], 2000)

    def test_gpu_train_bundle_has_pretrained(self):
        result = recommend_assets(probe(vram=8), Profile(will_train="yes"))
        ids = {item["id"] for item in result["items"]}
        self.assertIn("torch_cuda", ids)
        self.assertIn("pretrained_v2", ids)

    def test_low_vram_uses_light_separation(self):
        result = recommend_assets(probe(vram=4), Profile())
        ids = {item["id"] for item in result["items"]}
        self.assertIn("uvr_hp2", ids)
        self.assertNotIn("uvr_becruily", ids)

    def test_disk_warning(self):
        result = recommend_assets(probe(vram=8, disk=1.0), Profile())
        self.assertTrue(result["warning"])

    def test_plan_hp2_overrides_separation(self):
        plans = recommend(probe(vram=8), Profile())
        quiet = next((s.plan for s in plans if s.id == "vram8_quiet"), None)
        result = recommend_assets(probe(vram=8), Profile(), quiet)
        ids = {item["id"] for item in result["items"]}
        self.assertIn("uvr_hp2", ids)


if __name__ == "__main__":
    unittest.main()