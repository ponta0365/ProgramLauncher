from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(base_dir: Path) -> Path:
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    logging.getLogger(__name__).info("logging started")
    return log_path


def install_exception_hook() -> None:
    logger = logging.getLogger("launcher.unhandled")
    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        logger.exception("unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception
