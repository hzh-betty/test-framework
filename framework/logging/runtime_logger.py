from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path


@dataclass(frozen=True)
class FailureContext:
    url: str
    locator: str
    screenshot_path: str
    error: str

    def to_log_message(self) -> str:
        return (
            "step_failure "
            f"url={self.url} locator={self.locator} "
            f"screenshot={self.screenshot_path} error={self.error}"
        )


def configure_runtime_logger(
    logger_name: str = "framework.runtime",
    level: str = "INFO",
    log_file: str = "artifacts/runtime.log",
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper()))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
