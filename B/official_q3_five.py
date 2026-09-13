"""User-requested exploratory stop at five candidate cases; retain prior controls."""
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import statistics
import sys

import official_sensitivity as runner
from official_sensitivity_analysis import audit_trial


def write(path, value):
    runner.write(path, value)


def main(out):
    runner.check_host(out)
    assert not (out / 'inflight.json').exists() and not (out / 'interruption.json').exists()
    plan = json.loads((out / 'effective_plan.json').read_text())
    config = json.loads((out / 'config.json').read_text())
    with (out / 'batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runs = runner.read_runs(out)
        for order in plan['remaining_candidate_orders']:
            if order in {r['order'] for r in runs}:
                continue
            assert sum(r['setting'] == 'candidate' for r in runs) < 5
            assert datetime.now().astimezone() < datetime.fromisoformat(config['cutoff'])
            item = config['schedule'][order - 1]
            assert item['setting'] == 'candidate'
            run = runner.one(out, item)
            try:
                audit_trial(run)
            except Exception as exc:
                write(out / 'interruption.json', dict(order=order, error=repr(exc), stage='ledger audit'))
                raise
            runs.append(run)
            write(out / 'status.json', dict(state='running-five-candidate-check', completed=len(runs),
                total=plan['retained_baseline_runs'] + 5,
                candidate_completed=sum(r['setting'] == 'candidate' for r in runs), candidate_target=5))
            print('FIVE_RUN_PROGRESS', sum(r['setting'] == 'candidate' for r in runs), 5, flush=True)
        rows = [dict(audit_trial(r), program_runtime_s=r['robot']['wall_s']) for r in runs]
        candidate = [r for r in rows if r['setting'] == 'candidate']
        assert len(candidate) == 5
        summary = []
        for setting in ('baseline', 'candidate'):
            group = [r for r in rows if r['setting'] == setting]
            summary.append(dict(setting=setting, runs=len(group), all_clear=sum(r['completed'] for r in group),
                mean_cleared=statistics.fmean(r['cleared'] for r in group),
                mean_localization_clear_s=statistics.fmean(r['seconds_per_source'] for r in group),
                mean_program_runtime_s=statistics.fmean(r['program_runtime_s'] for r in group)))
        for row in summary:
            for key in ('mean_localization_clear_s', 'mean_program_runtime_s'):
                row[key + '_deviation_percent'] = (row[key] / summary[0][key] - 1) * 100
        result = dict(complete=True, exploratory_only=True, candidate_runs=5,
            retained_baseline_runs=plan['retained_baseline_runs'], all_clear=sum(r['completed'] for r in rows),
            superiority_test_performed=False, verdict='Five-case descriptive check only; no confirmed superiority',
            summary=summary, candidate_trials=candidate, mock_executions=0, official_formal_runs=0)
        write(out / 'result.json', result)
        write(out / 'audited_trials.json', rows)
        lines = ['# Q3候选方案5局初步测试', '',
            '按用户要求终止原80局复验，仅将候选累计补足5局；此前已完成的3局baseline全部保留。', '',
            '候选：trial_radius=65、max_active=2，其余参数保持原baseline；任务排序仍为原two_opt。本批未混入最近邻＋50米方案。', '',
            '|候选局次|案例码|清除源数|平均定位清除时间（秒）|程序运行时间（秒）|', '|---:|---|---:|---:|---:|']
        for i, row in enumerate(candidate, 1):
            lines.append(f"|{i}|{row['case_code']}|{row['cleared']}|{row['seconds_per_source']:.3f}|{row['program_runtime_s']:.4f}|")
        lines += ['', '|方案|局数|全清局数|清除数均值|平均定位清除时间（秒）|偏移|平均程序运行时间（秒）|偏移|',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        for row in summary:
            lines.append(f"|{row['setting']}|{row['runs']}|{row['all_clear']}|{row['mean_cleared']:.2f}|"
                f"{row['mean_localization_clear_s']:.3f}|{row['mean_localization_clear_s_deviation_percent']:+.2f}%|"
                f"{row['mean_program_runtime_s']:.4f}|{row['mean_program_runtime_s_deviation_percent']:+.2f}%|")
        lines += ['', '全部均值为逐局算术平均；偏移相对于本批已完成的3局baseline。样本数较小且不同组为不同官方案例，仅用于初步观察，不作统计优效结论。',
                  '', '原80局冻结配置保留于config.json；用户缩减后的有效计划见effective_plan.json，取消证据见operations/。']
        (out / 'REPORT.md').write_text('\n'.join(lines) + '\n')
        runner.collect(out)
        postflight = runner.ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialQ3Refinement-20260913\verify.py" "C:\BQ3Refinement-20260913" "\\Mac\Home\Downloads\OfficialQ3Refinement-20260913\runtime_manifest.json"')
        (out / 'postflight.log').write_text(postflight)
        runner.check_host(out)
        write(out / 'finalization.json', dict(at=datetime.now().astimezone().isoformat(), complete=True,
            effective_plan='five candidate runs, retain previous controls', candidate_runs=5, archived_runs=len(rows),
            official_formal_runs=0, mock_executions=0, superiority_test_performed=False))
        write(out / 'status.json', dict(state='complete', completed=len(rows), total=len(rows),
            candidate_completed=5, candidate_target=5, all_clear=result['all_clear']))
        names = ['REPORT.md', 'result.json', 'effective_plan.json', 'config.json', 'runs.jsonl',
                 'audited_trials.json', 'finalization.json', 'runtime_manifest.json', 'host_manifest.json', 'jlog_manifest.json']
        write(out / 'deliverable_manifest.json', {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in names})
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
