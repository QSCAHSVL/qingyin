import unittest

from cover_pipeline.plan import engine


class FitPlanTest(unittest.TestCase):
    def test_blend_between_tiers(self):
        plans = engine.load_plans()
        fitted = engine.fit_to_probe({"gpu": {"vram_gb": 6.8}}, plans)
        self.assertIsNotNone(fitted)
        self.assertTrue(fitted.get("generated"))
        self.assertIn("fit_", fitted["id"])
        self.assertEqual(len(fitted.get("derived_from", [])), 2)

    def test_exact_tier_returns_none(self):
        plans = engine.load_plans()
        self.assertIsNone(engine.fit_to_probe({"gpu": {"vram_gb": 8.0}}, plans))

    def test_no_gpu_returns_none(self):
        self.assertIsNone(engine.fit_to_probe({"gpu": {}}, engine.load_plans()))


if __name__ == "__main__":
    unittest.main()
