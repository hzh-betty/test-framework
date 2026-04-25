"""浏览器层公共 API。

实现拆分为定位器、动作封装和 Page Object 基类；这里仅保留稳定导出。
"""

from webtest_core.browser.actions import BrowserActions, BrowserConfig, BrowserSessionActions
from webtest_core.browser.locators import LOCATOR_STRATEGIES, Locator, parse_locator
from webtest_core.browser.page import BasePage

__all__ = [
    "BasePage",
    "BrowserActions",
    "BrowserConfig",
    "BrowserSessionActions",
    "LOCATOR_STRATEGIES",
    "Locator",
    "parse_locator",
]
