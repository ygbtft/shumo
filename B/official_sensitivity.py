"""Prepare and serially execute a frozen official-practice sensitivity batch."""
import argparse
import ast
from collections import Counter
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

import auto_practice as ap
import official_sensitivity_config as cfg

ROOT = Path(__file__).resolve().parent
GUEST_ROOT = r'C:\BSensitivity-20260913'
GUEST_B = GUEST_ROOT + r'\B'
TRANSFER = Path.home()/'Downloads/OfficialSensitivity-20260913'
CUTOFF = '2026-09-13T17:00:00+08:00'


def write(path, data):
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_runs(out):
    path = out/'runs.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def preflight():
    from client import Client
    settings, schedule = cfg.assignments()
    def no_io(*args, **kwargs):
        raise AssertionError('Construction must not perform any action')
    checked = []
    for row in schedule:
        policy = cfg.construct(row['problem'],Client(no_io),row['changes'])
        actual = cfg.actual_parameters(policy,row['problem'])
        assert actual == row['parameters']
        checked.append(dict(order=row['order'],parameters=actual))
    assert Counter(r['phase'] for r in schedule) == dict(calibration=2,screen=500,robustness=240)
    for p in (3,4):
        for block in range(1,41):
            group=[r for r in schedule if r['phase']=='robustness' and r['problem']==p and r['block']==block]
            assert Counter(r['setting'] for r in group)==dict(baseline=1,perturbed=2)
    assert not any(k == 'mock' or k.startswith('mock.') for k in sys.modules)
    return settings,schedule,checked


def prepare(out, ablation):
    settings,schedule,checked = preflight()
    out.mkdir(parents=True,exist_ok=False)
    package = out/'package/B'
    package.mkdir(parents=True)
    # Snapshot exactly the locally loaded production modules; no mock package is shipped.
    files = {Path(m.__file__).resolve() for m in list(sys.modules.values())
             if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT
             and Path(m.__file__).suffix=='.py'}
    files.add(ROOT/'official_sensitivity_robot.py')
    production = [p for p in files if p.name not in ('official_sensitivity.py','auto_practice.py')]
    for file in production:
        shutil.copy2(file,package/file.name)
    (package/'layouts').mkdir()
    shutil.copy2(ROOT/'layouts/grid21_29.json',package/'layouts/grid21_29.json')
    configuration = dict(created_at=datetime.now().astimezone().isoformat(),backend='official-practice',
        seed=216091303,cutoff=CUTOFF,settings=settings,schedule=schedule,grid=cfg.GRID,
        defaults=cfg.DEFAULT,neighborhood=cfg.NEIGHBORHOOD,prior_ablation=str(ablation.resolve()),
        guest_root=GUEST_ROOT,official_formal_runs=0,mock_executions=0,
        success_rule='For each problem: 80/80 perturbed and 40/40 baseline all-clear; block-bootstrap ratio upper97.5 < 1.05',
        inference=dict(bootstrap_replicates=100000,noninferiority_ratio=1.05,
            upper_quantile=.975,screen_holm_comparisons=48,scenario_pairing=False),
        schedule_sha256=cfg.canonical_hash(schedule))
    write(out/'config.json',configuration)
    write(package/'experiment.json',configuration)
    write(out/'preflight.json',dict(assignments=len(checked),all_actual_parameters_match=True,
        mock_imported=False,network_requests=0,construction_checks=checked))
    host = out/'host'
    host.mkdir()
    for name in ('official_sensitivity.py','official_sensitivity_config.py','official_sensitivity_analysis.py','auto_practice.py'):
        shutil.copy2(ROOT/name,host/name)
    shutil.copytree(ROOT/'auto_practice_support',host/'auto_practice_support')
    write(out/'source_hashes.json',{str(file):sha(file) for file in files})
    write(out/'host_manifest.json',{str(p.relative_to(host)):sha(p) for p in host.rglob('*') if p.is_file()})
    manifest={str(p.relative_to(out/'package')).replace('\\','/'):sha(p) for p in (out/'package').rglob('*') if p.is_file()}
    write(out/'runtime_manifest.json',manifest)
    with zipfile.ZipFile(out/'runtime.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in manifest:
            z.write(out/'package'/name,name)
    write(out/'analysis_plan.json',dict(frozen_at=configuration['created_at'],observed_sensitivity_results=0,
        primary=configuration['success_rule'],inference=configuration['inference'],
        wide_screen='Exploratory; no post-screen parameter selection or tuning',
        random_neighborhood='Independent uniform draws per coordinate, reject only all-default; frozen before all outcomes',
        all_started_cases_retained=True,cutoff=CUTOFF,
        schedule_sha256=configuration['schedule_sha256']))
    print('PREPARED',out,'742 assignments; no guest access or simulator execution',flush=True)


def check_host(out):
    for rel,digest in ap.read_json(out/'host_manifest.json').items():
        assert sha(out/'host'/rel)==digest,rel
    assert cfg.canonical_hash(ap.read_json(out/'config.json')['schedule'])==ap.read_json(out/'config.json')['schedule_sha256']


def wait_for_ablation(out, configuration):
    ablation=Path(configuration['prior_ablation'])
    while not (ablation/'finalization.json').exists():
        count=len((ablation/'runs.jsonl').read_text().splitlines()) if (ablation/'runs.jsonl').exists() else 0
        state=dict(state='waiting-for-ablation-finalization',at=datetime.now().astimezone().isoformat(),
                   observed_ablation_rows=count,prior_interruption=(ablation/'interruption.json').exists())
        write(out/'status.json',state)
        print('WAITING_FOR_ABLATION',count,flush=True)
        if datetime.now().astimezone()>=datetime.fromisoformat(configuration['cutoff']):
            raise RuntimeError('Start cutoff reached while waiting for prior ablation')
        time.sleep(30)
    final=ap.read_json(ablation/'finalization.json')
    assert final['official_validation_runs']==160 and final['official_calibration_runs']==2
    assert (ablation/'completion.json').exists() and not (ablation/'interruption.json').exists()
    write(out/'prior_ablation_released.json',dict(at=datetime.now().astimezone().isoformat(),finalization=final))


def deploy(out):
    TRANSFER.mkdir(exist_ok=True)
    for name in ('runtime.zip','runtime_manifest.json'):
        shutil.copy2(out/name,TRANSFER/name)
    verifier='''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); manifest=json.loads(pathlib.Path(sys.argv[2]).read_text())
bad=[r for r,h in manifest.items() if not (root/r).is_file() or hashlib.sha256((root/r).read_bytes()).hexdigest()!=h]
assert not bad,bad
print('Frozen runtime verified:',len(manifest))
'''
    (TRANSFER/'verify.py').write_text(verifier)
    script=fr'''$ErrorActionPreference='Stop'
$dest='{GUEST_ROOT}'
if(Test-Path $dest){{throw 'Sensitivity destination already exists; verify previous deployment'}}
Expand-Archive -LiteralPath '\\Mac\Home\Downloads\OfficialSensitivity-20260913\runtime.zip' -DestinationPath $dest
New-Item -ItemType Directory -Path ($dest+'\B\robot_runs') -Force | Out-Null
& 'C:\Python314-arm64\python.exe' -B '\\Mac\Home\Downloads\OfficialSensitivity-20260913\verify.py' $dest '\\Mac\Home\Downloads\OfficialSensitivity-20260913\runtime_manifest.json'
if($LASTEXITCODE -ne 0){{throw 'Runtime verification failed'}}
'''
    (TRANSFER/'deploy.ps1').write_text(script,encoding='utf-8-sig')
    result=ap.guest(r'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\Mac\Home\Downloads\OfficialSensitivity-20260913\deploy.ps1"')
    (out/'deploy.log').write_text(result)
    write(out/'deployment.json',dict(at=datetime.now().astimezone().isoformat(),guest_root=GUEST_ROOT))


class SensitivityRunner(ap.Runner):
    def __init__(self,item):
        super().__init__(SimpleNamespace(problem=item['problem'],robot_id='202623001141',execute=True,reject_formal=False,runs=1))
        self.item=item
    def setup(self):
        super().setup()
        script=(self.directory/'ui.ps1').read_text(encoding='utf-8-sig')
        assert script.count("'run_bounded_robot.py'")==1
        script=script.replace("'run_bounded_robot.py'",f"'official_sensitivity_robot.py','--assignment-id','{self.item['order']}'")
        script=script.replace(r'C:\BRobot',GUEST_B)
        (self.directory/'ui.ps1').write_text(script,encoding='utf-8-sig')
        ap.guest(f'copy /Y "{self.unc}\\ui.ps1" "{self.guest_dir}\\ui.ps1" >nul')
        write(self.directory/'source-hashes.json',{name:sha(self.directory/name) for name in ('ui.ps1','database.py')})


def one(out,item):
    runner=SensitivityRunner(item)
    started=time.perf_counter()
    result=None
    write(out/'inflight.json',dict(assignment=item,evidence=str(runner.evidence),working_evidence=str(runner.directory),
                                 began=datetime.now().astimezone().isoformat()))
    try:
        runner.run()
        official=runner.results[0]
        paths=list(runner.directory.glob('*/robot-run/summary.json'))
        assert len(paths)==1
        robot=ap.read_json(paths[0])
        assert robot['assignment']==item and robot['parameters']==item['parameters']
        assert robot['mode']=='practice' and robot['mock_executions']==0
        assert abs(robot['total_virtual_s']-official['virtual_time_us']/1e6)<2e-6
        assert robot['cleared']==official['cleared_jammer_count']
        result=dict(**item,authoritative=official,robot=robot,evidence=str(runner.evidence),wall_s=time.perf_counter()-started)
    except BaseException as exc:
        for path in runner.directory.glob('*/job.json'):
            (path.parent/'STOP').touch()
        write(out/'interruption.json',dict(assignment=item,error=repr(exc),evidence=str(runner.evidence),
              working_evidence=str(runner.directory),at=datetime.now().astimezone().isoformat()))
        raise
    finally:
        try:
            ap.guest(f'schtasks /delete /tn "{runner.task}" /f',timeout=10)
        except Exception:
            pass
        runner.evidence.parent.mkdir(exist_ok=True)
        shutil.copytree(runner.directory,runner.evidence,dirs_exist_ok=True)
        if runner.lock:
            runner.lock.close()
    assert result is not None
    # Append only once all raw evidence is immutable in the archive.
    with (out/'runs.jsonl').open('a') as f:
        f.write(json.dumps(result,ensure_ascii=False)+'\n')
        f.flush()
        os.fsync(f.fileno())
    (out/'inflight.json').unlink()
    return result


def collect(out):
    names=[]
    for r in read_runs(out):
        a=r['authoritative']
        name=f"practice-p{r['problem']}-{a['practice_run_no']}-{a['case_code']}.jlog"
        assert re.fullmatch(r'practice-p[34]-\d+-[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\.jlog',name)
        names.append(name)
    (TRANSFER/'jlogs').mkdir(exist_ok=True)
    # Keep generated commands below command-line limits by using a script file.
    lines=["$ErrorActionPreference='Stop'",'$names=@('+','.join(ap.psquote(n) for n in names)+')',
        r"foreach($name in $names){Copy-Item -LiteralPath ('C:\Jammers\JammersSimulatorData\behavior-logs\'+$name) -Destination ('\\Mac\Home\Downloads\OfficialSensitivity-20260913\jlogs\'+$name)}",
        "Write-Output ('Copied '+$names.Count+' sensitivity logs')"]
    (TRANSFER/'collect.ps1').write_text('\n'.join(lines),encoding='utf-8-sig')
    result=ap.guest(r'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\Mac\Home\Downloads\OfficialSensitivity-20260913\collect.ps1"')
    (out/'collect.log').write_text(result)
    dest=out/'jlogs'
    dest.mkdir(exist_ok=True)
    for name in names:
        shutil.copy2(TRANSFER/'jlogs'/name,dest/name)
    write(out/'jlog_manifest.json',{name:sha(dest/name) for name in names})


def execute(out):
    check_host(out)
    configuration=ap.read_json(out/'config.json')
    if (out/'interruption.json').exists() or (out/'inflight.json').exists():
        raise RuntimeError('Interrupted or uncertain case requires evidence reconciliation before resumption')
    with (out/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        wait_for_ablation(out,configuration)
        if not (out/'deployment.json').exists():
            deploy(out)
        completed={r['order'] for r in read_runs(out)}
        for item in configuration['schedule']:
            if item['order'] in completed:
                continue
            if datetime.now().astimezone()>=datetime.fromisoformat(configuration['cutoff']):
                write(out/'cutoff.json',dict(at=datetime.now().astimezone().isoformat(),completed=len(completed),next_order=item['order']))
                break
            row=one(out,item)
            completed.add(item['order'])
            a=row['authoritative']
            write(out/'status.json',dict(state='running',at=datetime.now().astimezone().isoformat(),
                completed=len(completed),total=len(configuration['schedule']),last_order=item['order'],phase=item['phase'],
                last_all_cleared=a['jammer_count']==a['cleared_jammer_count']))
            print('SENSITIVITY_PROGRESS',item['order'],742,item['phase'],item['problem'],item['setting'],
                  a['case_code'],a['cleared_jammer_count'],a['jammer_count'],flush=True)
            if item['phase']=='calibration' and a['jammer_count']!=a['cleared_jammer_count']:
                raise RuntimeError('Official calibration did not fully clear; stop before main experiment')
        complete=len(completed)==742
        if complete:
            write(out/'completion.json',dict(completed=742,official_practice=True,mock_executions=0))
        subprocess.run([sys.executable,'-B',str(out/'host/official_sensitivity_analysis.py'),str(out)],check=True)
        collect(out)
        result=ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialSensitivity-20260913\verify.py" "C:\BSensitivity-20260913" "\\Mac\Home\Downloads\OfficialSensitivity-20260913\runtime_manifest.json"')
        (out/'postflight.log').write_text(result)
        check_host(out)
        write(out/'finalization.json',dict(at=datetime.now().astimezone().isoformat(),complete=complete,
              archived_runs=len(completed),report='REPORT.md',official_formal_runs=0,mock_executions=0))
        write(out/'status.json',dict(state='complete' if complete else 'cutoff-partial',completed=len(completed),total=742))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--ablation',type=Path,default=ROOT/'experiments/runs/2026-09-13_official-ablation')
    args=parser.parse_args()
    out=args.output.resolve()
    if args.prepare:
        prepare(out,args.ablation)
    elif args.execute:
        execute(out)
    else:
        parser.error('Choose --prepare or --execute')


if __name__=='__main__':
    main()
