"""recipes/loader.py：配方库读取、推荐项选择、决策记录。"""
import tempfile
import unittest
from pathlib import Path

import yaml

from cover_pipeline.recipes import loader


class LoadRecipesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "b_seam.yaml").write_text(
            yaml.safe_dump({"id": "seam_noise", "name": "接缝杂音", "recipes": [
                {"id": "r1", "name": "做法一", "how": "降 protect", "cost": "1 分钟", "risk": "音色略变"},
                {"id": "r2", "name": "做法二", "how": "换切点", "cost": "2 分钟", "risk": "低",
                 "experimental": True},
            ]}, allow_unicode=True),
            encoding="utf-8",
        )
        (self.dir / "a_muffle.yaml").write_text(
            yaml.safe_dump({"id": "muffled_vocal", "name": "人声发闷", "selected": "r9"}, allow_unicode=True),
            encoding="utf-8",
        )
        (self.dir / "broken.yaml").write_text("- 这不是映射\n- 只是列表\n", encoding="utf-8")
        (self.dir / "no_id.yaml").write_text("name: 没有 id 的配方\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_valid_recipes_only(self):
        items = loader.load_recipes(self.dir)
        self.assertEqual([i["id"] for i in items], ["muffled_vocal", "seam_noise"])  # 按文件名排序
        self.assertTrue(all("source" in i for i in items))

    def test_missing_dir_returns_empty(self):
        self.assertEqual(loader.load_recipes(self.dir / "不存在"), [])

    def test_find_recipe(self):
        self.assertIsNotNone(loader.find_recipe("seam_noise", self.dir))
        self.assertIsNone(loader.find_recipe("没有这个", self.dir))

    def test_recommended_prefers_selected(self):
        symptom = {"selected": "r2", "recipes": [{"id": "r1"}, {"id": "r2"}]}
        self.assertEqual(loader.recommended_of(symptom), "r2")

    def test_recommended_falls_back_to_first(self):
        symptom = {"recipes": [{"id": "r1"}, {"id": "r2"}]}
        self.assertEqual(loader.recommended_of(symptom), "r1")
        self.assertEqual(loader.recommended_of({}), "")

    def test_describe_marks_recommended(self):
        symptom = {
            "symptom": "接缝杂音",
            "recipes": [
                {"id": "r1", "name": "换切点", "how": "往前挪 0.2s", "cost": "1 分钟", "risk": "低"},
                {"id": "r2", "name": "实验做法", "how": "……", "cost": "3 分钟", "risk": "中",
                 "experimental": True, "evidence": "本机实测 2 次"},
            ],
        }
        text = loader.describe(symptom)
        self.assertIn("症状：接缝杂音", text)
        self.assertIn("★ 推荐", text)
        self.assertIn("实验性", text)
        self.assertIn("证据：本机实测 2 次", text)


class DecisionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = {"project": {"root": str(self.root)}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_and_read_last_choice(self):
        self.assertIsNone(loader.last_choice(self.cfg, "seam_noise"))
        loader.record_decision(self.cfg, "seam_noise", "r1", ["r1", "r2"], "先试保守的")
        loader.record_decision(self.cfg, "seam_noise", "r2", ["r1", "r2"])
        loader.record_decision(self.cfg, "muffled", "r3", ["r3"])
        self.assertEqual(loader.last_choice(self.cfg, "seam_noise"), "r2")
        self.assertEqual(loader.last_choice(self.cfg, "muffled"), "r3")
        lines = (self.root / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)

    def test_broken_lines_are_skipped(self):
        path = self.root / "decisions.jsonl"
        path.write_text('{"symptom": "a", "chosen": "x"}\n不是 json\n', encoding="utf-8")
        self.assertEqual(loader.last_choice(self.cfg, "a"), "x")


if __name__ == "__main__":
    unittest.main()
