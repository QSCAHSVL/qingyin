import unittest

from cover_pipeline import config


class ConfigValidateTest(unittest.TestCase):
    def test_valid_config_passes(self):
        self.assertEqual(config.validate({"project": {}, "server": {"port": 7801}}), [])

    def test_wrong_section_type(self):
        problems = config.validate({"separate": "uvr"})
        self.assertTrue(any("separate" in p for p in problems))

    def test_wrong_field_type(self):
        problems = config.validate({"server": {"port": "7801"}})
        self.assertTrue(any("server.port" in p for p in problems))

    def test_load_rejects_bad_override(self):
        with self.assertRaises(config.ConfigError):
            config.load_config(overrides={"server": {"port": "abc"}})

    def test_real_config_loads(self):
        cfg = config.load_config()
        self.assertIn("project", cfg)


if __name__ == "__main__":
    unittest.main()
