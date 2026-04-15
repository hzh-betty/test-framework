from __future__ import annotations

from pathlib import Path

import yaml


def load_runtime_config(config_path: str | None) -> dict:
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError("Config root must be a mapping object.")
    return content
