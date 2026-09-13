"""Host orchestration for randomized official practice ablation, using guarded UIA.

Each official run has a newly assigned case. Comparisons are unpaired;
randomized blocks balance run order, not the hidden scene geometry.
"""
import argparse
from datetime import datetime
import hashlib
import json
import random
import shutil
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
import auto_practice as ap
import ablation_data_suite as local

ROOT=Path(__file__).resolve().parent
FROZEN=ROOT/'experiments/runs/2026-09-13_ablation-data/frozen'
GUEST_ROOT=r'C:\BAblation-20260913'
GUEST_B=GUEST_ROOT+r'\B'


def selected(scope):
    choices=[]
    for p in (3,4):
        for v in local.variants(p):
            if scope=='all' or v['component']=='full' or (v['family']=='core' and v['gate']==local.DEFAULT_GATE[p]):
                choices.append(dict(problem=p,variant=v['id']))
    assert len(choices)==(31 if scope=='all' else 16)
    return choices


def prepare(out,scope,repeats):
    out.mkdir(parents=True,exist_ok=False)
    package=out/'package';shutil.copytree(FROZEN,package)
    shutil.copy2(ROOT/'official_ablation_robot.py',package/'B/official_ablation_robot.py')
    manifest={str(p.relative_to(package)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in package.rglob('*') if p.is_file()}
    ap.write_json(out/'runtime_manifest.json',manifest)
    archive=out/'runtime.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for rel in manifest:z.write(package/rel,rel)
    transfer=Path.home()/'Downloads/OfficialAblation-20260913'
    transfer.mkdir(exist_ok=True)
    shutil.copy2(archive,transfer/'runtime.zip');shutil.copy2(out/'runtime_manifest.json',transfer/'runtime_manifest.json')
    verify='''import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
manifest=json.loads(pathlib.Path(sys.argv[2]).read_text())
bad=[r for r,h in manifest.items() if not (root/r).exists() or hashlib.sha256((root/r).read_bytes()).hexdigest()!=h]
assert not bad,bad
print('Official ablation runtime hash match:',len(manifest))
'''
    (transfer/'verify.py').write_text(verify)
    deploy=fr'''$ErrorActionPreference='Stop'
$dest='{GUEST_ROOT}'
if(Test-Path $dest){{throw 'Fresh official ablation deployment destination already exists'}}
Expand-Archive -LiteralPath '\\Mac\Home\Downloads\OfficialAblation-20260913\runtime.zip' -DestinationPath $dest
New-Item -ItemType Directory -Path ($dest+'\B\robot_runs') -Force | Out-Null
& 'C:\Python314-arm64\python.exe' -B '\\Mac\Home\Downloads\OfficialAblation-20260913\verify.py' $dest '\\Mac\Home\Downloads\OfficialAblation-20260913\runtime_manifest.json'
if($LASTEXITCODE -ne 0){{throw 'Hash verification failed'}}
'''
    # Raw UNC literals in generated PowerShell must start with TWO backslashes.
    (transfer/'deploy.ps1').write_text(deploy,encoding='utf-8-sig')
    result=ap.guest(r'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\Mac\Home\Downloads\OfficialAblation-20260913\deploy.ps1"')
    (out/'deploy.log').write_text(result)
    print(result,flush=True)
    schedule=[];rng=random.Random(216091301)
    for block in range(repeats):
        items=selected(scope);rng.shuffle(items)
        start=len(schedule)
        schedule.extend(dict(**item,block=block+1,order=start+i+1) for i,item in enumerate(items))
    ap.write_json(out/'config.json',dict(backend='official-practice',guest_root=GUEST_ROOT,scope=scope,
        repeats=repeats,settings=selected(scope),schedule=schedule,randomization_seed=216091301,
        pairable=False,scoring='Official practice_statistics_tasks.virtual_time_us / jammer_count',
        scene_assignment='New simulator case each run; no hidden source inputs read by robot',
        runtime_manifest_sha256=hashlib.sha256((out/'runtime_manifest.json').read_bytes()).hexdigest(),
        official_formal_runs=0,local_mock_scored_runs=0,calibration_runs=2))


class VariantRunner(ap.Runner):
    def __init__(self,problem,variant):
        args=SimpleNamespace(problem=problem,robot_id='202623001141',execute=True,reject_formal=False,runs=1)
        super().__init__(args);self.variant=variant
        assert any(v['id']==variant for v in local.variants(problem))

    def setup(self):
        super().setup()
        text=(ap.SUPPORT/'ui.ps1').read_text(encoding='utf-8-sig')
        assert text.count("'run_bounded_robot.py'")==1
        text=text.replace("'run_bounded_robot.py'",f"'official_ablation_robot.py','--variant','{self.variant}'")
        text=text.replace(r'C:\BRobot',GUEST_B)
        (self.directory/'ui.ps1').write_text(text,encoding='utf-8-sig')
        ap.guest(f'copy /Y "{self.unc}\\ui.ps1" "{self.guest_dir}\\ui.ps1" >nul')
        ap.write_json(self.directory/'source-hashes.json',{name:hashlib.sha256((self.directory/name).read_bytes()).hexdigest()
                                                        for name in ('ui.ps1','database.py')})
        self.log('OFFICIAL_ABLATION_VARIANT',problem=self.args.problem,variant=self.variant,guest_code=GUEST_B)


def one(out,item,phase):
    runner=VariantRunner(item['problem'],item['variant']);started=time.perf_counter()
    try:
        runner.run()
        score=runner.results[0]
        robot=list(runner.directory.glob('*/robot-run/summary.json'))
        assert len(robot)==1,robot
        robot_summary=ap.read_json(robot[0])
        assert robot_summary['mock_executions']==0 and robot_summary['mode']=='practice'
        assert abs(robot_summary['total_virtual_s']-score['virtual_time_us']/1e6)<2e-6
        assert robot_summary['cleared']==score['cleared_jammer_count']
        result=dict(**item,phase=phase,authoritative=score,robot=robot_summary,
                    evidence=str(runner.evidence),wall_s=time.perf_counter()-started)
        with (out/'runs.jsonl').open('a') as stream:stream.write(json.dumps(result,ensure_ascii=False)+'\n')
        return result
    except BaseException as exc:
        for path in runner.directory.glob('*/job.json'):(path.parent/'STOP').touch()
        ap.write_json(out/'interruption.json',dict(item=item,phase=phase,error=repr(exc),evidence=str(runner.evidence)))
        raise
    finally:
        try:ap.guest(f'schtasks /delete /tn "{runner.task}" /f',timeout=10)
        except Exception:pass
        runner.evidence.parent.mkdir(exist_ok=True)
        shutil.copytree(runner.directory,runner.evidence,dirs_exist_ok=True)
        if runner.lock:runner.lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--scope',choices=['core-gates','all'],default='core-gates')
    parser.add_argument('--repeats',type=int,default=10)
    parser.add_argument('--calibrate',action='store_true')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if args.prepare:prepare(out,args.scope,args.repeats);return
    config=ap.read_json(out/'config.json')
    done=[json.loads(l) for l in (out/'runs.jsonl').read_text().splitlines()] if (out/'runs.jsonl').exists() else []
    if args.calibrate:
        for p in (3,4):
            if not any(r['phase']=='calibration' and r['problem']==p for r in done):
                one(out,dict(problem=p,variant=f'full__g{local.DEFAULT_GATE[p]:g}',order=0,block=0),'calibration')
    elif args.execute:
        if (out/'interruption.json').exists():raise RuntimeError('Unresolved interrupted official session; inspect evidence before resuming')
        completed={r['order'] for r in done if r['phase']=='validation'}
        for item in config['schedule']:
            if item['order'] not in completed:
                result=one(out,item,'validation')
                print('OFFICIAL_BATCH_PROGRESS',item['order'],len(config['schedule']),result['authoritative'],flush=True)
        ap.write_json(out/'completion.json',dict(completed=len(config['schedule']),official_practice=True,local_mock_scored_runs=0))
    else:parser.error('Choose --prepare, --calibrate, or --execute')


if __name__=='__main__':main()
