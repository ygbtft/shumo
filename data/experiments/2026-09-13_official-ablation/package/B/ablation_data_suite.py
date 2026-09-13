"""Frozen, paired Q3/Q4 experiments. Local protocol only; no production edits.

Prepare once from the working tree, then run/analyze from OUT/frozen/B.
"""
import os
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
import platform
import shutil
import sys
import time
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import numpy as np
import component_ablation as old
import component_ablation_supplement as interaction
from mock.scenario_gen import ScenarioConfig, generate

ROOT = Path(__file__).resolve().parent
DEFAULT_GATE = {3: 50., 4: 35.}
CORE = ['full', 'no_share', 'scan_then_service', 'no_negative', 'online_nearest']
LABELS = dict(full='完整策略', no_share='关闭顺路补测', scan_then_service='扫描与服务分阶段',
              no_negative='关闭负反馈位置裁剪', online_nearest='在线路线改为最近邻',
              nearest_sensing='测向选点改为保收最近邻', no_range_skip='关闭距离删测',
              no_grid='关闭光学格心搜索', weak_no_grid='弱定位并关闭光学格心搜索')
ERRORS = [dict(model='iid'), dict(model='smooth'),
          *[dict(model='adversarial', adversarial_sign=s) for s in ('positive', 'negative', 'spatial')]]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def variants(problem):
    core = CORE + (['nearest_sensing'] if problem == 3 else [])
    items = [dict(component=c, gate=g, family='core')
             for g in (DEFAULT_GATE[problem], 20.) for c in core]
    items += [dict(component='full', gate=g, family='gate')
              for g in ([80.] if problem == 3 else [40., 80.])]
    items += [dict(component=c, gate=DEFAULT_GATE[problem], family='supplement')
              for c in ('no_range_skip', 'no_grid', 'weak_no_grid')]
    for item in items:
        item['id'] = f"{item['component']}__g{item['gate']:g}"
    return items


def phased_next(policy, original_next):
    def next_task(unused):
        if len(set(policy.regions) | policy.cleared) == 16:
            policy.stats['known_upper_bound_skips'] += len(unused)
            unused.clear()
        if unused:
            policy.stats['joint_route_solves'] += 1
            index = unused[int(old.remaining_route(policy.stations[unused], policy.client.position, True)[0])]
            return 'survey', index, policy.stations[index]
        # Preserve the production service ranking, packet interruption and budgets.
        return original_next(unused)
    return next_task


def construct(problem, client, variant):
    component = variant['component']
    if component == 'weak_no_grid':
        policy = interaction.construct(problem, client,
                    'nearest_without_grid' if problem == 3 else 'negative_without_grid')
    else:
        setting = {'full': 'baseline', 'scan_then_service': 'baseline',
                   'no_range_skip': 'baseline', 'no_grid': 'no_optical_grid'}.get(component, component)
        policy = old.construct(problem, client, setting)
    policy.trial_radius = variant['gate']
    if problem == 4:
        policy.bracket_trial_radius = variant['gate']
    if component == 'no_range_skip':
        policy.range_skip = False
    if component == 'scan_then_service':
        policy.next_task = phased_next(policy, policy.next_task)
    return policy


def fixtures(problem, phase):
    """Independent seeds per cell; radius and Q4 orientation crossed, not tied."""
    start = 2160913000 + (problem - 3) * 100000 + (10000 if phase == 'validation' else 0)
    directions = ('uniform', 'outward') if problem == 4 else ('uniform',)
    cells = list(itertools.product(range(10, 17), ('uniform', 'edge', 'clustered'),
                                    range(5), ('uniform', 'fixed'), directions))
    repeats = (10 if problem == 3 else 5) if phase == 'validation' else 1
    if phase == 'pilot' and problem == 4:
        # Pilot is a path check, not an inference sample: retain both directions.
        cells = [cell for i, cell in enumerate(cells) if i % 4 in (0, 3)]
    result = []
    for rep in range(repeats):
        for n, layout, error_index, radius, direction in cells:
            seed = start + len(result)
            cfg = ScenarioConfig(count_min=n, count_max=n, position_distribution=layout,
                directional_fraction=.5 if problem == 4 else 0.,
                direction_distribution=direction, radius_distribution=radius, radius_fixed=1000.)
            error = asdict(old.harness.ErrorConfig(**ERRORS[error_index]))
            factors = dict(n=n, layout=layout, error=f"{error['model']}/{error['adversarial_sign']}",
                           radius=radius, direction=direction)
            result.append(dict(case_id=f'q{problem}_{seed}', scenario=generate(seed, cfg).to_dict(),
                error=error, category='/'.join(map(str, factors.values())), factors=factors,
                stratum=json.dumps(factors, sort_keys=True), repeat=rep))
    assert len(result) == (2100 if phase == 'validation' else 210)
    return result


def source_files():
    files = {str(p.relative_to(ROOT)): p for p in ROOT.glob('*.py')}
    files.update({str(p.relative_to(ROOT)): p for p in (ROOT/'layouts').rglob('*') if p.is_file()})
    return files


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    target = out/'frozen/B'
    target.mkdir(parents=True)
    copied = {}
    original = {}
    for rel, path in source_files().items():
        dest = target/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        copied[str(dest.relative_to(out/'frozen'))] = digest(dest.read_bytes())
        original[str(path)] = digest(path.read_bytes())
    mock_root = ROOT.parent/'mock'
    for path in mock_root.rglob('*.py'):
        rel = path.relative_to(mock_root)
        if any(x in ('.venv', '__pycache__', 'results', '.git') for x in rel.parts):
            continue
        dest = out/'frozen/mock'/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        copied[str(dest.relative_to(out/'frozen'))] = digest(dest.read_bytes())
        original[str(path)] = digest(path.read_bytes())
    for path in (ROOT/'tests').glob('test_ablation_data*.py'):
        dest = target/'tests'/path.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(path, dest)
        copied[str(dest.relative_to(out/'frozen'))] = digest(dest.read_bytes())
    data = {phase: {str(p): fixtures(p, phase) for p in (3, 4)} for phase in ('pilot', 'validation')}
    stress_path = ROOT/'experiments/runs/2026-09-12_component-ablation/supplement/stress/fixtures.json'
    stress = json.loads(stress_path.read_text())
    for p, group in stress.items():
        assert len(group) == 45
        for f in group:
            f['factors'] = dict(layout=f['category'], n=len(f['scenario']['sources']),
                                error=f['error']['model'], radius='stress', direction='stress')
            f['stratum'] = f['category']
    data['stress'] = stress
    new_seeds = {f['scenario']['seed'] for phase in ('pilot', 'validation')
                 for group in data[phase].values() for f in group}
    assert len(new_seeds) == 4620
    checked = []; overlaps = []; unreadable = []
    # Inspect saved fixture datasets, excluding copied snapshots and traces.
    for root in (ROOT/'experiments', ROOT.parent/'review-opt', ROOT.parent/'mock/results'):
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ('snapshot', 'code_snapshot', 'mock_snapshot',
                      'frozen', 'traces', '.venv', 'pytest-temp', 'node_modules')]
            for name in names:
                if name != 'fixtures.json':
                    continue
                path = Path(dirpath)/name
                if out == path or out in path.parents:
                    continue
                try:
                    obj = json.loads(path.read_text())
                except (ValueError, OSError) as exc:
                    unreadable.append(dict(path=str(path), error=str(exc)))
                    continue
                seeds = set()
                def collect(x):
                    if isinstance(x, dict):
                        if isinstance(x.get('seed'), int): seeds.add(x['seed'])
                        for v in x.values(): collect(v)
                    elif isinstance(x, list):
                        for v in x: collect(v)
                collect(obj)
                checked.append(dict(path=str(path), sha256=digest(path.read_bytes()), seeds=len(seeds)))
                overlaps.extend(sorted(new_seeds & seeds))
    assert not overlaps and not unreadable, (overlaps, unreadable)
    write_json(out/'seed_audit.json', dict(new_unique_seeds=len(new_seeds), checked=checked,
               overlapping_seeds=overlaps, unreadable=unreadable,
               scope='Existing fixtures.json archives under B/experiments, review-opt and mock/results; stress intentionally reused.'))
    for phase, value in data.items():
        (out/phase).mkdir()
        write_json(out/phase/'fixtures.json', value)
    config = dict(design_version=1, python=sys.executable, python_version=platform.python_version(),
        numpy_version=np.__version__, settings={p: variants(p) for p in (3, 4)},
        baseline_specs=old.harness.builders.SPECS, frozen_sha256=copied, source_sha256=original,
        fixture_sha256={phase: digest((out/phase/'fixtures.json').read_bytes()) for phase in data},
        stress_origin=str(stress_path), stress_origin_sha256=digest(stress_path.read_bytes()),
        official_calls=0, bootstrap_replicates=4000, bootstrap_seed=2160913,
        inference='Stratified paired scene bootstrap; all planned conditions retained; no tuning.',
        expected_executions=73005)
    config['experiment_id'] = digest(canonical(config))
    write_json(out/'config.json', config)
    print(json.dumps(dict(archive=str(out), experiment_id=config['experiment_id'],
                         expected_executions=73005, checked_seed_archives=len(checked)), indent=2))


def normalized_trace(trace):
    return [dict(path=e['path'], request={k:v for k,v in e['request'].items() if k not in ('request_id',)},
                 response={k:v for k,v in e['response'].items() if k != 'real_timestamp_ms'}) for e in trace]


def execute(problem, variant, fixture, capture=True):
    scenario = old.harness.Scenario.from_dict(fixture['scenario'])
    sim = old.harness.Simulator(scenario,
        old.harness.ErrorField(scenario.seed, old.harness.ErrorConfig(**fixture['error'])),
        old.harness.Limits(countdown_s=0))
    transport = old.harness.Transport(old.harness.Protocol(sim))
    state = dict(policy=None, clear_type=None)
    def tracked_transport(path, raw):
        policy = state['policy']
        context = ('sharing' if policy and policy._sharing else
                   'survey' if policy and policy._surveying else 'primary')
        before = len(sim.trace)
        response = transport(path, raw)
        if len(sim.trace) > before:
            sim.trace[-1]['context'] = state['clear_type'] if path == '/clear' else context
        return response
    policy = construct(problem, old.harness.Client(tracked_transport, robot_id='mock-robot'), variant)
    state['policy'] = policy
    clear_events = []; decisions = []
    seen = dict(early=0, grid=0)
    original_clear = policy.clear
    def clear(point, channel, certified=False):
        early = policy.stats.get('early_optical_trials', 0) + policy.stats.get('bracket_optical_trials', 0)
        grid = policy.stats.get('optical_fallback_calls', 0)
        kind = ('certified' if certified else 'early' if early > seen['early'] else
                'grid' if grid > seen['grid'] else 'fallback_center')
        seen.update(early=early, grid=grid)
        old_kind = state['clear_type']; state['clear_type'] = kind
        index = len(sim.trace)
        event = dict(channel=channel, kind=kind, certified=bool(certified),
                     radius=policy.circle(channel)[1] if channel in policy.regions else None)
        try:
            success = original_clear(point, channel, certified)
            event['success'] = bool(success)
            event['trace_index'] = next(i for i in range(index, len(sim.trace)) if sim.trace[i]['path'] == '/clear')
            clear_events.append(event)
            return success
        finally:
            state['clear_type'] = old_kind
    policy.clear = clear
    original_next = policy.next_task
    def next_task(unused):
        task = original_next(unused)
        decisions.append(dict(trace_index=len(sim.trace), unused=len(unused),
                              task=None if task is None else [task[0], int(task[1]), list(map(float, task[2]))]))
        return task
    policy.next_task = next_task
    failure = ''; unavailable = False
    began = time.perf_counter()
    try:
        stats = policy.run()
    except Exception as exc:
        failure = repr(exc); unavailable = isinstance(exc, old.ComponentUnavailable)
        stats = policy.stats.copy()
        if unavailable:
            stats['stop_reason'] = 'ablation_component_unavailable'
            policy.client.exit()
    measures = switches = misses = successes = 0
    distance = 0.; position = (0., 0.); channel = 1
    for e in sim.trace:
        if not e['response'].get('accepted'): continue
        if e['path'] in ('/measure', '/clear'):
            q = e['request']['position']; q = (q['x'], q['y'])
            distance += math.dist(position, q); position = q
        if e['path'] == '/measure':
            measures += 1; new = e['request']['channel']; switches += int(new != channel); channel = new
        if e['path'] == '/clear':
            success = e['response']['clear_result'] == 'success'
            successes += success; misses += not success
    costs = dict(move_s=distance/5, measure_s=5*measures, switch_s=switches,
                 clear_success_s=5*successes, clear_failure_s=3*misses)
    row = dict(problem=problem, variant=variant['id'], component=variant['component'], gate=variant['gate'],
        family=variant['family'], case_id=fixture['case_id'], category=fixture['category'],
        factors=fixture['factors'], stratum=fixture['stratum'], sources=len(scenario.sources),
        cleared=len(sim.cleared), all_cleared=len(sim.cleared)==len(scenario.sources) and not failure,
        failure=failure, unavailable=unavailable, stop_reason=stats.get('stop_reason'),
        total_virtual_s=sim.virtual_time_s, distance_m=distance, measurements=measures,
        switches=switches, successes=successes, misses=misses, costs=costs,
        ledger_error_s=sum(costs.values())-sim.virtual_time_s,
        stats=stats, wall_s=time.perf_counter()-began,
        trace_sha256=digest(canonical(normalized_trace(sim.trace))))
    for kind in ('certified', 'early', 'fallback_center', 'grid'):
        group = [e for e in clear_events if e['kind'] == kind]
        row[kind+'_attempts'] = len(group)
        row[kind+'_successes'] = sum(e['success'] for e in group)
    assert sum(row[k+'_attempts'] for k in ('certified','early','fallback_center','grid')) == successes+misses
    assert abs(row['ledger_error_s']) <= max(1, len(sim.trace))*0.5001e-6
    if variant['component'] == 'no_share': assert stats['shared_known_measurements'] == 0
    if variant['component'] == 'no_range_skip': assert stats['certified_range_scan_skips'] == 0
    if variant['component'] == 'no_negative':
        if problem == 3: assert stats['omni_negative_cuts'] == 0
        else: assert stats['bracket_pair_cuts'] == stats['ablation_disabled_negative_calls']
    if variant['component'] in ('no_grid', 'weak_no_grid'): assert stats['optical_fallback_calls'] == 0
    if variant['component'] == 'scan_then_service':
        assert all(not d['task'] or d['task'][0] != 'source' or d['unused'] == 0 for d in decisions)
    assert row['certified_attempts'] == row['certified_successes']
    assert row['early_attempts'] == stats.get('early_optical_trials',0)+stats.get('bracket_optical_trials',0)
    return row, dict(trace=sim.trace, decisions=decisions, clear_events=clear_events) if capture else None


def worker(task):
    problem, fixture, pending, outstr, phase, experiment_id = task
    out = Path(outstr); result = []
    for variant in pending:
        row, detail = execute(problem, variant, fixture)
        row['experiment_id'] = experiment_id
        row['fixture_sha256'] = digest(canonical(fixture))
        rel = Path(phase)/'traces'/fixture['case_id']/(variant['id']+'.json.gz')
        path = out/rel; path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical(dict(row=row, **detail))
        compressed = gzip.compress(payload, compresslevel=1, mtime=0)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(compressed); temporary.replace(path)
        row['trace_file'] = str(rel); row['file_sha256'] = digest(compressed)
        result.append(row)
    return result


def load_rows(path):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip(): rows.append(json.loads(line))
    return rows


def verify_frozen(out, config):
    assert ROOT == out/'frozen/B', 'Run the frozen script, not the live working-tree script'
    for rel, sha in config['frozen_sha256'].items():
        assert digest((out/'frozen'/rel).read_bytes()) == sha, rel
    for phase, sha in config['fixture_sha256'].items():
        assert digest((out/phase/'fixtures.json').read_bytes()) == sha


def run(out, phase, workers):
    config = json.loads((out/'config.json').read_text()); verify_frozen(out, config)
    if phase != 'pilot':
        pilot = json.loads((out/'pilot/completion.json').read_text())
        assert pilot['unexpected_errors'] == 0 and pilot['runs'] == 6510
    fs = json.loads((out/phase/'fixtures.json').read_text())
    path = out/phase/'trials.jsonl'
    # Each complete JSON line is durable; discard only a crash-truncated final line.
    if path.exists():
        raw = path.read_bytes()
        if raw and not raw.endswith(b'\n'):
            path.write_bytes(raw[:raw.rfind(b'\n')+1])
    rows = load_rows(path); existing = {}
    for row in rows:
        key = (row['problem'], row['case_id'], row['variant'])
        assert key not in existing and row['experiment_id'] == config['experiment_id']
        assert digest((out/row['trace_file']).read_bytes()) == row['file_sha256']
        existing[key] = row
    tasks = []
    for p in (3,4):
        for fixture in fs[str(p)]:
            pending = [v for v in variants(p) if (p, fixture['case_id'], v['id']) not in existing]
            if pending: tasks.append((p,fixture,pending,str(out),phase,config['experiment_id']))
    began = time.perf_counter(); done = len(rows)
    expected = sum(len(fs[str(p)])*len(variants(p)) for p in (3,4))
    with path.open('a') as stream, ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), 1):
            batch = future.result()
            for row in batch: stream.write(json.dumps(row, ensure_ascii=False)+'\n')
            stream.flush(); os.fsync(stream.fileno())
            rows.extend(batch); done += len(batch)
            if index % 10 == 0 or done == expected:
                print(f'{phase}: {done}/{expected} executions, {time.perf_counter()-began:.1f}s', flush=True)
    unexpected = sum(bool(r['failure']) and not r['unavailable'] for r in rows)
    assert len(rows) == expected
    write_json(out/phase/'completion.json', dict(runs=len(rows), expected=expected,
        all_cleared=sum(r['all_cleared'] for r in rows),
        unavailable=sum(r['unavailable'] for r in rows), unexpected_errors=unexpected,
        max_abs_ledger_error_s=max(abs(r['ledger_error_s']) for r in rows),
        wall_s_this_invocation=time.perf_counter()-began))
    assert not unexpected, f'{unexpected} unexpected exceptions; investigate before validation'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--phase',choices=['pilot','validation','stress'])
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(); out=args.output.resolve()
    if args.prepare: prepare(out)
    elif args.phase: run(out,args.phase,args.workers)
    else: parser.error('Choose --prepare or --phase')


if __name__ == '__main__': main()
