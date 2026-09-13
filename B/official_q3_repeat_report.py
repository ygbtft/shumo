"""Retain both five-case fused-Q3 batches in a descriptive repeat report."""
import hashlib
import json
from pathlib import Path
import statistics
import sys


def read_runs(path):
    return [json.loads(line) for line in (path / 'runs.jsonl').read_text().splitlines()]


def summary(label, runs, baseline):
    result = dict(label=label, runs=len(runs),
        all_clear=sum(r['authoritative']['cleared_jammer_count'] == r['authoritative']['jammer_count'] for r in runs),
        mean_cleared=statistics.fmean(r['authoritative']['cleared_jammer_count'] for r in runs),
        mean_localization_clear_s=statistics.fmean(r['authoritative']['virtual_time_us'] / 1e6 /
                                                 r['authoritative']['jammer_count'] for r in runs),
        mean_program_runtime_s=statistics.fmean(r['robot']['wall_s'] for r in runs))
    for key in ('mean_localization_clear_s', 'mean_program_runtime_s'):
        result[key + '_deviation_percent'] = (result[key] / baseline[key] - 1) * 100
    return result


def main(out):
    config = json.loads((out / 'config.json').read_text())
    previous = Path(config['repeat_of'])
    for folder in (previous, out):
        assert json.loads((folder / 'finalization.json').read_text())['complete']
        for name, digest in json.loads((folder / 'deliverable_manifest.json').read_text()).items():
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
        for name, digest in json.loads((folder / 'jlog_manifest.json').read_text()).items():
            assert hashlib.sha256((folder / 'jlogs' / name).read_bytes()).hexdigest() == digest
    first, second = read_runs(previous), read_runs(out)
    assert len(first) == len(second) == 5
    assert len({r['authoritative']['case_code'] for r in first + second}) == 10
    assert all(r['robot']['parameters'] == config['parameters'] for r in first + second)
    baseline = json.loads((out / 'result.json').read_text())['summary'][0]
    groups = [baseline, summary('融合方案第一轮', first, baseline),
              summary('融合方案第二轮', second, baseline), summary('融合方案两轮合计', first + second, baseline)]
    rows = [dict(round=round_no, order=r['order'], case_code=r['authoritative']['case_code'],
                 cleared=r['authoritative']['cleared_jammer_count'], sources=r['authoritative']['jammer_count'],
                 localization_clear_s=r['authoritative']['virtual_time_us'] / 1e6 / r['authoritative']['jammer_count'],
                 program_runtime_s=r['robot']['wall_s'], evidence=r['evidence'])
            for round_no, group in ((1, first), (2, second)) for r in group]
    result = dict(complete=True, parameters=config['parameters'], summary=groups, trials=rows,
        first_round=str(previous), second_round=str(out),
        first_round_runs_sha256=hashlib.sha256((previous / 'runs.jsonl').read_bytes()).hexdigest(),
        second_round_runs_sha256=hashlib.sha256((out / 'runs.jsonl').read_bytes()).hexdigest(),
        retained_cases=10, descriptive_only=True, superiority_test_performed=False)
    (out / 'repeat_comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    lines = ['# 最近邻＋65米＋2轮：第二轮及累计结果', '',
        '第二轮与第一轮使用完全一致的策略和机器人文件。两轮各5局均为原官方模拟器的新演练案例，所有10局均保留。', '',
        '|组别|局数|全清局数|清除数均值|平均定位清除时间（秒）|相对baseline|平均程序运行时间（秒）|相对baseline|',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in groups:
        lines.append(f"|{row['label']}|{row['runs']}|{row['all_clear']}|{row['mean_cleared']:.2f}|"
            f"{row['mean_localization_clear_s']:.3f}|{row['mean_localization_clear_s_deviation_percent']:+.2f}%|"
            f"{row['mean_program_runtime_s']:.4f}|{row['mean_program_runtime_s_deviation_percent']:+.2f}%|")
    lines += ['', '## 逐局成绩', '', '|轮次|局次|案例码|清除数|源数|平均定位清除时间（秒）|程序运行时间（秒）|',
              '|---:|---:|---|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"|{row['round']}|{row['order']}|{row['case_code']}|{row['cleared']}|{row['sources']}|"
                     f"{row['localization_clear_s']:.3f}|{row['program_runtime_s']:.4f}|")
    lines += ['', '三个指标分别按逐局值相加除以本组局数计算；累计均值包含全部10局。偏移使用未舍入的本组均值和原敏感性宽扫10局baseline均值计算。',
              '', '追加第二轮是在查看第一轮结果后按用户要求进行，因此这里只做描述性汇总，不进行优效检验。各组为不同官方案例，源数和几何差异会影响结果；程序运行时间还受系统负载影响。',
              '', '第二轮曾在启动界面操作前遇到Q4资源锁，确认没有产生新案例后等待Q4完成再启动。等待与未启动的尝试未计入实验样本；核对记录位于operations/。']
    report = out / 'REPORT.md'
    original = out / 'operations/REPORT-before-repeat-summary.md'
    if not original.exists():
        original.write_bytes(report.read_bytes())
    report.write_text('\n'.join(lines) + '\n')
    manifest = json.loads((out / 'deliverable_manifest.json').read_text())
    for name in ('REPORT.md', 'repeat_comparison.json'):
        manifest[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / 'deliverable_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'summary': groups, 'retained_cases': 10}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
