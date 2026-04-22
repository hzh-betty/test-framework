import unittest

from framework.core.time import parse_positive_timeout, parse_time


class TestTimeUtils(unittest.TestCase):
    def test_parse_time_supports_numbers_and_units(self):
        self.assertEqual(parse_time(2), 2.0)
        self.assertEqual(parse_time("500ms"), 0.5)
        self.assertEqual(parse_time("2s"), 2.0)
        self.assertEqual(parse_time("1 minute"), 60.0)
        self.assertEqual(parse_time("00:00:03"), 3.0)

    def test_parse_time_rejects_invalid_value(self):
        with self.assertRaisesRegex(ValueError, "Invalid time value 'soon'"):
            parse_time("soon")

    def test_parse_positive_timeout_rejects_zero_or_negative(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            parse_positive_timeout("0")
        with self.assertRaisesRegex(ValueError, "must be positive"):
            parse_positive_timeout("-1s")


if __name__ == "__main__":
    unittest.main()
