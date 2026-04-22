import unittest

from framework.selenium.driver_manager import DriverConfig
from framework.selenium.session import BrowserSessionError, BrowserSessionManager


class FakeDriver:
    def __init__(self, name: str):
        self.name = name
        self.quitted = False

    def quit(self):
        self.quitted = True


class FakeDriverManager:
    def __init__(self):
        self.created: list[FakeDriver] = []
        self.quitted: list[FakeDriver] = []

    def create_driver(self, _config):
        driver = FakeDriver(f"driver-{len(self.created) + 1}")
        self.created.append(driver)
        return driver

    def quit_driver(self, driver):
        driver.quit()
        self.quitted.append(driver)


class FakeActions:
    def __init__(self, driver):
        self.driver = driver


class TestBrowserSessionManager(unittest.TestCase):
    def test_open_browser_registers_alias_and_sets_current(self):
        driver_manager = FakeDriverManager()
        sessions = BrowserSessionManager(
            driver_manager=driver_manager,
            driver_config=DriverConfig(),
            actions_factory=FakeActions,
        )

        actions = sessions.open_browser("admin")

        self.assertEqual(actions.driver.name, "driver-1")
        self.assertEqual(sessions.current_alias, "admin")

    def test_switch_browser_accepts_alias(self):
        driver_manager = FakeDriverManager()
        sessions = BrowserSessionManager(driver_manager, DriverConfig(), FakeActions)
        sessions.open_browser("first")
        sessions.open_browser("second")

        actions = sessions.switch_browser("first")

        self.assertEqual(actions.driver.name, "driver-1")
        self.assertEqual(sessions.current_alias, "first")

    def test_current_actions_can_lazily_open_default_browser(self):
        driver_manager = FakeDriverManager()
        sessions = BrowserSessionManager(driver_manager, DriverConfig(), FakeActions)

        actions = sessions.current_actions(create_default=True)

        self.assertEqual(actions.driver.name, "driver-1")
        self.assertEqual(sessions.current_alias, "default")

    def test_close_browser_removes_session_and_quits_driver(self):
        driver_manager = FakeDriverManager()
        sessions = BrowserSessionManager(driver_manager, DriverConfig(), FakeActions)
        sessions.open_browser("default")

        sessions.close_browser("default")

        self.assertTrue(driver_manager.created[0].quitted)
        with self.assertRaisesRegex(BrowserSessionError, "No current browser session"):
            sessions.current_actions()

    def test_close_all_quits_all_sessions(self):
        driver_manager = FakeDriverManager()
        sessions = BrowserSessionManager(driver_manager, DriverConfig(), FakeActions)
        sessions.open_browser("first")
        sessions.open_browser("second")

        sessions.close_all()

        self.assertEqual(len(driver_manager.quitted), 2)
        self.assertTrue(all(driver.quitted for driver in driver_manager.created))


if __name__ == "__main__":
    unittest.main()
