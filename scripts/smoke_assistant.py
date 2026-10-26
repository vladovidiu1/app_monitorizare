"""Smoke AI real pentru chat/surse; date temporare, fără aplicare de propuneri."""

import argparse
import json
import multiprocessing
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from focusdesk.ai.models import default_model_path
    from focusdesk.ai.smoke import run_assistant_smoke

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["answer", "steps", "email"], default="answer")
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    report = run_assistant_smoke(args.model, args.mode, args.timeout)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
