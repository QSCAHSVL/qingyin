import tempfile
import unittest
from pathlib import Path

from cover_pipeline.plan import engine, stats


class PlanStatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stats._path_override = Path(self.tmp.name) / "stats.jsonl"

    def tearDown(self):
        stats._path_override = None
        self.tmp.cleanup()

    def test_record_and_summary(self):
        stats.record("vram8_balanced", True, seconds=120)
        stats.record("vram8_balanced", False, seconds=30, kind="oom")
        table = stats.summary()
        item = table["vram8_balanced"]
        self.assertEqual(item["runs"], 2)
        self.assertEqual(item["ok"], 1)
        self.assertEqual(item["kinds"]["oom"], 1)
        self.assertEqual(item["avg_seconds"], 75.0)

    def test_adjust_penalises_oom(self):
        for _ in range(3):
            stats.record("vram12_quality", False, kind="oom")
        table = stats.summary()
        self.assertLess(stats.adjust("vram12_quality", 4.0, table), 4.0)

    def test_bad_json_ignored(self):
        stats.stats_path().parent.mkdir(parents=True, exist_ok=True)
        stats.stats_path().write_text("{not json}\n", encoding="utf-8")
        self.assertEqual(stats.summary(), {})


class PlanHealTest(unittest.TestCase):
    def setUp(self):
        self.plan = engine.load_plans()[0]

    def test_classify(self):
        self.assertEqual(engine.__name__ and __import__("cover_pipeline.plan.heal", fromlist=["classify"]).classify("CUDA out of memory"), "oom")
        heal = __import__("cover_pipeline.plan.heal", fromlist=["classify"])
        self.assertEqual(heal.classify("Read timed out"), "timeout")
        self.assertEqual(heal.classify("No module named 'x'"), "missing_model")

    def test_degrade_lowers_batch(self):
        heal = __import__("cover_pipeline.plan.heal", fromlist=["degrade"])
        healed = heal.degrade(self.plan, "oom")
        self.assertIsNotNone(healed)
        self.assertLessEqual(healed["params"]["train"]["batch_size"], self.plan["params"]["train"]["batch_size"])
        self.assertTrue(healed["id"].endswith("+healoom"))

    def test_retry_cap(self):
        heal = __import__("cover_pipeline.plan.heal", fromlist=["next_plan"])
        self.assertIsNotNone(heal.next_plan(self.plan, "OOM", 1))
        self.assertIsNone(heal.next_plan(self.plan, "OOM", 2))


if __name__ == "__main__":
    unittest.main()