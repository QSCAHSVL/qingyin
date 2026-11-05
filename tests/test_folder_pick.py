import unittest
from pathlib import Path

from cover_pipeline.utils import folder_pick


class FolderPickScriptTest(unittest.TestCase):
    def test_script_contains_dialog_and_output(self):
        script = folder_pick.build_script("选目录", None, Path("C:/tmp/out.txt"))
        self.assertIn("FolderBrowserDialog", script)
        self.assertIn("TopMost", script)  # 置顶 owner，否则对话框会躲在浏览器后面
        self.assertIn("out.txt", script)
        self.assertNotIn("$dialog.SelectedPath = ", script)  # 没给初始目录时不设默认值

    def test_title_quote_escaped(self):
        script = folder_pick.build_script("it's fine", None, Path("C:/tmp/o.txt"))
        self.assertIn("it''s fine", script)

    def test_initial_only_when_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            script = folder_pick.build_script("选目录", tmp, Path("C:/tmp/o.txt"))
            self.assertIn("SelectedPath", script)

    def test_available_flag_is_bool(self):
        self.assertIsInstance(folder_pick.available(), bool)


if __name__ == "__main__":
    unittest.main()
