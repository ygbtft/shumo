"""Copy formal upload DB bytes first. SQLite NEVER opens a live simulator path."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import tempfile

LIVE_DB = Path(r'C:\Jammers\JammersSimulatorData\upload-queue.sqlite3')
COLUMNS = ('kind', 'problem_no', 'formal_index', 'case_code', 'package_sha256', 'package_bytes', 'formal_upload_state', 'state', 'attempt_count', 'last_error_code', 'received_at_ms')


def snapshot(destination, source=LIVE_DB):
    destination = Path(destination)
    if destination.exists() or destination.resolve() == source.parent.resolve():
        raise RuntimeError('Snapshot must use a fresh isolated directory')
    destination.mkdir(parents=True)
    for attempt in range(10):
        bundles = []
        for name in ('a', 'b'):
            folder = destination / f'{attempt}-{name}'
            folder.mkdir()
            hashes = {}
            for suffix in ('', '-wal'):
                original = Path(str(source) + suffix)
                if original.exists():
                    target = folder / (source.name + suffix)
                    # Ordinary read-only file handles, never connect to the live SQLite DB.
                    shutil.copyfile(original, target)
                    hashes[suffix] = hashlib.sha256(target.read_bytes()).hexdigest()
            bundles.append((folder, hashes))
        if bundles[0][1] == bundles[1][1] and '' in bundles[0][1]:
            copied = bundles[1][0] / source.name
            with closing(sqlite3.connect(copied.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
                connection.execute('PRAGMA query_only=ON')
                if connection.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise RuntimeError('Snapshot failed SQLite quick_check')
                connection.row_factory = sqlite3.Row
                rows = [dict(row) for row in connection.execute(
                    'SELECT ' + ','.join(COLUMNS) + " FROM upload_tasks WHERE kind='formal_behavior' AND problem_no=3 AND case_code='G4MK-ZVXM-A682-MVBS'")]
            result = dict(rows=rows, copied_database=str(copied), sha256=bundles[1][1],
                          source_opened_by_sqlite=False)
            (destination / 'rows.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
            return result
        time.sleep(.2)
    raise RuntimeError('Live DB changing: no stable double-copy snapshot; no query performed')


if __name__ == '__main__':
    export = Path(sys.argv[1])
    # SQLite URI/WAL locking on Parallels UNC shares is unsupported. Query local copies.
    with tempfile.TemporaryDirectory(prefix='auto-practice-db-') as temporary:
        local = Path(temporary) / 'snapshot'
        snapshot(local)
        shutil.copytree(local, export)
