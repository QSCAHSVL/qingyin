import unittest

from cover_pipeline.plan import Profile, load_plans, recommend


def fake_probe(vram=8.0, disk=100.0):
    return {
        "gpu": [{"name": "fake", "vram_gb": vram}] if vram else [],
        "disk": {"free_gb": disk},
        "ffmpeg": {"available": True},
        "memory": {"total_gb": 16, "available_gb": 8},
        "deps": {},
        "assets": {"model_count": 1},
        "local": {},
    }


class PlanEngineTest(unittest.TestCase):
    def test_plans_loaded(self):
        plans = load_plans()
        self.assertGreaterEqual(len(plans), 10)
        ids = {p["id"] for p in plans}
        self.assertIn("vram8_balanced", ids)

    def test_recommend_for_8g(self):
        scored = recommend(fake_probe(8.0), Profile())
        self.assertTrue(scored)
        self.assertTrue(scored[0].recommended)
        self.assertLessEqual(len([s for s in scored if not s.excluded_reason]), 3)

    def test_vram_budget_excludes(self):
        scored = recommend(fake_probe(8.0), Profile(max_vram_gb=5.0))
        available = [s for s in scored if not s.excluded_reason]
        for item in available:
            peak = float(item.plan.get("estimate", {}).get("vram_peak_gb") or 0)
            self.assertLessEqual(peak, 5.0)

    def test_no_gpu_excludes_gpu_plans(self):
        scored = recommend(fake_probe(0), Profile())
        for item in scored:
            if item.excluded_reason:
                continue
            self.assertFalse(item.plan.get("for", {}).get("gpu_required", True))


if __name__ == "__main__":
    unittest.main()