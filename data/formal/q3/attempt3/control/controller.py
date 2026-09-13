import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import auto_practice as ap

out = Path(__file__).resolve().parents[1]
runner = ap.Runner(SimpleNamespace(problem=3, robot_id='202623001141', execute=False, reject_formal=False, runs=1))
try:
    runner.setup()
    state = dict(directory=str(runner.directory), evidence=str(runner.evidence), guest_dir=runner.guest_dir, unc=runner.unc)
    (out / 'controller-state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    print('READY', json.dumps(state, ensure_ascii=False), flush=True)
    queue = out / 'commands'
    queue.mkdir(exist_ok=True)
    while True:
        pending = [p for p in sorted(queue.glob('*.command.json')) if not p.with_suffix('.result.json').exists()]
        if not pending:
            time.sleep(.4)
            continue
        path = pending[0]
        with path.with_suffix('.started').open('x') as stream:
            stream.write('Never replay an uncertain GUI action.\n')
        command = json.loads(path.read_text())
        if command.get('exit'):
            path.with_suffix('.result.json').write_text('{"ok":true,"status":"closed"}\n')
            break
        # Copy the reviewable per-action controller before launching this job.
        shutil.copy2(ap.SUPPORT / 'ui.ps1', runner.directory / 'ui.ps1')
        ap.guest(f'copy /Y "{runner.unc}\\ui.ps1" "{runner.guest_dir}\\ui.ps1" >nul')
        try:
            result = runner.ui(command['action'], runner.counter, command.get('case_code'))
            print('ACTION_RESULT', json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            result = dict(ok=False, error=repr(exc))
            print('ACTION_ERROR', repr(exc), flush=True)
        path.with_suffix('.result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        shutil.copytree(runner.directory, out / 'ui-evidence', dirs_exist_ok=True)
finally:
    if runner.lock:
        runner.lock.close()
