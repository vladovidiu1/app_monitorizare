"""Fail closed on different wheels before pip installs native code."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    manifest=json.loads((Path(__file__).resolve().parents[1]/'packaging/windows-wheels.json').read_text())
    expected={item['filename']:item['sha256'] for item in manifest['artifacts']}
    actual={p.name for p in args.directory.glob('*.whl')}
    if actual!=set(expected):raise ValueError(f'Unexpected wheel set: {actual ^ set(expected)}')
    for name,digest in expected.items():
        if hashlib.sha256((args.directory/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Wheel SHA256 mismatch: '+name)
    print(f'{len(expected)} locked wheels verified.')


if __name__=='__main__':main()
