from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DriverConfig:
    browser: str = "chrome"
    headless: bool = False
    implicit_wait: int = 10


DriverFactory = Callable[[bool], object]


class DriverManager:
    def __init__(self, factories: dict[str, DriverFactory] | None = None):
        self._factories = factories or {
            "chrome": self._create_chrome,
            "firefox": self._create_firefox,
            "edge": self._create_edge,
        }

    def create_driver(self, config: DriverConfig) -> object:
        if config.browser not in self._factories:
            raise ValueError(f"Unsupported browser: {config.browser}")
        driver = self._factories[config.browser](config.headless)
        driver.implicitly_wait(config.implicit_wait)
        driver.maximize_window()
        return driver

    def quit_driver(self, driver: object | None) -> None:
        if driver is not None:
            driver.quit()

    def _create_chrome(self, headless: bool) -> object:
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        return webdriver.Chrome(options=options)

    def _create_firefox(self, headless: bool) -> object:
        from selenium import webdriver

        options = webdriver.FirefoxOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--width=1920")
        options.add_argument("--height=1080")
        return webdriver.Firefox(options=options)

    def _create_edge(self, headless: bool) -> object:
        from selenium import webdriver

        options = webdriver.EdgeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        return webdriver.Edge(options=options)
