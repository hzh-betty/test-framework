"""Selenium 浏览器动作封装。

执行器不会直接依赖 Selenium；它只调用关键字。关键字再调用这里的动作封装。
这样 dry-run、单元测试和真实浏览器执行可以共享同一套上层逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from webtest_core.browser.locators import Locator, parse_locator


@dataclass(frozen=True)
class BrowserConfig:
    browser: str = "chrome"
    headless: bool = False
    implicit_wait: int = 10


class BrowserActions:
    """默认 Web 关键字使用的 Selenium 薄封装。"""

    def __init__(self, driver):
        self.driver = driver

    @classmethod
    def create(cls, config: BrowserConfig):
        options = None
        if config.browser == "chrome":
            options = webdriver.ChromeOptions()
            if config.headless:
                options.add_argument("--headless=new")
            driver = webdriver.Chrome(options=options)
        elif config.browser == "firefox":
            options = webdriver.FirefoxOptions()
            if config.headless:
                options.add_argument("-headless")
            driver = webdriver.Firefox(options=options)
        elif config.browser == "edge":
            options = webdriver.EdgeOptions()
            if config.headless:
                options.add_argument("--headless=new")
            driver = webdriver.Edge(options=options)
        else:
            raise ValueError(f"Unsupported browser: {config.browser}")
        driver.implicitly_wait(config.implicit_wait)
        return cls(driver)

    def close_browser(self):
        self.driver.quit()

    def new_browser(self, alias: str = "default"):
        return None

    def switch_browser(self, alias: str):
        return None

    def open(self, url: str):
        self.driver.get(url)

    def click(self, locator: Locator):
        self.driver.find_element(locator.by, locator.value).click()

    def type_text(self, locator: Locator, text: str):
        element = self.driver.find_element(locator.by, locator.value)
        element.clear()
        element.send_keys(text)

    def clear(self, locator: Locator):
        self.driver.find_element(locator.by, locator.value).clear()

    def assert_text(self, locator: Locator, text: str):
        actual = self.driver.find_element(locator.by, locator.value).text
        if text not in actual:
            raise AssertionError(f"Expected {text!r} to be present in {actual!r}")

    def wait_visible(self, locator: Locator, timeout: int | float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((locator.by, locator.value))
        )

    def wait_clickable(self, locator: Locator, timeout: int | float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((locator.by, locator.value))
        )

    def wait_not_visible(self, locator: Locator, timeout: int | float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.invisibility_of_element_located((locator.by, locator.value))
        )

    def wait_text(self, locator: Locator, text: str, timeout: int | float = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.text_to_be_present_in_element((locator.by, locator.value), text)
        )

    def wait_url_contains(self, fragment: str, timeout: int | float = 10):
        return WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))

    def assert_element_visible(self, locator: Locator):
        element = self.driver.find_element(locator.by, locator.value)
        if not element.is_displayed():
            raise AssertionError(f"Expected element to be visible: {locator}")

    def assert_element_contains(self, locator: Locator, text: str):
        self.assert_text(locator, text)

    def assert_url_contains(self, fragment: str):
        if fragment not in self.driver.current_url:
            raise AssertionError(f"Expected URL to contain {fragment!r}")

    def assert_title_contains(self, text: str):
        if text not in self.driver.title:
            raise AssertionError(f"Expected title to contain {text!r}")

    def select(self, locator: Locator, text: str):
        Select(self.driver.find_element(locator.by, locator.value)).select_by_visible_text(text)

    def hover(self, locator: Locator):
        ActionChains(self.driver).move_to_element(
            self.driver.find_element(locator.by, locator.value)
        ).perform()

    def switch_frame(self, target: str):
        if target == "default":
            self.driver.switch_to.default_content()
        elif target == "parent":
            self.driver.switch_to.parent_frame()
        elif target.isdigit():
            self.driver.switch_to.frame(int(target))
        else:
            locator = parse_locator(target)
            self.driver.switch_to.frame(self.driver.find_element(locator.by, locator.value))

    def switch_window(self, target: str):
        if target.isdigit():
            self.driver.switch_to.window(self.driver.window_handles[int(target)])
        else:
            self.driver.switch_to.window(target)

    def accept_alert(self):
        self.driver.switch_to.alert.accept()

    def upload_file(self, locator: Locator, path: str):
        self.driver.find_element(locator.by, locator.value).send_keys(path)

    def screenshot(self, path: str):
        self.driver.save_screenshot(path)


class BrowserSessionActions:
    """支持多浏览器别名的动作代理。

    关键字层始终调用同一个对象；该对象按别名把调用转发到不同的
    ``BrowserActions`` 实例，从而支持 ``New Browser`` 和 ``Switch Browser``。
    """

    def __init__(self, config: BrowserConfig):
        self.config = config
        self._sessions: dict[str, BrowserActions] = {}
        self._current_alias = "default"

    @classmethod
    def create(cls, config: BrowserConfig):
        return cls(config)

    def new_browser(self, alias: str = "default"):
        if alias not in self._sessions:
            self._sessions[alias] = BrowserActions.create(self.config)
        self._current_alias = alias

    def switch_browser(self, alias: str):
        if alias not in self._sessions:
            raise ValueError(f"Unknown browser alias: {alias}")
        self._current_alias = alias

    def close_browser(self):
        if self._current_alias in self._sessions:
            self._sessions.pop(self._current_alias).close_browser()
        if self._sessions:
            self._current_alias = next(iter(self._sessions))

    def close_all(self):
        for actions in list(self._sessions.values()):
            actions.close_browser()
        self._sessions.clear()

    def _actions(self) -> BrowserActions:
        if self._current_alias not in self._sessions:
            self.new_browser(self._current_alias)
        return self._sessions[self._current_alias]

    def __getattr__(self, name: str):
        return getattr(self._actions(), name)
