#!/usr/bin/env python3
"""Validate repository files; optionally compile the G1 model."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_files() -> None:
    records = json.loads((ROOT / '.repository-manifest.json').read_text())['files']
    for record in records:
        path = ROOT / record['path']
        require(path.is_file(), f'Missing file: {record["path"]}')
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == record['sha256'], f'Checksum mismatch: {record["path"]}')
    print(f'PASS: {len(records)} migrated file checksums')


def validate_model() -> None:
    import g1_model

    model = g1_model.load_g1()
    require(model.nq == 36, 'Expected floating root plus 29 joints')
    print(f'PASS: bundled G1 model compiled (nq={model.nq}, nv={model.nv})')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='store_true', help='compile bundled XML; requires mujoco and numpy')
    args = parser.parse_args()
    try:
        validate_files()
        if args.model:
            validate_model()
    except (ValueError, OSError, KeyError, ImportError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
