"""Descărcare explicită a unui singur GGUF, reluabilă și verificată înainte de publicare."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .models import ModelManifest, validate_location, verify_file


def resolve_manifest(destination: Path, *, opener=urllib.request.urlopen) -> ModelManifest:
    """Nu ghicește nume/revizii/hash-uri. Scrie doar după validarea metadatelor reale."""
    repository = "Qwen/Qwen3-8B-GGUF"
    wanted = "qwen3-8b-q4_k_m.gguf"
    with opener(f"https://huggingface.co/api/models/{repository}?blobs=true", timeout=30) as response:
        info = json.load(response)
    candidates = [item for item in info["siblings"] if item["rfilename"].casefold() == wanted.casefold()]
    if len(candidates) != 1:
        raise ValueError(f"Fișierul {wanted} nu există ca fișier unic în catalogul furnizorului.")
    item = candidates[0]
    lfs = item.get("lfs", {})
    manifest = ModelManifest(
        repository=repository, requested_filename=wanted, filename=item["rfilename"],
        revision=info["sha"], sha256=lfs.get("sha256"), size=lfs.get("size"),
        license=info.get("cardData", {}).get("license"),
    ).require_verified()
    # Provider model card is retained with the resolved immutable revision.
    card_url = f"https://huggingface.co/{repository}/raw/{manifest.revision}/README.md"
    with opener(card_url, timeout=30) as response:
        card = response.read()
    license_url = f"https://huggingface.co/{repository}/raw/{manifest.revision}/LICENSE"
    with opener(license_url, timeout=30) as response:
        license_text = response.read()
    if manifest.license != "apache-2.0" or b"Apache License" not in license_text:
        raise ValueError("Licența furnizorului necesită verificare înainte de distribuție.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    card_path = destination.parent / "Qwen3-MODEL-CARD.md"
    card_path.write_bytes(card)
    (destination.parent / "Qwen3-LICENSE.txt").write_bytes(license_text)
    payload = {**manifest.model_dump(), "status": "verified", "metadata_source":
               f"https://huggingface.co/api/models/{repository}/revision/{manifest.revision}?blobs=true"}
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return manifest


def download_model(manifest: ModelManifest, directory: Path, *, progress=None,
                   opener=urllib.request.urlopen, attempts: int = 3) -> Path:
    manifest.require_verified()
    target = validate_location(directory / manifest.filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            verify_file(target, manifest, progress)
            return target
        except ValueError:
            pass  # Leave the existing file intact until a valid replacement is available.
    partial = target.with_name(target.name + f".{manifest.sha256[:16]}.part")
    url = (f"https://huggingface.co/{manifest.repository}/resolve/{manifest.revision}/"
           f"{urllib.parse.quote(manifest.filename)}?download=true")
    for attempt in range(attempts):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == manifest.size:
            break
        if offset > manifest.size:
            partial.unlink()
            offset = 0
        request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            with opener(request, timeout=60) as response:
                if response.status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != offset or int(match[3]) != manifest.size:
                        raise ValueError("Serverul a returnat un interval de reluare incorect.")
                elif response.status == 200:
                    offset = 0  # Server ignores Range: restart rather than append a duplicate.
                else:
                    raise ValueError(f"Răspuns HTTP neașteptat: {response.status}")
                with partial.open("ab" if offset else "wb") as output:
                    if progress:
                        progress(offset, manifest.size)
                    while block := response.read(1024 * 1024):
                        if offset + len(block) > manifest.size:
                            raise ValueError("Descărcarea depășește dimensiunea din manifest.")
                        output.write(block)
                        offset += len(block)
                        if progress:
                            progress(offset, manifest.size)
                    output.flush()
                    os.fsync(output.fileno())
            if offset != manifest.size:
                raise OSError("Descărcare întreruptă înainte de dimensiunea așteptată.")
            break
        except (OSError, urllib.error.URLError):
            if attempt + 1 == attempts:
                raise
            time.sleep(min(attempt + 1, 2))
    try:
        verify_file(partial, manifest, progress)
    except ValueError:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, target)
    return target
