"""Monte Carlo evaluation with paired seeds, failures and replayable truth+traces."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import csv
import json
from pathlib import Path
import platform
import time
import numpy as np
from .client_or_inproc import InProcessClient, load_strategy, run_strategy
from .error_field import ErrorConfig, ErrorField
from .protocol import Protocol
from .scenario_gen import Scenario, generate, load_config
from .simulator import Limits, Simulator


def metrics(total, cleared, total_time_s):
    # 假设 A9：统计整局所有已接受动作的虚拟耗时，包括最后清除后的搜索。
    return dict(total=total, cleared=cleared, cleared_fraction=cleared/total if total else None,
                total_time_s=total_time_s,
                average_clear_time_s=total_time_s/cleared if cleared else None)


def evaluate_case(seed, scenario_cfg, error_cfg, strategy_spec, max_actions=10000, scenario=None):
    case = scenario or generate(seed, scenario_cfg)
    # 假设 A10：MC 省略 5 秒准备倒计时；其余两种现实限时/虚拟上限保持一致。
    sim = Simulator(case, ErrorField(case.seed, error_cfg), Limits(countdown_s=0))
    protocol = Protocol(sim)
    try:
        strategy = load_strategy(strategy_spec, seed)
        result = run_strategy(InProcessClient(protocol), strategy, max_actions)
        reason, error, runtime = result.stop_reason, result.error, result.runtime_s
    except Exception as exc:
        reason, error, runtime = 'strategy_load_error', f'{type(exc).__name__}: {exc}', 0.
    row = dict(seed=case.seed, **metrics(len(case.sources), len(sim.cleared), sim.virtual_time_s),
               actions=len(sim.trace), stop_reason=reason, runtime_s=runtime, error=error,
               missed_channels=sorted(set(sim.sources)-sim.cleared))
    row['failure'] = row['cleared'] != row['total'] or reason != 'user_exit'
    return {'metrics':row, 'scenario':case.to_dict(), 'error':asdict(error_cfg),
            'strategy':strategy_spec, 'max_actions':max_actions, 'trace':sim.trace,
            'end_reason':sim.end_reason}


def _job(args): return evaluate_case(*args)


def mandatory_conditions(scenario_cfg, error_cfg):
    """Mandatory 3 position distributions x 5 bounded error conditions.

    Empirical calibrations add conditions; they never remove stress conditions.
    """
    positions=['uniform','edge','clustered']
    if scenario_cfg.position_distribution=='empirical': positions.append('empirical')
    errors=[replace(error_cfg,model='iid'),replace(error_cfg,model='smooth')]
    errors.extend(replace(error_cfg,model='adversarial',adversarial_sign=sign) for sign in ('positive','negative','spatial'))
    if error_cfg.model=='empirical': errors.append(error_cfg)
    return [(position+'__'+ec.model+('-'+ec.adversarial_sign if ec.model=='adversarial' else ''),
             replace(scenario_cfg,position_distribution=position),ec) for position in positions for ec in errors]


def distribution(values):
    valid = [v for v in values if v is not None and np.isfinite(v)]
    if not valid: return {'n':0, 'undefined':len(values), 'mean':None, 'std':None, 'quantiles':{}}
    a = np.asarray(valid, dtype=float)
    return dict(n=len(a), undefined=len(values)-len(a), mean=float(a.mean()), std=float(a.std()),
                quantiles={f'p{q:02d}':float(np.percentile(a, q)) for q in (0, 5, 25, 50, 75, 95, 100)})


def summarize(rows):
    cleared = sum(r['cleared'] for r in rows)
    total = sum(r['total'] for r in rows)
    return dict(runs=len(rows), failures=sum(r['failure'] for r in rows),
                all_cleared_rate=sum(r['total']==r['cleared'] for r in rows)/len(rows),
                cleared_fraction=distribution([r['cleared_fraction'] for r in rows]),
                average_clear_time_s=distribution([r['average_clear_time_s'] for r in rows]),
                total_time_s=distribution([r['total_time_s'] for r in rows]),
                runtime_s=distribution([r['runtime_s'] for r in rows]),
                pooled_cleared_fraction=cleared/total if total else None,
                pooled_average_clear_time_s=sum(r['total_time_s'] for r in rows)/cleared if cleared else None,
                zero_clear_runs=sum(r['cleared']==0 for r in rows))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=int, default=100, help='cases PER condition; mandatory matrix has at least 15 conditions')
    p.add_argument('--seed', type=int, default=0, help='first case seed; use same range for paired comparisons')
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--config')
    p.add_argument('--error-models', help='compatibility option; mandatory iid/smooth/+1/-1/spatial conditions always run')
    p.add_argument('--strategy', help='module:Class, constructor accepts seed=; default Baseline or saved case strategy')
    p.add_argument('--max-actions', type=int, help='default 10000, or original saved case limit during replay')
    p.add_argument('--case', help='replay saved failure/sample case with exact source and error configuration')
    p.add_argument('--output', default='mock/results/mc')
    p.add_argument('--plot', action='store_true', help='plot first and worst case of each condition')
    args = p.parse_args()
    if args.runs < 1 or args.workers < 1 or (args.max_actions is not None and args.max_actions < 1): p.error('runs/workers/max-actions must be positive')
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    cfg, error = load_config(args.config)
    if args.case:
        saved = json.loads(Path(args.case).read_text(encoding='utf-8'))
        error = ErrorConfig(**saved['error'])
        scenario = Scenario.from_dict(saved['scenario'])
        result = evaluate_case(scenario.seed, cfg, error, args.strategy or saved.get('strategy', 'mock.strategy:Baseline'), args.max_actions or saved.get('max_actions', 10000), scenario)
        write_json(out/'replay.json', result)
        if args.plot:
            from .viz import plot_case
            plot_case(result, out/'replay.png')
        print(json.dumps(result['metrics'], indent=2)); return
    args.strategy = args.strategy or 'mock.strategy:Baseline'
    args.max_actions = args.max_actions or 10000
    if args.error_models:
        for model in args.error_models.split(','):
            if model not in ('iid','smooth','adversarial'): p.error('unknown error model')
    started = time.perf_counter()
    summaries = {}
    for label, condition_cfg, ec in mandatory_conditions(cfg,error):
        folder = out/label
        if folder.exists():
            p.error(f'output condition exists: {folder}; choose a new output directory to avoid stale failures')
        folder.mkdir(parents=True)
        jobs = ((seed, condition_cfg, ec, args.strategy, args.max_actions) for seed in range(args.seed, args.seed+args.runs))
        rows, worst = [], None
        pool = ProcessPoolExecutor(args.workers) if args.workers > 1 else None
        try:
            results = pool.map(_job, jobs, chunksize=4) if pool else map(_job, jobs)
            for index, result in enumerate(results):
                row = result['metrics']; rows.append(row)
                if index == 0: write_json(folder/'sample.json', result)
                if row['failure']: write_json(folder/'failures'/f"seed-{row['seed']}.json", result)
                score = (row['cleared_fraction'], -(row['average_clear_time_s'] or float('inf')))
                if worst is None or score < worst[0]: worst = (score, result)
                if (index+1) % 50 == 0: print(f'{label}: {index+1}/{args.runs}', flush=True)
        finally:
            if pool: pool.shutdown()
        write_json(folder/'worst.json', worst[1])
        write_json(folder/'rows.json', rows)
        with (folder/'rows.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        summary = summarize(rows)
        summary.update(scenario_config=asdict(condition_cfg), error_config=asdict(ec), strategy=args.strategy,
                       seed_start=args.seed, max_actions=args.max_actions, workers=args.workers)
        write_json(folder/'summary.json', summary)
        summaries[label] = summary
        if args.plot:
            from .viz import plot_case
            for name in ('sample','worst'):
                plot_case(json.loads((folder/f'{name}.json').read_text(encoding='utf-8')), folder/f'{name}.png')
        print(f"{label}: cleared={summary['cleared_fraction']['mean']:.4%}; average={summary['average_clear_time_s']['mean']} s/source; failures={summary['failures']}", flush=True)
    worst_coverage=min(summaries,key=lambda k:(summaries[k]['cleared_fraction']['mean'],-(summaries[k]['average_clear_time_s']['mean'] or float('inf'))))
    worst_time=max(summaries,key=lambda k:summaries[k]['average_clear_time_s']['mean'] or float('inf'))
    worst=dict(coverage_condition=worst_coverage,coverage=summaries[worst_coverage],
               time_condition=worst_time,time=summaries[worst_time])
    write_json(out/'summary.json', dict(conditions=summaries, worst=worst,
                                      mandatory_matrix_complete=len(summaries)>=15,
                                      elapsed_s=time.perf_counter()-started,
                                      python=platform.python_version(), numpy=np.__version__))
    print(f'Worst coverage: {worst_coverage}; worst average time: {worst_time}',flush=True)

if __name__ == '__main__': main()
