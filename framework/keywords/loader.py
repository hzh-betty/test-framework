from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType


def load_keyword_libraries(config: dict) -> list[object]:
    return _load_objects(config.get("keyword_libraries") or config.get("libraries") or [])


def load_listeners(config: dict) -> list[object]:
    return _load_objects(config.get("listeners") or [])


def _load_objects(entries: object) -> list[object]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError("Runtime config entries must be a list.")
    loaded: list[object] = []
    for entry in entries:
        loaded.extend(_load_entry(entry))
    return loaded


def _load_entry(entry: object) -> list[object]:
    if isinstance(entry, str):
        module = _load_module(entry)
        return _objects_from_module(module)
    if not isinstance(entry, dict):
        raise ValueError("Runtime config entry must be a string or mapping.")
    module_path = entry.get("path") or entry.get("module")
    if not isinstance(module_path, str):
        raise ValueError("Runtime config entry requires 'path' or 'module'.")
    module = _load_module(module_path)
    object_name = entry.get("class") or entry.get("object")
    args = entry.get("args", [])
    kwargs = entry.get("kwargs", {})
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        raise ValueError("Runtime config entry args/kwargs must be list/mapping.")
    if object_name:
        target = getattr(module, str(object_name))
        return [target(*args, **kwargs) if isinstance(target, type) else target]
    return _objects_from_module(module)


def _load_module(module_path: str) -> ModuleType:
    path = Path(module_path)
    if path.suffix == ".py" or path.exists():
        if not path.exists():
            raise ValueError(f"Python module file not found: {path}")
        module_name = f"webtest_user_{path.stem}_{abs(hash(path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load Python module file: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_path)


def _objects_from_module(module: ModuleType) -> list[object]:
    objects: list[object] = [module]
    for value in vars(module).values():
        if isinstance(value, type) and getattr(value, "__keyword_library__", False):
            objects.append(value())
    return objects
