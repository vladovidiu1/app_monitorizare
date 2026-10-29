"""Punct de intrare FocusDesk."""

from __future__ import annotations

from .i18n import tr

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
    parser.add_argument('--workspace', type=Path, help=tr('extra.main.folderul_workspace_ului_de_deschis'))
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.smoke_test:
        from .smoke import run_smoke
        from .storage.atomic import atomic_write_json
        report = run_smoke()
        if args.smoke_report:
            atomic_write_json(args.smoke_report, report)
        else:
            import json
            print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "ok" else 1
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
