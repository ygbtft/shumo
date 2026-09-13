"""Five official practice cases of the integrated nearest/gate65/budget2 profile."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import zipfile

METHOD = 'range_area7'
PARAMETERS = dict(task_order='nearest', trial_radius=65., max_active=2,
                  share_limit=6, localization_weight=.08, remainder_weight=1.5)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def prepare(out, previous):
    assert not out.exists()
    assert json.loads((previous / 'finalization.json').read_text())['complete']
    from client import Client
    import bounded_candidates as builders
    def no_io(*args, **kwargs):
        raise AssertionError('Configuration check must not send requests')
    policy = builders.build(Client(no_io), builders.SPECS[3][METHOD], 3, builders.load_paths(3))
    actual = {key: getattr(policy, 'time_weight' if key == 'localization_weight' else key) for key in PARAMETERS}
    assert actual == PARAMETERS
    assert not any(s == 'mock' or s.startswith('mock.') for s in sys.modules)
    schedule = [dict(order=i, problem=3, phase='fused-five', block=i, method=METHOD,
                     setting='nearest65_a2', changes={}, parameters=PARAMETERS) for i in range(1, 6)]
    canonical = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    config = dict(created_at=datetime.now().astimezone().isoformat(), schedule=schedule,
        schedule_sha256=canonical(schedule), parameters=PARAMETERS, candidate_target=5,
        cutoff='2026-09-13T17:00:00+08:00', observed_fused_results=0, descriptive_only=True,
        source_sensitivity=str(previous), official_formal_runs=0, mock_executions=0)
    out.mkdir(parents=True)
    shutil.copytree(previous / 'package', out / 'package')
    shutil.copy2(Path(__file__).parent / 'bounded_candidates.py', out / 'package/B/bounded_candidates.py')
    frozen_cfg = '''import hashlib,json
DEFAULT={3:PARAMETER_LITERAL}
METHOD={3:METHOD_LITERAL}
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def actual_parameters(policy,problem):
    assert problem==3
    return {key:getattr(policy,'time_weight' if key=='localization_weight' else key) for key in DEFAULT[3]}
def construct(problem,client,changes):
    import bounded_candidates as builders
    assert problem==3 and not changes
    policy=builders.build(client,builders.SPECS[3][METHOD[3]],3,builders.load_paths(3))
    assert actual_parameters(policy,3)==DEFAULT[3]
    return policy
'''.replace('PARAMETER_LITERAL', repr(PARAMETERS)).replace('METHOD_LITERAL', repr(METHOD))
    (out / 'package/B/official_sensitivity_config.py').write_text(frozen_cfg)
    write(out / 'package/B/experiment.json', config)
    write(out / 'config.json', config)
    host = out / 'host'
    host.mkdir()
    for name in ('auto_practice.py', 'official_sensitivity_analysis.py'):
        shutil.copy2(previous / 'host' / name, host / name)
    (host / 'official_sensitivity_config.py').write_text(frozen_cfg)
    shutil.copytree(previous / 'host/auto_practice_support', host / 'auto_practice_support')
    ui = host / 'auto_practice_support/ui.ps1'
    text = ui.read_text(encoding='utf-8-sig')
    assert text.count("'range_area7'") == 1
    ui.write_text(text.replace("'range_area7'", repr(METHOD)), encoding='utf-8-sig')
    helper = (previous / 'host/official_sensitivity.py').read_text()
    helper = helper.replace('BSensitivity-20260913', 'BQ3FusedFive-20260913')
    helper = helper.replace('OfficialSensitivity-20260913', 'OfficialQ3FusedFive-20260913')
    (host / 'official_sensitivity.py').write_text(helper)
    shutil.copy2(Path(__file__), host / Path(__file__).name)
    write(out / 'host_manifest.json', {str(p.relative_to(host)): sha(p) for p in host.rglob('*') if p.is_file()})
    manifest = {str(p.relative_to(out / 'package')): sha(p) for p in (out / 'package').rglob('*') if p.is_file()}
    write(out / 'runtime_manifest.json', manifest)
    with zipfile.ZipFile(out / 'runtime.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(out / 'package' / name, name)
    write(out / 'preflight.json', dict(actual_parameters=actual, network_requests=0,
        mock_imported=False, integrated_builder_sha256=sha(out / 'package/B/bounded_candidates.py')))
    (out / 'PLAN.md').write_text('''# Q3融合方案：5局官方演练

任务排序最近邻，trial_radius=65，max_active=2；share_limit=6、localization_weight=0.08、remainder_weight=1.5。调用生产入口注册的range_area7，其他机制保留。

按用户澄清，单独运行5个全新官方演练案例，串行、不使用mock、不使用正式测试额度；本批不混入此前未融合最近邻的参数候选。计划与运行文件在首局前冻结，所有结果保留，不重抽不利案例。

给出逐局三指标及5局算术平均，与历史baseline、最近邻50米及原65米/2轮候选分别作描述性比较。不同历史组为不同官方案例，样本量和时间段不同，均值差异不代表已验证的因果改善；5局不作统计优效结论。
''')
    write(out / 'status.json', dict(state='prepared', completed=0, total=5))
    print('PREPARED', out, actual, flush=True)


def summarize(label, runs):
    return dict(label=label, runs=len(runs), all_clear=sum(r['authoritative']['cleared_jammer_count'] == r['authoritative']['jammer_count'] for r in runs),
        mean_cleared=statistics.fmean(r['authoritative']['cleared_jammer_count'] for r in runs),
        mean_localization_clear_s=statistics.fmean(r['authoritative']['virtual_time_us'] / 1e6 / r['authoritative']['jammer_count'] for r in runs),
        mean_program_runtime_s=statistics.fmean(r['robot']['wall_s'] for r in runs))


def execute(out):
    import official_sensitivity as runner
    from official_sensitivity_analysis import audit_trial
    runner.check_host(out)
    assert not (out / 'interruption.json').exists() and not (out / 'inflight.json').exists()
    config = json.loads((out / 'config.json').read_text())
    with (out / 'batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (out / 'deployment.json').exists():
            runner.deploy(out)
        runs = runner.read_runs(out)
        for item in config['schedule']:
            if item['order'] in {r['order'] for r in runs}:
                continue
            assert datetime.now().astimezone() < datetime.fromisoformat(config['cutoff'])
            try:
                run = runner.one(out, item)
                audit_trial(run)
            except Exception as exc:
                if not (out / 'interruption.json').exists():
                    write(out / 'interruption.json', dict(order=item['order'], error=repr(exc)))
                raise
            runs.append(run)
            write(out / 'status.json', dict(state='running', completed=len(runs), total=5,
                all_clear=sum(r['authoritative']['jammer_count'] == r['authoritative']['cleared_jammer_count'] for r in runs)))
            print('FUSED_PROGRESS', len(runs), 5, flush=True)
        assert len(runs) == 5 and len({r['authoritative']['case_code'] for r in runs}) == 5
        rows = [dict(audit_trial(r), program_runtime_s=r['robot']['wall_s']) for r in runs]
        previous = Path(config['source_sensitivity'])
        historical = runner.read_runs(previous)
        baseline = [r for r in historical if r['problem'] == 3 and r['phase'] == 'screen' and r['setting'] == 'baseline']
        ablation = runner.read_runs(previous.parent / '2026-09-13_official-ablation')
        nearest = [r for r in ablation if r['problem'] == 3 and r['phase'] == 'validation' and r['variant'] == 'online_nearest__g50']
        parameter_only = [r for r in runner.read_runs(previous.parent / '2026-09-13_official-q3-refinement') if r['setting'] == 'candidate']
        assert len(baseline) == len(nearest) == 10
        summary = [summarize('原baseline', baseline), summarize('最近邻＋50米（历史消融）', nearest),
                   summarize('原排序＋65米＋2轮（此前候选）', parameter_only), summarize('最近邻＋65米＋2轮（本次融合）', runs)]
        for row in summary:
            for key in ('mean_localization_clear_s', 'mean_program_runtime_s'):
                row[key + '_deviation_percent'] = (row[key] / summary[0][key] - 1) * 100
        result = dict(complete=True, official_practice_runs=5, parameters=PARAMETERS, summary=summary,
            trials=rows, descriptive_only=True, superiority_test_performed=False, mock_executions=0, official_formal_runs=0)
        write(out / 'result.json', result)
        lines = ['# Q3融合方案5局官方演练结果', '',
            '方案：最近邻任务排序＋65米试清门限＋2轮主定位预算；其余参数与baseline一致。', '',
            '|局次|案例码|清除数|平均定位清除时间（秒）|程序运行时间（秒）|', '|---:|---|---:|---:|---:|']
        for row in rows:
            lines.append(f"|{row['order']}|{row['case_code']}|{row['cleared']}|{row['seconds_per_source']:.3f}|{row['program_runtime_s']:.4f}|")
        lines += ['', '|方案|局数|全清局数|清除数均值|定位清除时间均值（秒）|相对baseline|程序运行时间均值（秒）|相对baseline|',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        for row in summary:
            lines.append(f"|{row['label']}|{row['runs']}|{row['all_clear']}|{row['mean_cleared']:.2f}|"
                f"{row['mean_localization_clear_s']:.3f}|{row['mean_localization_clear_s_deviation_percent']:+.2f}%|"
                f"{row['mean_program_runtime_s']:.4f}|{row['mean_program_runtime_s_deviation_percent']:+.2f}%|")
        lines += ['', '所有均值为逐局值相加除以局数；偏移使用未舍入均值计算。清除数不同反映不同案例的源数差异。程序耗时为robot.wall_s，包含HTTP交互，不含界面准备与归档。',
                  '', '本次仅5局，历史对照的案例、数量、运行时间段均不同；结果只能作为初步观察，不作优效或普遍更优结论。']
        (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
        runner.collect(out)
        post = runner.ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialQ3FusedFive-20260913\verify.py" "C:\BQ3FusedFive-20260913" "\\Mac\Home\Downloads\OfficialQ3FusedFive-20260913\runtime_manifest.json"')
        (out / 'postflight.log').write_text(post)
        runner.check_host(out)
        write(out / 'finalization.json', dict(complete=True, archived_runs=5, official_formal_runs=0, mock_executions=0,
            at=datetime.now().astimezone().isoformat()))
        write(out / 'status.json', dict(state='complete', completed=5, total=5, all_clear=sum(r['completed'] for r in rows)))
        names = ['PLAN.md', 'REPORT.md', 'config.json', 'result.json', 'runs.jsonl', 'preflight.json',
                 'host_manifest.json', 'runtime_manifest.json', 'jlog_manifest.json', 'finalization.json', 'postflight.log']
        write(out / 'deliverable_manifest.json', {n: sha(out / n) for n in names})
        print(json.dumps({'summary': summary, 'complete': True}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output.resolve(), args.previous.resolve())
    else:
        execute(args.output.resolve())
