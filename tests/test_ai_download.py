from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from focusdesk.ai.download import download_model, resolve_manifest
from focusdesk.ai.models import ModelManifest, read_manifest, validate_location


class Reply(io.BytesIO):
    def __init__(self, content, status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}


def manifest(data=b"GGUF: verified test payload"):
    return ModelManifest(repository="Qwen/Qwen3-8B-GGUF", requested_filename="qwen3-8b-q4_k_m.gguf",
        filename="Qwen3-8B-Q4_K_M.gguf", revision="a" * 40, sha256=hashlib.sha256(data).hexdigest(),
        size=len(data), license="apache-2.0")


def test_resume_validates_range_hash_and_reuses_existing_file(tmp_path):
    payload = b"GGUF: verified test payload"
    m = manifest(payload)
    part = tmp_path / (m.filename + f".{m.sha256[:16]}.part")
    part.write_bytes(payload[:7])
    calls = []
    def opener(req, **kw):
        calls.append(req)
        assert req.get_header("Range") == "bytes=7-"
        assert "/resolve/" + m.revision + "/" in req.full_url
        return Reply(payload[7:], 206, {"Content-Range": f"bytes 7-{len(payload)-1}/{len(payload)}"})
    progress = []
    target = download_model(m, tmp_path, opener=opener, progress=lambda a, b: progress.append((a, b)))
    assert target.read_bytes() == payload and not part.exists()
    assert progress[-1] == (len(payload), len(payload))
    assert download_model(m, tmp_path, opener=lambda *a, **k: pytest.fail("must reuse")) == target
    assert len(calls) == 1


def test_server_ignoring_range_restarts_instead_of_appending(tmp_path):
    payload = b"GGUF: verified test payload"
    m = manifest(payload)
    (tmp_path / (m.filename + f".{m.sha256[:16]}.part")).write_bytes(payload[:3])
    target = download_model(m, tmp_path, opener=lambda *a, **k: Reply(payload))
    assert target.read_bytes() == payload


def test_corrupt_download_never_replaces_existing_file(tmp_path):
    payload = b"GGUF: verified test payload"
    m = manifest(payload)
    target = tmp_path / m.filename
    target.write_bytes(b"existing file")
    with pytest.raises(ValueError, match="SHA256"):
        download_model(m, tmp_path, opener=lambda *a, **k: Reply(b"X" * len(payload)))
    assert target.read_bytes() == b"existing file"
    assert not list(tmp_path.glob("*.part"))


def test_incomplete_transfer_is_retained_then_resumed(tmp_path):
    payload = b"GGUF: verified test payload"
    m = manifest(payload)
    with pytest.raises(OSError, match="întreruptă"):
        download_model(m, tmp_path, attempts=1, opener=lambda *a, **k: Reply(payload[:5]))
    assert list(tmp_path.glob("*.part"))[0].read_bytes() == payload[:5]
    target = download_model(m, tmp_path, opener=lambda *a, **k: Reply(payload[5:], 206,
        {"Content-Range": f"bytes 5-{len(payload)-1}/{len(payload)}"}))
    assert target.read_bytes() == payload


def test_incorrect_range_is_rejected(tmp_path):
    m = manifest()
    with pytest.raises(ValueError, match="interval"):
        download_model(m, tmp_path, opener=lambda *a, **k: Reply(b"abc", 206, {"Content-Range": "bytes 8-10/11"}))
    assert not (tmp_path / m.filename).exists()


def test_metadata_resolver_uses_provider_case_revision_hash_and_license(tmp_path):
    m = manifest()
    metadata = {"sha": m.revision, "cardData": {"license": m.license}, "siblings": [
        {"rfilename": m.filename, "lfs": {"sha256": m.sha256, "size": m.size}}]}
    def opener(url, **kwargs):
        if "/api/models/" in url:
            return Reply(json.dumps(metadata).encode())
        assert m.revision in url
        return Reply(b"Apache License" if url.endswith("LICENSE") else b"Qwen3 model card")
    dest = tmp_path / "ai-model.json"
    result = resolve_manifest(dest, opener=opener)
    assert read_manifest(dest) == result == m
    assert (tmp_path / "Qwen3-LICENSE.txt").exists()


def test_missing_metadata_does_not_overwrite_manifest(tmp_path):
    dest = tmp_path / "ai-model.json"
    dest.write_text("existing")
    with pytest.raises(ValueError):
        resolve_manifest(dest, opener=lambda *a, **k: Reply(b'{"siblings": []}'))
    assert dest.read_text() == "existing"


def test_manifest_and_location_reject_unsafe_or_unverified_values(tmp_path):
    with pytest.raises(ValueError, match="metadate"):
        ModelManifest(repository="Qwen/Qwen3-8B-GGUF", requested_filename="model.gguf").require_verified()
    (tmp_path / "workspace.json").write_text("{}")
    with pytest.raises(ValueError, match="workspace"):
        validate_location(tmp_path / "models" / "model.gguf")
