"""Safety and authoritative-result tests; no VM, GUI, or official HTTP calls."""
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_practice as ap
spec = importlib.util.spec_from_file_location('ap_database', ROOT / 'auto_practice_support/database.py')
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)


def row(identifier=1, case='AAAA-BBBB-CCCC-DDDD'):
    return dict(id=identifier, team_no='202623001141', problem_no=3, practice_run_no=100+identifier,
                case_code=case, entered=1, jammer_count=15, cleared_jammer_count=15,
                clear_failure_count=1, virtual_time_us=123456789, end_reason='user_exit', created_at_ms=1)


class Results(unittest.TestCase):
    def test_reject_wrong_or_ambiguous_round(self):
        good = row()
        for changes in ({'case_code':'WRONG'}, {'problem_no':4}, {'team_no':'other'},
                        {'entered':0}, {'end_reason':''}, {'virtual_time_us':-1}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                ap.match_result([], [dict(good, **changes)], good['case_code'], 3, good['team_no'])
        for rows in ([], [good, row(2), row(3)], [good]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                ap.match_result([good], rows, good['case_code'], 3, good['team_no'])

    def test_large_run_number_and_microseconds_preserved(self):
        good = dict(row(), practice_run_no=7587800027227437419, virtual_time_us=3522849773)
        self.assertEqual(ap.match_result([], [good], good['case_code'], 3, good['team_no']), good)

    def test_wal_snapshot_does_not_change_live_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'live.sqlite3'
            with closing(sqlite3.connect(source)) as connection:
                connection.execute('PRAGMA journal_mode=WAL')
                connection.execute('PRAGMA wal_autocheckpoint=0')
                types = {k: ('TEXT' if k in ('team_no','case_code','end_reason') else 'INTEGER') for k in database.COLUMNS}
                connection.execute('CREATE TABLE practice_statistics_tasks (' + ','.join(k+' '+v for k,v in types.items()) + ')')
                good = row()
                connection.execute('INSERT INTO practice_statistics_tasks VALUES (' + ','.join('?' for _ in database.COLUMNS) + ')', [good[k] for k in database.COLUMNS])
                connection.commit()
                paths = [source, Path(str(source)+'-wal'), Path(str(source)+'-shm')]
                before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
                copied = database.snapshot(folder / 'copy', source)
                after = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
                self.assertEqual(before, after)
                self.assertEqual(copied['rows'], [good])
                self.assertFalse(copied['source_opened_by_sqlite'])
                with self.assertRaises(RuntimeError):
                    database.snapshot(folder / 'copy', source)


class Batch(unittest.TestCase):
    def runner(self, folder):
        runner = object.__new__(ap.Runner)
        runner.args = types.SimpleNamespace(execute=True, problem=3, robot_id='202623001141', runs=2)
        runner.directory = folder
        runner.results = []
        runner.setup = lambda: None
        runner.log = lambda *a, **k: None
        return runner

    def test_two_rounds_require_authoritative_match_and_return_between(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.runner(Path(tmp))
            rows = []
            events = []
            r.db = lambda label: list(rows)
            def ui(action, number, expected_case=None):
                events.append((action, number))
                if action == 'dry-run':
                    return dict(ok=True)
                if action == 'run':
                    new = row(number, f'{number:04}-BBBB-CCCC-DDDD')
                    rows.append(new)
                    return dict(case_code=new['case_code'])
                self.assertEqual(expected_case, rows[-1]['case_code'])
                return dict(ok=True)
            r.ui = ui
            r.run()
            self.assertEqual(events, [('dry-run',0),('run',1),('return',1),('run',2),('return',2)])
            self.assertEqual(json.loads((r.directory/'summary.json').read_text())['completed_runs'], 2)

    def test_gui_denial_aborts_batch_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.runner(Path(tmp))
            events = []
            r.db = lambda label: events.append(label) or []
            def deny(*args):
                events.append('DENY_FORMAL')
                raise RuntimeError('DENY_FORMAL')
            r.ui = deny
            with self.assertRaisesRegex(RuntimeError, 'DENY_FORMAL'):
                r.run()
            self.assertEqual(events, ['DENY_FORMAL'])


if __name__ == '__main__':
    unittest.main()
