"""Freeze and independently validate one Q3 candidate using official practice."""
import argparse
from collections import Counter
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys
import zipfile

CHANGES = {'trial_radius': 65, 'max_active': 2}
CUTOFF = '2026-09-13T17:00:00+08:00'


def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out, previous):
    assert json.loads((previous / 'finalization.json').read_text())['complete']
    assert not out.exists(), 'Use a new output directory; never overwrite an experiment.'
    sys.path.insert(0, str(previous / 'package/B'))
    import official_sensitivity_config as cfg
    from client import Client
    import numpy as np
    rows = [json.loads(s) for s in (previous / 'runs.jsonl').read_text().splitlines()]
    training = [r for r in rows if r['problem'] == 3 and r['phase'] == 'screen']
    old_config = json.loads((previous / 'config.json').read_text())
    settings = [s['setting'] for s in old_config['settings'] if s['problem'] == 3 and s['setting'] != 'baseline']
    x = np.array([[1, r['authoritative']['jammer_count']] + [int(r['block'] == b) for b in range(2, 11)]
                  + [int(r['setting'] == s) for s in settings] for r in training])
    y = np.array([r['authoritative']['virtual_time_us'] / 1e6 for r in training])
    inverse = np.linalg.inv(x.T @ x)
    coef = inverse @ x.T @ y
    residual = (y - x @ coef) / (1 - np.sum((x @ inverse) * x, axis=1))
    cov = inverse @ ((x * residual[:, None]).T @ (x * residual[:, None])) @ inverse
    nref = float(np.mean(x[:, 1]))
    effects = [dict(setting=s, adjusted_delta_s_per_source=float(coef[i] / nref),
                    hc3_se=float(np.sqrt(cov[i, i]) / nref)) for i, s in enumerate(settings, 11)]
    rng = random.Random(216091306)
    schedule = []
    for block in range(1, 41):
        pair = [('baseline', {}), ('candidate', CHANGES.copy())]
        rng.shuffle(pair)
        for setting, changes in pair:
            schedule.append(dict(order=len(schedule) + 1, problem=3, phase='refinement', block=block,
                                 method=cfg.METHOD[3], setting=setting, changes=changes,
                                 parameters=cfg.DEFAULT[3] | changes))
    def no_io(*args, **kwargs):
        raise AssertionError('Construction check must not perform an action')
    for item in schedule:
        actual = cfg.actual_parameters(cfg.construct(3, Client(no_io), item['changes']), 3)
        assert actual == item['parameters']
    assert Counter(r['setting'] for r in schedule) == {'baseline': 40, 'candidate': 40}
    assert not any(s == 'mock' or s.startswith('mock.') for s in sys.modules)
    configuration = dict(created_at=datetime.now().astimezone().isoformat(), candidate=cfg.DEFAULT[3] | CHANGES,
        baseline=cfg.DEFAULT[3], schedule=schedule, schedule_sha256=cfg.canonical_hash(schedule),
        cutoff=CUTOFF, seed=216091306, previous_experiment=str(previous),
        previous_runs_sha256=sha(previous / 'runs.jsonl'), observed_new_validation_results=0,
        primary='Equal-case arithmetic mean of official virtual seconds / source count; candidate/default ratio',
        success_rule='All 40 candidate and all 40 baseline cases clear; one-sided 95% block-bootstrap ratio upper < 1',
        bootstrap_replicates=100000, bootstrap_seed=216091307,
        secondary='Arithmetic mean robot.wall_s, cleared source counts, pooled virtual seconds/source; descriptive only',
        no_optional_stopping=True, no_same_scenario_pairing=True, official_formal_runs=0, mock_executions=0)
    out.mkdir(parents=True)
    shutil.copytree(previous / 'package', out / 'package')
    write(out / 'package/B/experiment.json', configuration)
    write(out / 'config.json', configuration)
    write(out / 'selection_analysis.json', dict(development_data_only=True, n=210,
        model='official total_s ~ source_count + time_block + setting; HC3 SE', reference_sources=nref,
        effects=effects, chosen_changes=CHANGES,
        interpretation='Exploratory candidate selection, not a significance claim. Joint effects cannot be added as a guaranteed gain.'))
    host = out / 'host'
    host.mkdir()
    for name in ('auto_practice.py', 'official_sensitivity_config.py', 'official_sensitivity_analysis.py'):
        shutil.copy2(previous / 'host' / name, host / name)
    shutil.copytree(previous / 'host/auto_practice_support', host / 'auto_practice_support')
    helper = (previous / 'host/official_sensitivity.py').read_text()
    helper = helper.replace('BSensitivity-20260913', 'BQ3Refinement-20260913')
    helper = helper.replace('OfficialSensitivity-20260913', 'OfficialQ3Refinement-20260913')
    (host / 'official_sensitivity.py').write_text(helper)
    shutil.copy2(Path(__file__), host / Path(__file__).name)
    write(out / 'host_manifest.json', {str(p.relative_to(host)): sha(p) for p in host.rglob('*') if p.is_file()})
    manifest = {str(p.relative_to(out / 'package')): sha(p) for p in (out / 'package').rglob('*') if p.is_file()}
    write(out / 'runtime_manifest.json', manifest)
    old_manifest = json.loads((previous / 'runtime_manifest.json').read_text())
    assert [key for key in manifest if manifest[key] != old_manifest[key]] == ['B/experiment.json']
    with zipfile.ZipFile(out / 'runtime.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(out / 'package' / name, name)
    write(out / 'preflight.json', dict(constructions_checked=80, actual_parameters_verified=True,
        strategy_files_identical_to_previous=True, mock_imported=False, network_requests=0))
    (out / 'PLAN.md').write_text('''# Q3候选参数独立复验

候选：trial_radius=65、max_active=2；share_limit=6、localization_weight=0.08、remainder_weight=1.5沿用默认值。

原宽扫结果用于选参。源数量和时间区组调整后的探索性分析优先支持门槛65与主定位预算2；该模型不能证明真实收益，也不能把两个单因素收益相加。

新复验80局：候选40局、原baseline40局；40个时间区组内随机安排两者先后。仅使用原官方模拟器演练，串行、不用mock、不占正式测试额度。各局是独立新案例，不是同场景配对。

主指标遵循用户最新口径：每局官方虚拟总秒数/源数，分别对40局等权算术平均。只有候选40/40与baseline40/40全部清除，且候选/baseline均值比单侧95%区组bootstrap上界小于1，才称新复验支持候选定位清除时间更优。重采样100000次，种子216091307。

程序运行时间使用robot.wall_s；清除源数、程序耗时和源加权虚拟时间为辅助描述，不单独用于挑选赢家。参数和排程在第一局新结果前冻结，保留全部案例，不按中途结果停止、增样或换参。17:00停止启动新局；不足80局只报告不完整结果。

新复验不会改写此前742局、原baseline或敏感性实验结论。结果见REPORT.md、result.json；进度见status.json。
''')
    write(out / 'status.json', dict(state='prepared', completed=0, total=80))
    print('PREPARED', out, '80 official-only assignments', flush=True)


def analyze(out, rows):
    import numpy as np
    result = dict(complete=len(rows) == 80, recorded_runs=len(rows), all_clear=sum(r['completed'] for r in rows),
                  mock_executions=0, official_formal_runs=0, summary=[])
    for name in ('baseline', 'candidate'):
        group = [r for r in rows if r['setting'] == name]
        if not group:
            continue
        result['summary'].append(dict(setting=name, runs=len(group), all_clear=sum(r['completed'] for r in group),
            mean_cleared=float(np.mean([r['cleared'] for r in group])),
            mean_localization_clear_s=float(np.mean([r['seconds_per_source'] for r in group])),
            mean_program_runtime_s=float(np.mean([r['program_runtime_s'] for r in group])),
            pooled_virtual_s_per_source=sum(r['total_s'] for r in group) / sum(r['sources'] for r in group)))
    if len(result['summary']) == 2:
        baseline, candidate = result['summary']
        for key in ('mean_localization_clear_s', 'mean_program_runtime_s'):
            candidate[key + '_deviation_percent'] = (candidate[key] / baseline[key] - 1) * 100
            baseline[key + '_deviation_percent'] = 0.
        result['ratio'] = candidate['mean_localization_clear_s'] / baseline['mean_localization_clear_s']
    result['ratio_upper95'] = None
    result['superiority_passed'] = False
    result['verdict'] = 'incomplete; no confirmatory conclusion'
    if result['complete']:
        assert Counter(r['setting'] for r in rows) == {'baseline': 40, 'candidate': 40}
        blocks = []
        for block in range(1, 41):
            pair = {r['setting']: r for r in rows if r['block'] == block}
            assert set(pair) == {'baseline', 'candidate'}
            blocks.append([pair[name]['seconds_per_source'] for name in ('baseline', 'candidate')])
        values = np.array(blocks)
        rng = np.random.default_rng(216091307)
        ratios = []
        for _ in range(20):
            means = values[rng.integers(40, size=(5000, 40))].mean(axis=1)
            ratios.extend((means[:, 1] / means[:, 0]).tolist())
        result['ratio_upper95'] = float(np.quantile(ratios, .95))
        result['ratio_ci95'] = np.quantile(ratios, [.025, .975]).tolist()
        result['superiority_passed'] = result['all_clear'] == 80 and result['ratio_upper95'] < 1
        result['verdict'] = ('independent validation supports lower localization-clearance time'
                             if result['superiority_passed'] else 'insufficient evidence for superiority')
        if result['all_clear'] != 80:
            result['verdict'] = 'completion criterion failed'
    write(out / 'result.json', result)
    write(out / 'audited_trials.json', rows)
    lines = ['# Q3候选参数独立官方复验', '', f"已归档{len(rows)}/80局，全清{result['all_clear']}/{len(rows)}。", '',
             '候选：trial_radius=65、max_active=2，其余参数保持原baseline。每局使用独立官方演练案例，以下均值为逐局等权算术平均。', '',
             '|方案|局数|全清局数|平均清除数|平均定位清除时间（秒）|偏移|平均程序运行时间（秒）|偏移|',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in result['summary']:
        delta = row.get('mean_localization_clear_s_deviation_percent', 0.)
        runtime_delta = row.get('mean_program_runtime_s_deviation_percent', 0.)
        lines.append(f"|{row['setting']}|{row['runs']}|{row['all_clear']}|{row['mean_cleared']:.2f}|"
                     f"{row['mean_localization_clear_s']:.3f}|{delta:+.2f}%|{row['mean_program_runtime_s']:.4f}|{runtime_delta:+.2f}%|")
    if result['complete']:
        lines += ['', f"候选/baseline定位清除时间均值比：{result['ratio']:.5f}；单侧95%上界：{result['ratio_upper95']:.5f}。",
                  '', '独立复验支持候选定位清除时间更优。' if result['superiority_passed'] else
                  '本次复验未通过预设优效判据，不能将候选标记为已验证更优。']
    else:
        lines += ['', '样本未完成，不作验证结论。']
    lines += ['', '旧敏感性数据仅用于选参，没有并入新复验。bootstrap区组连接的是运行时间段，不是相同场景。程序耗时是墙钟耗时，包含HTTP交互，受系统负载影响。',
              '', '全部原始官方成绩和HTTP动作保存在runs.jsonl及host/auto_practice_evidence/；官方日志见jlogs/。']
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    return result


def execute(out):
    import official_sensitivity as runner
    from official_sensitivity_analysis import audit_trial
    runner.check_host(out)
    config = json.loads((out / 'config.json').read_text())
    assert not (out / 'interruption.json').exists() and not (out / 'inflight.json').exists()
    with (out / 'batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (out / 'deployment.json').exists():
            runner.deploy(out)
        rows = []
        for run in runner.read_runs(out):
            rows.append(dict(audit_trial(run), program_runtime_s=run['robot']['wall_s']))
        completed = {r['order'] for r in rows}
        for item in config['schedule']:
            if item['order'] in completed:
                continue
            if datetime.now().astimezone() >= datetime.fromisoformat(config['cutoff']):
                write(out / 'cutoff.json', dict(completed=len(rows), next_order=item['order']))
                break
            try:
                run = runner.one(out, item)
                row = dict(audit_trial(run), program_runtime_s=run['robot']['wall_s'])
                rows.append(row)
            except BaseException as exc:
                if not (out / 'interruption.json').exists():
                    write(out / 'interruption.json', dict(order=item['order'], error=repr(exc), stage='official evidence audit'))
                raise
            write(out / 'status.json', dict(state='running', at=datetime.now().astimezone().isoformat(),
                completed=len(rows), total=80, all_clear=sum(r['completed'] for r in rows),
                audited=len(rows), sources=sum(r['sources'] for r in rows)))
            print('REFINEMENT_PROGRESS', len(rows), 80, item['setting'], row['completed'], flush=True)
        result = analyze(out, rows)
        runner.collect(out)
        postflight = runner.ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialQ3Refinement-20260913\verify.py" "C:\BQ3Refinement-20260913" "\\Mac\Home\Downloads\OfficialQ3Refinement-20260913\runtime_manifest.json"')
        (out / 'postflight.log').write_text(postflight)
        runner.check_host(out)
        write(out / 'finalization.json', dict(at=datetime.now().astimezone().isoformat(), complete=len(rows) == 80,
            archived_runs=len(rows), official_formal_runs=0, mock_executions=0,
            superiority_passed=result['superiority_passed']))
        write(out / 'status.json', dict(state='complete' if len(rows) == 80 else 'cutoff-partial',
            completed=len(rows), total=80, all_clear=result['all_clear']))
        names = ['PLAN.md', 'REPORT.md', 'config.json', 'selection_analysis.json', 'result.json', 'audited_trials.json',
                 'runs.jsonl', 'preflight.json', 'host_manifest.json', 'runtime_manifest.json', 'jlog_manifest.json',
                 'finalization.json', 'postflight.log']
        write(out / 'deliverable_manifest.json', {name: sha(out / name) for name in names})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output.resolve(), args.previous.resolve())
    elif args.execute:
        execute(args.output.resolve())
    else:
        parser.error('Choose --prepare or --execute')
