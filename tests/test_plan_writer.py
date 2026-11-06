"""plan/writer.py：把方案写进 configs/local.yaml，且不能弄丢用户手改的其它段。"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from cover_pipeline import config as cfg_mod
from cover_pipeline.plan import writer


class ApplyPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name) / "configs"
        self.config_dir.mkdir()
        self.patch = mock.patch.object(cfg_mod, "CONFIG_DIR", self.config_dir)
        self.patch.start()
        self.path = self.config_dir / "local.yaml"

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _write_existing(self, data: dict) -> None:
        self.path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    def test_creates_file_with_plan_params(self):
        plan = {"id": "vram8_balanced", "name": "8G 均衡", "params": {"convert": {"pitch": 0}}}
        out = writer.apply_plan(plan)
        self.assertEqual(out, self.path)
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["convert"]["pitch"], 0)
        self.assertEqual(data["plan"]["id"], "vram8_balanced")
        self.assertIn("applied_at", data["plan"])

    def test_keeps_untouched_sections(self):
        self._write_existing({
            "tools": {"rvc_dir": "D:/RVC"},
            "source": {"search_dirs": ["D:/music"]},
            "convert": {"backend": "local"},
        })
        plan = {"id": "p", "name": "n", "params": {"convert": {"pitch": -2}, "separate": {"model": "uvr"}}}
        writer.apply_plan(plan)
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["tools"]["rvc_dir"], "D:/RVC")
        self.assertEqual(data["source"]["search_dirs"], ["D:/music"])
        # 深合并：老的 backend 保留，新参数叠加
        self.assertEqual(data["convert"]["backend"], "local")
        self.assertEqual(data["convert"]["pitch"], -2)
        self.assertEqual(data["separate"]["model"], "uvr")

    def test_ignores_unmanaged_keys_in_plan(self):
        plan = {"id": "p", "name": "n", "params": {"tools": {"bad": 1}, "device": {"gpu": 9}}}
        writer.apply_plan(plan)
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("tools", data)
        self.assertNotIn("device", data)

    def test_makes_backup_before_overwrite(self):
        self._write_existing({"tools": {"rvc_dir": "D:/RVC"}})
        writer.apply_plan({"id": "p", "name": "n", "params": {}})
        backups = list(self.config_dir.glob("local.yaml.bak-*"))
        self.assertEqual(len(backups), 1)
        old = yaml.safe_load(backups[0].read_text(encoding="utf-8"))
        self.assertEqual(old["tools"]["rvc_dir"], "D:/RVC")

    def test_no_backup_when_disabled(self):
        self._write_existing({"tools": {"rvc_dir": "D:/RVC"}})
        writer.apply_plan({"id": "p", "name": "n", "params": {}}, backup=False)
        self.assertEqual(list(self.config_dir.glob("local.yaml.bak-*")), [])

    def test_current_plan_reads_back(self):
        self.assertIsNone(writer.current_plan())
        writer.apply_plan({"id": "abc", "name": "方案", "params": {}})
        cur = writer.current_plan()
        self.assertIsNotNone(cur)
        self.assertEqual(cur["id"], "abc")

    def test_current_plan_tolerates_broken_yaml(self):
        self.path.write_text("\t这是坏 yaml: [", encoding="utf-8")
        self.assertIsNone(writer.current_plan())


if __name__ == "__main__":
    unittest.main()
