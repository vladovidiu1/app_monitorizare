"""Verifică spawn din executabil, cu PATH gol; opțional inferență GGUF reală."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--model", type=Path, help="Dacă lipsește, verifică numai eroarea controlată pentru model absent")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--assistant-mode", choices=["answer", "steps", "email"])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="focusdesk-frozen-ai-") as tmp:
        report = Path(tmp) / "result.json"
        model = args.model.resolve() if args.model else Path(tmp) / "absent.gguf"
        env = {**os.environ, "PATH": "", "APPDATA": str(Path(tmp) / "appdata")}
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        command = [str(args.exe.resolve()), "--ai-smoke", str(model), "--ai-smoke-report", str(report),
                   "--ai-timeout", str(args.timeout)]
        if args.assistant_mode:
            command.extend(["--assistant-smoke", args.assistant_mode])
        result = subprocess.run(command, env=env, timeout=args.timeout + 15)
        data = json.loads(report.read_text(encoding="utf-8"))
        if args.model:
            assert result.returncode == 0 and data["status"] == "ok", data
            print("OK: executabil standalone, spawn, încărcare GGUF și inferență reală, PATH gol.")
        else:
            assert result.returncode == 1 and data["status"] == "error" and "absent" in data["error"], data
            print("OK: executabil standalone, spawn și eroare controlată pentru model absent; inferență NETESTATĂ.")
        print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
