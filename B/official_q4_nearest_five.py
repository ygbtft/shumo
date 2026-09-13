"""Five authorized official Q4 practice cases of nearest ordering, default parameters."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import zipfile

PARAMETERS = dict(trial_radius=35., share_limit=6, share_cooldown=150.,
                  transverse_m=40., fraction=.15, steps=10, pause_limit=16,
                  dispatch='nearest')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(p)


def prepare(out, previous):
    assert not out.exists()
    assert json.loads((previous/'finalization.json').read_text())['complete']
    manifest = json.loads((previous/'runtime_manifest.json').read_text())
    for rel, digest in manifest.items():
        assert sha(previous/'package'/rel) == digest
    out.mkdir(parents=True)
    shutil.copytree(previous/'package', out/'package')
    cfg = out/'package/B/official_sensitivity_config.py'
    shutil.copy2(cfg, cfg.with_name('original_sensitivity_config.py'))
    wrapper = '''import hashlib,json
import original_sensitivity_config as original
DEFAULT={4:PARAMETERS_LITERAL}
METHOD={4:'range_grid21_29'}
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def actual_parameters(policy,problem):
    assert problem==4
    return original.actual_parameters(policy,4)|{'dispatch':policy.dispatch}
def construct(problem,client,changes):
    assert problem==4 and not changes
    policy=original.construct(4,client,{})
    policy.dispatch='nearest'
    assert actual_parameters(policy,4)==DEFAULT[4]
    assert policy.bracket_trial_radius==35. and policy.bracket_steps==10
    assert policy.dispatch_model=='base' and policy.range_skip and len(policy.stations)==21
    return policy
'''.replace('PARAMETERS_LITERAL', repr(PARAMETERS))
    cfg.write_text(wrapper)
    schedule = [dict(order=i, problem=4, phase='nearest-five', block=i,
        method='range_grid21_29', setting='nearest35_default_parameters',
        changes={}, parameters=PARAMETERS) for i in range(1, 6)]
    canonical = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    config = dict(created_at=datetime.now().astimezone().isoformat(), schedule=schedule,
        schedule_sha256=canonical(schedule), parameters=PARAMETERS, target=5,
        source_sensitivity=str(previous), cutoff='2026-09-13T17:00:00+08:00',
        official_formal_runs=0, mock_executions=0, observed_nearest_results=0,
        metric='arithmetic mean of per-case virtual time / cleared count',
        runtime='official exit real_timestamp_ms minus enter real_timestamp_ms')
    write(out/'config.json', config)
    write(out/'package/B/experiment.json', config)
    check = '''import json,sys
from client import Client
import official_sensitivity_config as cfg
def deny(*args,**kwargs):raise AssertionError('No requests in configuration check')
p=cfg.construct(4,Client(deny),{})
assert not any(x=='mock' or x.startswith('mock.') for x in sys.modules)
print(json.dumps(dict(parameters=cfg.actual_parameters(p,4),official_requests=0,mock_executions=0)))
'''
    (out/'package/B/check_nearest_config.py').write_text(check)
    checked = subprocess.run([sys.executable,'-B','check_nearest_config.py'],cwd=out/'package/B',capture_output=True,text=True,check=True)
    write(out/'preflight.json', json.loads(checked.stdout))
    host = out/'host';host.mkdir()
    for name in ('auto_practice.py','official_sensitivity_analysis.py'):
        shutil.copy2(previous/'host'/name, host/name)
    (host/'official_sensitivity_config.py').write_text(wrapper)
    shutil.copy2(cfg.with_name('original_sensitivity_config.py'),host/'original_sensitivity_config.py')
    shutil.copytree(previous/'host/auto_practice_support',host/'auto_practice_support')
    runner = (previous/'host/official_sensitivity.py').read_text()
    runner = runner.replace('BSensitivity-20260913','BQ4NearestFive-20260913').replace('OfficialSensitivity-20260913','OfficialQ4NearestFive-20260913')
    (host/'official_sensitivity.py').write_text(runner)
    shutil.copy2(Path(__file__),host/Path(__file__).name)
    write(out/'host_manifest.json',{str(p.relative_to(host)):sha(p) for p in host.rglob('*') if p.is_file()})
    runtime = {str(p.relative_to(out/'package')):sha(p) for p in (out/'package').rglob('*') if p.is_file()}
    write(out/'runtime_manifest.json',runtime)
    with zipfile.ZipFile(out/'runtime.zip','w',zipfile.ZIP_DEFLATED) as z:
        for rel in runtime:z.write(out/'package'/rel,rel)
    (out/'PLAN.md').write_text('Q4官方演练5局：最近邻任务排序、35米门限、fraction=0.15、share_limit=6，其余参数保留默认。\n'
        '五个独立新案例，串行运行，全部结果保留；不调用mock，不使用正式次数。逐局报告清除数、平均定位清除时间、程序运行时间，并计算五局算术平均。\n'
        '与历史同题完整策略及最近邻默认参数组仅作描述性比较；案例、批次及数量不同，不能据此作因果或优效结论。\n')
    write(out/'status.json',dict(state='prepared',completed=0,total=5))
    print('PREPARED',out,flush=True)


def program_time(run):
    files=list(Path(run['evidence']).glob('*/robot-run/requests.jsonl'));assert len(files)==1
    records=[json.loads(l) for l in files[0].read_text().splitlines()]
    accepted=[r for r in records if r.get('response',{}).get('accepted')]
    assert accepted[0]['path']=='/enter' and accepted[-1]['path']=='/exit'
    return (accepted[-1]['response']['real_timestamp_ms']-accepted[0]['response']['real_timestamp_ms'])/1000


def summarize(label,runs):
    return dict(label=label,runs=len(runs),all_clear=sum(r['authoritative']['cleared_jammer_count']==r['authoritative']['jammer_count'] for r in runs),
        mean_cleared=statistics.fmean(r['authoritative']['cleared_jammer_count'] for r in runs),
        mean_localization_clear_s=statistics.fmean(r['authoritative']['virtual_time_us']/1e6/r['authoritative']['cleared_jammer_count'] for r in runs),
        mean_program_runtime_s=statistics.fmean(program_time(r) for r in runs))


def execute(out):
    import official_sensitivity as runner
    from official_sensitivity_analysis import audit_trial
    runner.check_host(out)
    assert not (out/'interruption.json').exists() and not (out/'inflight.json').exists()
    config=json.loads((out/'config.json').read_text())
    with (out/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not (out/'deployment.json').exists():runner.deploy(out)
        check=runner.ap.guest(r'C:\Python314-arm64\python.exe -B C:\BQ4NearestFive-20260913\B\check_nearest_config.py')
        (out/'guest_preflight.log').write_text(check)
        runs=runner.read_runs(out)
        for item in config['schedule']:
            if item['order'] in {r['order'] for r in runs}:continue
            assert datetime.now().astimezone()<datetime.fromisoformat(config['cutoff'])
            run=runner.one(out,item)
            row=audit_trial(run)
            assert run['parameters']==PARAMETERS
            runs.append(run)
            write(out/'status.json',dict(state='running',completed=len(runs),total=5,
                all_clear=sum(r['authoritative']['jammer_count']==r['authoritative']['cleared_jammer_count'] for r in runs)))
            print('Q4_NEAREST_PROGRESS',len(runs),5,json.dumps(dict(case=row['case_code'],cleared=row['cleared'],sources=row['sources'],average_time=row['seconds_per_source'],program_runtime_s=program_time(run))),flush=True)
        assert len(runs)==5 and len({r['authoritative']['case_code'] for r in runs})==5
        rows=[dict(audit_trial(r),program_runtime_s=program_time(r)) for r in runs]
        previous=Path(config['source_sensitivity'])
        ablation=runner.read_runs(previous.parent/'2026-09-13_official-ablation')
        baseline=[r for r in ablation if r['problem']==4 and r['phase']=='validation' and r['variant']=='full__g35']
        nearest=[r for r in ablation if r['problem']==4 and r['phase']=='validation' and r['variant']=='online_nearest__g35']
        assert len(baseline)==len(nearest)==10
        fused=runner.read_runs(previous.parent/'2026-09-13_official-q4-fused-five')
        assert len(fused)==5
        summary=[summarize('历史完整策略35米',baseline),summarize('历史最近邻35米',nearest),
                 summarize('上一批融合方案',fused),summarize('本次最近邻35米＋默认参数',runs)]
        for r in summary:
            for key in ('mean_localization_clear_s','mean_program_runtime_s'):
                r[key+'_vs_original_baseline_pct']=(r[key]/summary[0][key]-1)*100
                r[key+'_vs_historical_nearest_pct']=(r[key]/summary[1][key]-1)*100
                r[key+'_vs_previous_fused_pct']=(r[key]/summary[2][key]-1)*100
        write(out/'result.json',dict(complete=True,official_practice_runs=5,official_formal_runs=0,mock_executions=0,
            parameters=PARAMETERS,trials=rows,summary=summary,descriptive_only=True))
        lines=['# Q4最近邻默认参数5局官方演练结果','',
            '|局次|案例编码|清除干扰源个数|平均定位清除时间（秒）|程序运行时间（秒）|','|---:|---|---:|---:|---:|']
        for r in rows:lines.append(f"|{r['order']}|{r['case_code']}|{r['cleared']}|{r['seconds_per_source']:.3f}|{r['program_runtime_s']:.3f}|")
        lines+=['','|方案|局数|全清局数|平均清除数|平均定位清除时间（秒）|平均程序运行时间（秒）|','|---|---:|---:|---:|---:|---:|']
        for r in summary:lines.append(f"|{r['label']}|{r['runs']}|{r['all_clear']}|{r['mean_cleared']:.2f}|{r['mean_localization_clear_s']:.3f}|{r['mean_program_runtime_s']:.4f}|")
        lines+=['','全部指标按逐局值取算术平均。程序运行时间来自官方退出与进入响应时间戳之差。历史组与本次案例不同，比较仅为描述性，5局不能证明优效。']
        (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
        runner.collect(out)
        post=runner.ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialQ4NearestFive-20260913\verify.py" "C:\BQ4NearestFive-20260913" "\\Mac\Home\Downloads\OfficialQ4NearestFive-20260913\runtime_manifest.json"')
        (out/'postflight.log').write_text(post)
        runner.check_host(out)
        write(out/'finalization.json',dict(complete=True,archived_runs=5,official_formal_runs=0,mock_executions=0,at=datetime.now().astimezone().isoformat()))
        write(out/'status.json',dict(state='complete',completed=5,total=5,all_clear=sum(r['completed'] for r in rows)))
        write(out/'deliverable_manifest.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='deliverable_manifest.json' and '__pycache__' not in p.parts})
        print(json.dumps(dict(complete=True,summary=summary),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--previous',type=Path)
    parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args()
    if args.prepare:prepare(args.output.resolve(),args.previous.resolve())
    else:execute(args.output.resolve())
