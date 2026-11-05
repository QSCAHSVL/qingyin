"""仓库元数据自检。

来历：0.2.x 时代 `scripts/sync_version.py` 用的正则没做行首锚定，
把 pyproject 里 `[tool.ruff] target-version` 一起替换成了 `"0.2.0"`（人家要的是 `py310`）。
ruff 读到非法值直接拒绝启动，而 CI 里 lint 又是 `continue-on-error` + `--exit-zero`，
于是「lint 从来没真正跑过」这件事一直没人发现。这里补一道守卫。
"""
import re
import unittest
from pathlib import Path

from cover_pipeline import __version__

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


class ProjectMetaTest(unittest.TestCase):
    def setUp(self):
        self.text = PYPROJECT.read_text(encoding="utf-8")

    def test_project_version_matches_package(self):
        match = re.search(r'(?m)^version = "([^"]+)"$', self.text)
        self.assertIsNotNone(match, "pyproject 里找不到 [project] version")
        self.assertEqual(match.group(1), __version__)

    def test_ruff_target_version_is_python_tag(self):
        match = re.search(r'(?m)^target-version = "([^"]+)"$', self.text)
        self.assertIsNotNone(match, "pyproject 里没有 [tool.ruff] target-version")
        value = match.group(1)
        self.assertRegex(value, r"^py3\d{1,2}$", f"target-version 应该是 py310 这种，现在是 {value!r}")

    def test_requires_python_matches_ruff_target(self):
        requires = re.search(r'(?m)^requires-python = ">=([\d.]+)"$', self.text)
        target = re.search(r'(?m)^target-version = "py(\d)(\d+)"$', self.text)
        self.assertIsNotNone(requires)
        self.assertIsNotNone(target)
        want = tuple(int(x) for x in requires.group(1).split(".")[:2])
        got = (int(target.group(1)), int(target.group(2)))
        self.assertEqual(got, want, "ruff 的 target-version 要和 requires-python 对齐")

    def test_version_consistency_script_passes(self):
        import subprocess
        import sys

        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_version.py"), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
