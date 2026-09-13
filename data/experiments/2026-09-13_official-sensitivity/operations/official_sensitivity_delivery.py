"""Validate the completed official batch and index its reviewable artifacts."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mechanisms(out, runs):
    groups = defaultdict(list)
    for run in runs:
        parameters, stats = run['parameters'], run['robot']['policy']
        if parameters['share_limit'] == 0:
            assert stats['shared_known_measurements'] == 0
        if run['problem'] == 4:
            assert max([0, *run['robot']['source_rounds'].values()]) <= parameters['steps']
            assert stats['source_interruptions'] <= parameters['pause_limit']
            if parameters['share_cooldown'] == 0:
                assert stats['shared_negative_cooldown_skips'] == 0
        else:
            assert stats['active_measurements'] <= parameters['max_active'] * run['authoritative']['jammer_count']
        groups[(run['phase'], run['problem'], run['setting'])].append(run)
    rows = []
    counters = ('active_measurements', 'shared_known_measurements',
                'shared_negative_cooldown_skips', 'source_interruptions',
                'forced_continuations', 'packet_fallbacks', 'optical_fallback_calls',
                'early_optical_trials', 'early_optical_success',
                'bracket_optical_trials', 'bracket_optical_success', 'bracket_pair_cuts')
    for (phase, problem, setting), group in sorted(groups.items()):
        row = dict(phase=phase, problem=problem, setting=setting, runs=len(group),
                   sources=sum(r['authoritative']['jammer_count'] for r in group))
        for name in counters:
            values = [r['robot']['policy'].get(name) for r in group]
            row[name] = sum(values) if all(v is not None for v in values) else None
        row['sources_at_round_budget'] = (sum(r['robot']['sources_at_round_budget'] for r in group)
                                         if problem == 4 else None)
        row['maximum_source_rounds'] = (max(v for r in group for v in
                                           [0, *r['robot']['source_rounds'].values()])
                                       if problem == 4 else None)
        rows.append(row)
    with (out / 'mechanisms.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    text = '''# 参数路径与机制计数说明

mechanisms.csv只汇总已归档的真实官方运行内部计数，不回放策略、不生成场景。

- share_limit是每次机会共享的数量上限；0表示关闭该路径。共享次数依赖已知源和几何可用性，不能用设定上限替代实际次数。
- Q3 max_active与Q4 steps是主定位预算，不强制执行满额。Q3未记录逐源轮数，预算触达数留空；active_measurements可反映实际主测量总数。
- Q4 maximum_source_rounds与sources_at_round_budget来自实际交错探测计数。达到上限不一定进入光学覆盖：最后一轮也可能已成功清除。
- Q4 transverse_m为横向位移目标，实际宽度还受1.02°—30°角度约束；fraction改变纵向探测距离。没有记录逐次实际角度，不能宣称全部目标位移均原样执行。
- pause_limit为全局源任务打断次数上限；source_interruptions记录实际次数，forced_continuations记录达到上限后强制续做的次数。
- optical_fallback_calls为光学覆盖点清除尝试次数，packet_fallbacks为Q4进入兜底的源任务数，两者单位不同。
- early_optical_trials/early_optical_success对应Q3门槛试清；bracket_optical_trials/bracket_optical_success对应Q4门槛试清。

本表用于解释参数路径是否实际活跃，不是另一个显著性检验。不同设置运行于不同官方案例；次数差异同时包含场景差异。部分预算未触发、角度截断或动作相同，均不能直接推出参数在所有场景下无影响。
'''
    (out / 'MECHANISMS.md').write_text(text)


def finalize(out):
    final = read(out / 'finalization.json')
    assert final['complete'] and final['archived_runs'] == 742
    assert not (out / 'inflight.json').exists()
    assert not (out / 'interruption.json').exists()
    assert not (out / 'live_audit_error.json').exists()
    audit = read(out / 'audit.json')
    assert audit['complete'] and audit['recorded_runs'] == audit['unique_cases'] == 742
    assert audit['phases'] == {'calibration': 2, 'screen': 500, 'robustness': 240}
    assert audit['mock_executions'] == audit['official_formal_runs'] == 0
    runs = [json.loads(line) for line in (out / 'runs.jsonl').read_text().splitlines()]
    assert [r['order'] for r in runs] == list(range(1, 743))
    config = read(out / 'config.json')
    assert all(all(r[key] == value for key, value in expected.items())
               for r, expected in zip(runs, config['schedule']))
    verified = {}
    for manifest, base in [('runtime_manifest.json', out / 'package'),
                           ('host_manifest.json', out / 'host'),
                           ('jlog_manifest.json', out / 'jlogs')]:
        records = read(out / manifest)
        assert records, manifest
        assert all(digest(base / name) == expected for name, expected in records.items()), manifest
        verified[manifest] = len(records)
    robust = read(out / 'robustness.json')
    assert {r['problem'] for r in robust} == {3, 4}
    assert all(r['perturbed_runs'] == 80 and r['baseline_runs'] == 40 for r in robust)
    mechanisms(out, runs)
    counts = Counter(r['problem'] for r in runs)
    sources = sum(r['authoritative']['jammer_count'] for r in runs)
    result = dict(complete=True, runs=742, all_cleared=audit['all_cleared'], sources=sources,
                  runs_by_problem=dict(counts), verified_manifests=verified,
                  prespecified_robustness_passed=all(r['overall_pass'] for r in robust),
                  conclusions={f"Q{r['problem']}": r['verdict'] for r in robust})
    (out / 'delivery_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 官方敏感性实验：742局已完成并归档', '',
             f"全部742局来自原官方模拟器演练，{audit['all_cleared']}/742局全清，共{sources}个源；mock运行0次，正式测试0次。", '',
             '先阅读[结果报告](REPORT.md)，其中列出了两题预设5%非劣效判据的实际结果。'
             '不能仅凭全部清除或差异不显著推断耗时稳健。', '',
             '- [预注册计划](PLAN.md)、[冻结配置](config.json)、[统计判据](analysis_plan.json)',
             '- [逐局数据](trials.csv)、[组汇总](summary.csv)、[宽扫比较](comparisons.csv)',
             '- [联合扰动结论](robustness.json)、[证据审计](audit.json)、[交付核验](delivery_audit.json)',
             '- [机制计数说明](MECHANISMS.md)与[参数路径统计](mechanisms.csv)',
             '- figures/：参数散点、差异区间、联合扰动和动作成本图。',
             '- runs.jsonl与host/auto_practice_evidence/：原始官方成绩、HTTP动作、UI快照和截图。',
             '- jlogs/：官方加密行为日志原件，校验和见jlog_manifest.json。', '',
             '前序消融完成归档后，本批独占官方模拟器串行执行。实验参数与排程在结果出现前冻结；'
             '没有根据宽扫结果挑选联合扰动参数。operations/保留UI采集效率修订及未记录计数的口径修订：'
             '策略运行包、主指标和统计推断函数保持不变。', '',
             'deliverable_manifest.json记录最终主要交付文件的SHA-256；'
             'runtime_manifest.json、host_manifest.json和jlog_manifest.json分别核对策略、宿主脚本和官方日志。']
    (out / 'READ_ME_FIRST.md').write_text('\n'.join(lines) + '\n')
    names = ['READ_ME_FIRST.md', 'REPORT.md', 'PLAN.md', 'config.json', 'analysis_plan.json',
             'trials.csv', 'summary.csv', 'comparisons.csv', 'robustness.json', 'audit.json',
             'adjusted_robustness.csv', 'delivery_audit.json', 'runs.jsonl', 'finalization.json',
             'completion.json', 'runtime_manifest.json', 'host_manifest.json', 'jlog_manifest.json',
             'neighborhood_coverage.json', 'calibration_audit.json', 'postflight.log',
             'mechanisms.csv', 'MECHANISMS.md']
    names += [str(p.relative_to(out)) for p in (out / 'figures').iterdir() if p.is_file()]
    manifest = {name: digest(out / name) for name in sorted(names)}
    (out / 'deliverable_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize(args.output.resolve()), ensure_ascii=False, indent=2))
