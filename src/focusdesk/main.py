"""Punct de intrare FocusDesk."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from .config import app_data_dir


def _setup_logging() -> None:
    log_dir = app_data_dir() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(log_dir / "focusdesk.log", maxBytes=1_000_000, backupCount=3,
                                                       encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focusdesk")
    parser.add_argument("--workspace", type=Path, help="folderul workspace-ului de deschis")
    args = parser.parse_args(argv)
    _setup_logging()
    from .ui.app import FocusDeskApp

    try:
        FocusDeskApp(args.workspace).run()
    except Exception:
        logging.getLogger("focusdesk").exception("Eroare fatală")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
