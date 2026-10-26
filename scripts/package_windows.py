"""Audit an allowlisted onedir, create a ZIP archive and SHA256 checksum."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

ALLOWED_ROOT = {'FocusDesk.exe', '_internal', 'licenses', 'build-info.json', 'CITESTE-MA.txt'}


def audit(bundle):
    actual = {p.name for p in bundle.iterdir()}
    if not actual <= ALLOWED_ROOT or 'FocusDesk.exe' not in actual:
        raise ValueError(f'Unexpected distribution entries: {actual - ALLOWED_ROOT}')
    forbidden = {'workspace.json', 'app.json', 'state.json', '.env', 'credentials.json'}
    for path in bundle.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink found in distribution: ' + str(path))
        if path.is_file() and path.name.lower() in forbidden:
            raise ValueError('Personal/workspace data found in distribution: ' + str(path))
        if path.suffix.lower() in {'.gguf', '.part'}:
            raise ValueError('Unexpected large data file: ' + str(path))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def archive(bundle, destination):
    audit(bundle)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as output:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                output.write(path, arcname='FocusDesk/' + path.relative_to(bundle).as_posix())
    with zipfile.ZipFile(destination) as check:
        bad = check.testzip()
        if bad:
            raise ValueError('Archive CRC mismatch: ' + bad)
    destination.with_suffix('.zip.sha256').write_text(
        sha256(destination) + '  ' + destination.name + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.bundle)
    args.output.mkdir(parents=True, exist_ok=True)
    expected = sum(p.stat().st_size for p in args.bundle.rglob('*') if p.is_file())
    if shutil.disk_usage(args.output).free < expected + 256 * 1024 * 1024:
        raise RuntimeError('Insufficient disk for archive')
    archive(args.bundle, args.output / 'FocusDesk-Windows-x64.zip')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
