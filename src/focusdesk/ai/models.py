"""Manifest verificabil și căi ale modelului, independente de workspace/PyInstaller temp."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..config import resource_path


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    repository: str
    requested_filename: str
    filename: str | None = None
    revision: str | None = None
    sha256: str | None = None
    size: int | None = Field(default=None, gt=0)
    license: str | None = None

    def require_verified(self) -> "ModelManifest":
        import re

        if (self.repository != "Qwen/Qwen3-8B-GGUF" or not self.filename
                or Path(self.filename).name != self.filename or "\\" in self.filename
                or not self.filename.lower().endswith(".gguf")
                or not re.fullmatch(r"[0-9a-f]{40}", self.revision or "")
                or not re.fullmatch(r"[0-9a-f]{64}", self.sha256 or "")
                or not self.size or not self.license):
            raise ValueError("Manifestul modelului nu are metadate verificate. Rulează scripts/download_model.py --resolve-manifest.")
        return self


def read_manifest(path: Path | None = None) -> ModelManifest:
    return ModelManifest.model_validate_json((path or resource_path("ai-model.json")).read_bytes())


def models_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "models"
    return Path(__file__).resolve().parents[3] / "models"


def default_model_path() -> Path:
    manifest = read_manifest()
    return models_dir() / (manifest.filename or manifest.requested_filename)


def validate_location(path: Path) -> Path:
    path = path.expanduser().resolve()
    for parent in (path.parent, *path.parents):
        if (parent / "workspace.json").exists():
            raise ValueError("Modelul trebuie păstrat în afara workspace-ului și backupurilor sale.")
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        if path.is_relative_to(Path(sys._MEIPASS).resolve()):
            raise ValueError("Modelul nu se păstrează în directorul temporar PyInstaller.")
    return path


def verify_file(path: Path, manifest: ModelManifest, progress=None) -> None:
    manifest.require_verified()
    if not path.is_file() or path.stat().st_size != manifest.size:
        raise ValueError("Model absent sau incomplet. Descarcă GGUF-ul și verifică manifestul.")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
            count += len(block)
            if progress:
                progress(count, manifest.size)
    if digest.hexdigest() != manifest.sha256:
        raise ValueError("SHA256 al modelului nu corespunde manifestului; fișierul nu va fi încărcat.")
