import unittest

from framework.cli.main import build_parser


class TestCliBootstrap(unittest.TestCase):
    def test_parser_accepts_required_dsl_path_and_optional_config(self):
        parser = build_parser()
        args = parser.parse_args(["examples/cases/login.xml", "--config", "examples/config/dev.yaml"])
        self.assertEqual(args.dsl_path, "examples/cases/login.xml")
        self.assertEqual(args.config, "examples/config/dev.yaml")

    def test_parser_exposes_runtime_options(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "examples/cases/login.xml",
                "--browser",
                "chrome",
                "--headless",
                "--log-level",
                "DEBUG",
            ]
        )
        self.assertEqual(args.browser, "chrome")
        self.assertTrue(args.headless)
        self.assertEqual(args.log_level, "DEBUG")


if __name__ == "__main__":
    unittest.main()
