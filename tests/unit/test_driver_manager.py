import unittest

from framework.selenium.driver_manager import DriverConfig, DriverManager


class FakeDriver:
    def __init__(self):
        self.implicit_wait_value = None
        self.maximized = False
        self.quitted = False

    def implicitly_wait(self, value: int):
        self.implicit_wait_value = value

    def maximize_window(self):
        self.maximized = True

    def quit(self):
        self.quitted = True


class TestDriverManager(unittest.TestCase):
    def test_create_driver_applies_defaults(self):
        fake_driver = FakeDriver()
        manager = DriverManager(factories={"chrome": lambda _headless: fake_driver})
        config = DriverConfig(browser="chrome", headless=True, implicit_wait=5)

        driver = manager.create_driver(config)

        self.assertIs(driver, fake_driver)
        self.assertEqual(fake_driver.implicit_wait_value, 5)
        self.assertTrue(fake_driver.maximized)

    def test_quit_driver_is_safe(self):
        fake_driver = FakeDriver()
        DriverManager().quit_driver(fake_driver)
        self.assertTrue(fake_driver.quitted)


if __name__ == "__main__":
    unittest.main()
