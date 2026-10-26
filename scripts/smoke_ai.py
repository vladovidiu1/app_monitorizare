"""Smoke real, explicit: CPU + GGUF verificat + IPC spawn; fără mock sau workspace."""

from __future__ import annotations

import argparse
import multiprocessing
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    from focusdesk.ai.models import default_model_path
    from focusdesk.ai.smoke import run_smoke

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=default_model_path())
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    import json
    report = run_smoke(args.model, args.timeout)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
