"""Page Object 基类。

页面对象应该表达业务动作，例如 ``login`` 或 ``submit_order``。它们通过
``BrowserActions`` 访问浏览器，从而和内置关键字共享同一套 Selenium 封装。
"""

from __future__ import annotations

from webtest_core.browser.actions import BrowserActions
from webtest_core.browser.locators import parse_locator


class BasePage:
    """给偏好 Page Object 模式的团队使用的小型基类。"""

    def __init__(self, actions: BrowserActions):
        self.actions = actions

    def open(self, url: str):
        self.actions.open(url)

    def click(self, locator: str):
        self.actions.click(parse_locator(locator))

    def type_text(self, locator: str, text: str):
        self.actions.type_text(parse_locator(locator), text)
