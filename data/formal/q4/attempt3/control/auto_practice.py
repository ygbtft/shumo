#!/usr/bin/env python3
"""Fail-closed GUI practice runner for the already logged-in Windows 11 guest."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
PRLCTL = '/Applications/Parallels Desktop.app/Contents/MacOS/prlctl'
VM = 'Windows 11'
TRANSFER = Path.home() / 'Downloads' / 'AutoPractice'
SUPPORT = ROOT / 'auto_practice_support'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def guest(command, timeout=60):
    result = subprocess.run([PRLCTL, 'exec', VM, 'cmd.exe', '/c',
                             'chcp 65001 >nul & ' + command],
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Guest command failed: ' + result.stdout.decode('utf8', 'replace') +
                           result.stderr.decode('utf8', 'replace'))
    return result.stdout.decode('utf8', 'replace')


def psquote(value):
    return "'" + str(value).replace("'", "''") + "'"


def match_result(before, after, case_code, problem, team):
    prior = {row['id'] for row in before}
    new = [r for r in after if r['id'] not in prior]
    if len(new) != 1:
        raise RuntimeError(f'Expected exactly one new authoritative row; found {len(new)}')
    row = new[0]
    if (row['case_code'] != case_code or int(row['problem_no']) != problem or
            str(row['team_no']) != team or int(row['entered']) != 1):
        raise RuntimeError('Authoritative row does not match UI case/problem/team/entered')
    for name in ('jammer_count', 'cleared_jammer_count', 'clear_failure_count', 'virtual_time_us'):
        if not isinstance(row[name], int) or row[name] < 0:
            raise RuntimeError(f'Invalid authoritative field: {name}')
    if not row['end_reason']:
        raise RuntimeError('Authoritative row is not final')
    return row


class Runner:
    def __init__(self, args):
        self.args = args
        self.name = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        self.directory = TRANSFER / self.name
        self.directory.mkdir(parents=True)
        self.evidence = ROOT / 'auto_practice_evidence' / self.name
        self.unc = '\\\\Mac\\Home\\Downloads\\AutoPractice\\' + self.name
        self.guest_dir = 'C:\\BRobot\\auto-practice\\' + self.name
        self.task = 'AutoPractice-' + self.name
        self.counter = 0
        self.results = []
        self.lock = None

    def log(self, event, **data):
        row = dict(time=datetime.now().astimezone().isoformat(), event=event, **data)
        with (self.directory / 'host-decisions.jsonl').open('a', encoding='utf8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(event, json.dumps(data, ensure_ascii=False), flush=True)

    def setup(self):
        # macOS advisory process lock: released automatically even on host crash.
        import fcntl
        self.lock = (TRANSFER / 'runner.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ('ui.ps1', 'database.py'):
            shutil.copyfile(SUPPORT / name, self.directory / name)
        guest(f'mkdir "{self.guest_dir}" & copy /Y "{self.unc}\\ui.ps1" "{self.guest_dir}\\ui.ps1" >nul & copy /Y "{self.unc}\\database.py" "{self.guest_dir}\\database.py" >nul')
        write_json(self.directory / 'source-hashes.json', {
            name: hashlib.sha256((self.directory / name).read_bytes()).hexdigest()
            for name in ('ui.ps1', 'database.py')})

    def db(self, label):
        destination = self.unc + '\\' + label
        guest(f'C:\\Python314-arm64\\python.exe -B "{self.guest_dir}\\database.py" "{destination}"')
        result = read_json(self.directory / label / 'rows.json')
        self.log('READ_ONLY_DB_COPY', label=label, rows=len(result['rows']))
        return result['rows']

    def ui(self, action, number, expected_case=None):
        self.counter += 1
        job_name = f'{self.counter:03d}-{number}-{action}'
        folder = self.directory / job_name
        folder.mkdir()
        job_unc = self.unc + '\\' + job_name
        write_json(folder / 'job.json', dict(action=action, problem=self.args.problem,
                   robot_id=self.args.robot_id, policy='formal-q4-once', expected_case=expected_case))
        # schtasks /it creates an InteractiveToken job; settings prevent battery queueing.
        # No time trigger remains: explicitly remove it before the only manual /run.
        tr = f'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{self.guest_dir}\\ui.ps1" -JobDir "{job_unc}"'
        launcher = f'''$ErrorActionPreference='Stop'
$tokens=$null;$parseErrors=$null
[System.Management.Automation.Language.Parser]::ParseFile({psquote(self.guest_dir + chr(92) + 'ui.ps1')},[ref]$tokens,[ref]$parseErrors)|Out-Null
if($parseErrors.Count){{throw ($parseErrors|Out-String)}}
$tr={psquote(tr)}
& schtasks.exe /create /tn {psquote(self.task)} /tr $tr /sc ONCE /st 23:59 /ru flower /it /f | Out-Null
if($LASTEXITCODE -ne 0){{throw 'CREATE_TASK_FAILED'}}
$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 23)
$t=Get-ScheduledTask -TaskName {psquote(self.task)}
$t.Triggers=@()
$t.Settings=$s
Set-ScheduledTask -InputObject $t | Out-Null
& schtasks.exe /run /tn {psquote(self.task)} | Out-Null
if($LASTEXITCODE -ne 0){{throw 'RUN_TASK_FAILED'}}
'''
        (self.directory / 'launch.ps1').write_text(launcher, encoding='utf-8-sig')
        guest(f'copy /Y "{self.unc}\\launch.ps1" "{self.guest_dir}\\launch.ps1" >nul & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{self.guest_dir}\\launch.ps1"')
        self.log('GUI_JOB', action=action, folder=job_name)
        deadline = time.monotonic() + (22 * 60 if action == 'run' else 60)
        heartbeat = 0
        while not (folder / 'result.json').exists():
            if os.environ.get('AUTO_PRACTICE_POLICY', 'practice-only') != 'practice-only' or (self.directory / 'STOP').exists():
                (folder / 'STOP').touch()
            if time.monotonic() > deadline:
                (folder / 'STOP').touch()
                raise RuntimeError('GUI task timed out: STOP written; inspect guest; no retry')
            if time.monotonic() > heartbeat:
                self.log('WAIT_GUI', seconds_remaining=round(deadline-time.monotonic()))
                heartbeat = time.monotonic() + 30
            time.sleep(.4)
        result = read_json(folder / 'result.json')
        self.log('GUI_RESULT', **result)
        guest(f'schtasks /delete /tn "{self.task}" /f')
        if not result['ok']:
            raise RuntimeError(result.get('error', 'GUI failed'))
        return result

    def run(self):
        self.setup()
        if not self.args.execute:
            self.ui('reject-formal' if self.args.reject_formal else 'dry-run', 0)
            return
        self.ui('dry-run', 0)  # No database or robot work before the initial UI safety check.
        for number in range(1, self.args.runs + 1):
            before = self.db(f'{number:03d}-db-before')
            try:
                result = self.ui('run', number)
            except Exception as exc:
                # Formal denial stops immediately. Other failures retain a read-only postmortem.
                if 'DENY_FORMAL' not in str(exc):
                    self.db(f'{number:03d}-db-after-abort')
                raise
            for attempt in range(10):
                after = self.db(f'{number:03d}-db-after-{attempt}')
                if {r['id'] for r in after} - {r['id'] for r in before}:
                    break
                time.sleep(1)
            row = match_result(before, after, result['case_code'], self.args.problem, self.args.robot_id)
            self.results.append(row)
            write_json(self.directory / 'summary.json', dict(
                policy='practice-only', problem=self.args.problem, requested_runs=self.args.runs,
                completed_runs=len(self.results), results=self.results,
                all_cleared=all(r['jammer_count'] == r['cleared_jammer_count'] for r in self.results),
                total_virtual_time_us=sum(r['virtual_time_us'] for r in self.results),
                total_jammer_count=sum(r['jammer_count'] for r in self.results),
                total_cleared_jammer_count=sum(r['cleared_jammer_count'] for r in self.results),
                total_clear_failure_count=sum(r['clear_failure_count'] for r in self.results)))
            self.log('AUTHORITATIVE_RESULT', **row)
            self.ui('return', number, row['case_code'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--problem', type=int, choices=(3, 4), required=True)
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--robot-id', default='202623001141')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='Actually start PRACTICE and run robot; default is dry-run')
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--reject-formal', action='store_true', help='Read a real formal navigation label and fail WITHOUT clicking')
    args = parser.parse_args()
    if args.runs < 1 or (not args.execute and args.runs != 1):
        parser.error('--runs must be positive and requires --execute when greater than 1')
    if not args.robot_id.isascii() or not args.robot_id.isdigit():
        parser.error('--robot-id must contain ASCII digits only')
    if os.environ.get('AUTO_PRACTICE_POLICY', 'practice-only') != 'practice-only' or (TRANSFER / 'STOP').exists():
        parser.error('AUTO_PRACTICE_POLICY disables all work unless exactly practice-only')
    runner = Runner(args)
    status = 0
    try:
        runner.run()
    except (Exception, KeyboardInterrupt) as exc:
        for folder in runner.directory.glob('*/job.json'):
            (folder.parent / 'STOP').touch()
        runner.log('ABORT', error=str(exc))
        status = 1
    finally:
        runner.evidence.parent.mkdir(exist_ok=True)
        try:
            guest(f'schtasks /delete /tn "{runner.task}" /f', timeout=10)
        except Exception:
            pass  # Tasks have no time trigger; STOP/single-use marker also prevent replay.
        shutil.copytree(runner.directory, runner.evidence, dirs_exist_ok=True)
        print(f'Evidence: {runner.evidence}', flush=True)
    return status


if __name__ == '__main__':
    sys.exit(main())
