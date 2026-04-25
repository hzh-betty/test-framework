"""元素定位器解析。

用例作者写的是 ``id=username`` 或 ``css=.submit`` 这样的文本；浏览器层
需要把它转换成 Selenium 能理解的 ``By`` 和定位值。
"""

from __future__ import annotations

from dataclasses import dataclass

from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class Locator:
    by: str
    value: str


LOCATOR_STRATEGIES = {
    "id": By.ID,
    "name": By.NAME,
    "css": By.CSS_SELECTOR,
    "xpath": By.XPATH,
    "class": By.CLASS_NAME,
    "tag": By.TAG_NAME,
    "link": By.LINK_TEXT,
    "partial_link": By.PARTIAL_LINK_TEXT,
}


def parse_locator(raw: str) -> Locator:
    """解析 ``prefix=value`` 定位器；没有前缀时默认按 CSS 处理。"""

    if "=" not in raw:
        return Locator(By.CSS_SELECTOR, raw)
    prefix, value = raw.split("=", 1)
    if prefix == "text":
        return Locator(By.XPATH, f"//*[normalize-space(.)={_xpath_literal(value)}]")
    if prefix == "partial_text":
        return Locator(By.XPATH, f"//*[contains(normalize-space(.), {_xpath_literal(value)})]")
    if prefix in {"testid", "data-testid"}:
        return Locator(By.CSS_SELECTOR, f"[data-testid={_css_string(value)}]")
    if prefix not in LOCATOR_STRATEGIES:
        raise ValueError(f"Unknown locator strategy: {prefix}")
    return Locator(LOCATOR_STRATEGIES[prefix], value)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in parts) + ")"


def _css_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
