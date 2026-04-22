from __future__ import annotations

import inspect
import json
from pathlib import Path

from .registry import KeywordRegistry


def export_keyword_docs(registry: KeywordRegistry, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "name": definition.name,
            "source": definition.source,
            "signature": str(inspect.signature(definition.callable)),
            "doc": inspect.getdoc(definition.callable) or "",
        }
        for definition in (registry.get(name) for name in registry.keyword_names)
    ]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
