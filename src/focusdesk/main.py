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
    from .bootstrap import prepare_multiprocessing

    prepare_multiprocessing()
    parser = argparse.ArgumentParser(prog="focusdesk")
    parser.add_argument("--workspace", type=Path, help="folderul workspace-ului de deschis")
    parser.add_argument("--ai-smoke", type=Path, help="test explicit al modelului local, fără interfață")
    parser.add_argument("--ai-smoke-report", type=Path, help="raport JSON pentru testul executabilului fără consolă")
    parser.add_argument("--ai-timeout", type=int, default=300, help=argparse.SUPPRESS)
    parser.add_argument("--assistant-smoke", choices=["answer", "steps", "email"], help=argparse.SUPPRESS)
    parser.add_argument("--distribution-smoke", choices=["real", "missing"], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.distribution_smoke:
        from .ai.distribution_smoke import run_distribution_smoke
        from .ai.models import default_model_path
        from .storage.atomic import atomic_write_json
        report = run_distribution_smoke(args.ai_smoke or default_model_path(), missing=args.distribution_smoke == "missing", timeout=args.ai_timeout)
        if args.ai_smoke_report:
            atomic_write_json(args.ai_smoke_report, report)
        return 0 if report["status"] == "ok" else 1
    if args.ai_smoke or args.assistant_smoke:
        from .ai.smoke import run_smoke, run_assistant_smoke
        from .ai.models import default_model_path
        from .storage.atomic import atomic_write_json

        report = (run_assistant_smoke(args.ai_smoke or default_model_path(), args.assistant_smoke, args.ai_timeout)
                  if args.assistant_smoke else run_smoke(args.ai_smoke, args.ai_timeout))
        if args.ai_smoke_report:
            atomic_write_json(args.ai_smoke_report, report)
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
