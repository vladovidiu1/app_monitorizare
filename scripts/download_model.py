"""Descărcare explicită; nu se execută automat la pornirea FocusDesk."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from focusdesk.ai.download import download_model, resolve_manifest
from focusdesk.ai.models import models_dir, read_manifest
from focusdesk.config import resource_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve-manifest", action="store_true", help="Obține numele exact, revizia și SHA256 de la HF")
    parser.add_argument("--metadata-only", action="store_true", help="Nu descarcă GGUF-ul")
    parser.add_argument("--directory", type=Path, default=models_dir())
    args = parser.parse_args()
    try:
        manifest = resolve_manifest(resource_path("ai-model.json")) if args.resolve_manifest else read_manifest()
        manifest.require_verified()
        print(f"Model: {manifest.repository}/{manifest.filename}\nRevizie: {manifest.revision}\nSHA256: {manifest.sha256}")
        if not args.metadata_only:
            last = [-1]
            def progress(done, total):
                percent = int(done * 100 / total)
                if percent != last[0]:
                    print(f"\rDescărcare/verificare: {percent:3d}% ({done:,}/{total:,} octeți)", end="", flush=True)
                    last[0] = percent
            target = download_model(manifest, args.directory, progress=progress)
            print(f"\nModel verificat: {target}")
        return 0
    except Exception as exc:
        print(f"Model indisponibil: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
