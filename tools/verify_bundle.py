"""Verify every file in a deployed bundle before running code."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'bundle_manifest.json').read_text(encoding='utf8'))
    bad = [n for n,h in manifest.items() if not (root/n).is_file()
           or hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
    if bad:
        raise RuntimeError(f'Bundle files differ: {bad}')
    print(json.dumps(dict(verified_files=len(manifest),official_requests=0)))


if __name__ == '__main__':
    main()
