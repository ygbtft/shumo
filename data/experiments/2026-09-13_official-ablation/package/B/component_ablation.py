"""Instance-only Q3/Q4 component removals, local mock only; never HTTP transport.
The experiment freezes definitions before independent validation. No winner selection.
"""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import param_sensitivity as harness
from adaptive_routes import remaining_route
from completion_sensing_policy import CompletionClearancePolicy
from intelligent import candidate_points, guaranteed_omni
from interleaved_policy import InterleavedMixin
from joint_task_policy import JointTaskPolicy
from omni_negative_policy import OmniNegativeCompletionPolicy
from policies import Policy

ROOT = Path(__file__).resolve().parent
NAMES = {
    'baseline': '完整主候选',
    'no_negative': '关闭位置负信息裁剪',
    'no_share': '关闭顺路已知源补测',
    'scan_first': '先扫描后逐源服务',
    'fixed_scan': '固定扫描相对顺序＋最小增量插源',
    'online_nearest': '在线联合路线改为最近邻',
    'no_early_trial': '关闭提前中心试探（保留有限光学兜底）',
    'no_optical_grid': '关闭光学格心遍历（保留兜底中心试清）',
    'vertex_prior': '面积积分替换为顶点/假设点先验',
    'nearest_sensing': '测向综合评分替换为保收候选最近邻',
    'certified_only': '仅凭MEC/near认证清除（联合移除非认证清除）',
}
SETTINGS = {p: [k for k in NAMES if p == 3 or k not in ('vertex_prior', 'nearest_sensing')]
            for p in (3, 4)}

class ComponentUnavailable(RuntimeError):
    """Explicit fail-fast completion failure, not an exception silently discarded."""


def clone_function(function, **replacements):
    """Private globals per bound experimental method; production globals unchanged."""
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    result = types.FunctionType(function.__code__, namespace, function.__name__,
                                function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def scan_first(self, unused):
    # Preserve public upper-bound pruning; never consult hidden source count.
    if len(set(self.regions) | self.cleared) == 16:
        self.stats['known_upper_bound_skips'] += len(unused)
        unused.clear()
    if unused:
        # Keep online scan-only reordering to isolate scan/service interleaving.
        i = unused[int(remaining_route(self.stations[unused], self.client.position, True)[0])]
        self.stats['joint_route_solves'] += 1
        return 'survey', i, self.stations[i]
    pending = [ch for ch in self.regions if ch not in self.cleared]
    if not pending:
        return None
    previous = getattr(self, '_last_partial', None)
    ch = previous if previous in pending else min(
        pending, key=lambda c: math.dist(self.client.position, self.circle(c)[0]))
    return 'source', ch, self.circle(ch)[0]


def construct(p, client, setting):
    changes = {'share': False} if setting == 'no_share' else {}
    if setting in ('no_early_trial', 'certified_only'):
        changes['trial_radius'] = 0.
    if setting == 'fixed_scan':
        changes['dispatch_model'] = 'locked'
    if setting == 'vertex_prior':
        changes['area_prior'] = False
    # Use the production factory, including its new Q3 negative mixin.
    spec = harness.builders.SPECS[p][harness.METHOD[p]].copy()
    spec.update(changes)
    policy = harness.builders.build(client, spec, p, harness.builders.load_paths(p))
    policy.stats.update(ablation_disabled_negative_calls=0, ablation_scoring_calls=0,
                        ablation_missing_grid=0, ablation_blocked_uncertified=0,
                        ablation_no_candidate=0)
    if setting == 'no_negative':
        if p == 3:
            def record(self, point, ch, reply):
                self.stats['ablation_disabled_negative_calls'] += 1
                # Keep the hook's parent chain, remove only the Q3 inference layer.
                super(OmniNegativeCompletionPolicy, self).record_feedback(point, ch, reply)
            policy.record_feedback = types.MethodType(record, policy)
        else:
            def identity_clip(poly, normal, bound):
                policy.stats['ablation_disabled_negative_calls'] += 1
                return poly
            policy.source_packet = types.MethodType(
                clone_function(InterleavedMixin.source_packet, clip=identity_clip), policy)
    if setting == 'scan_first':
        policy.next_task = types.MethodType(scan_first, policy)
    if setting == 'online_nearest':
        if p == 3:
            policy.task_order = 'nearest'
        else:
            policy.dispatch = 'nearest'
    if setting == 'nearest_sensing':
        def nearest(poly, observations, current, *args):
            policy.stats['ablation_scoring_calls'] += 1
            candidates = [q for q in candidate_points(poly, observations, current)
                          if guaranteed_omni(q, poly, observations[0][0])]
            if candidates:
                return min(candidates, key=lambda q: math.dist(q, current))
            # The original fallback choice also uses covariance. Replace it explicitly.
            from geometry import minimum_circle
            center, _ = minimum_circle(poly)
            if guaranteed_omni(center, poly, observations[0][0]):
                return center
            policy.stats['ablation_no_candidate'] += 1
            raise ComponentUnavailable('No certified nearest-neighbor sensing candidate')
        policy.complete_source = types.MethodType(clone_function(
            CompletionClearancePolicy.complete_source, completion_choice=nearest), policy)
    if setting in ('no_optical_grid', 'certified_only'):
        def absent_grid(poly, angle):
            policy.stats['ablation_missing_grid'] += 1
            raise ComponentUnavailable('Optical grid removed: fallback center failed')
        fallback = clone_function(Policy.complete_source, optical_cover=absent_grid)
        class PrivatePolicy:
            complete_source = staticmethod(fallback)
        if p == 3:
            policy.complete_source = types.MethodType(clone_function(
                CompletionClearancePolicy.complete_source, Policy=PrivatePolicy), policy)
        else:
            policy.fallback = types.MethodType(clone_function(
                InterleavedMixin.fallback, Policy=PrivatePolicy), policy)
        if setting == 'certified_only':
            original_clear = policy.clear
            def certified_clear(point, ch, certified=False):
                if not certified:
                    policy.stats['ablation_blocked_uncertified'] += 1
                    raise ComponentUnavailable('Only MEC/near-certified clear allowed; RF budget exhausted')
                return original_clear(point, ch, certified)
            policy.clear = certified_clear
    return policy


def execute(task):
    p, setting, fixture = task
    scenario = harness.Scenario.from_dict(fixture['scenario'])
    sim = harness.Simulator(scenario, harness.ErrorField(scenario.seed, harness.ErrorConfig(**fixture['error'])),
                            harness.Limits(countdown_s=0))
    client = harness.Client(harness.Transport(harness.Protocol(sim)), robot_id='mock-robot')
    policy = construct(p, client, setting)
    events = []
    original = policy.clear
    def clear(point, ch, certified=False):
        success = original(point, ch, certified)
        events.append(dict(channel=ch, certified=certified, success=success))
        return success
    policy.clear = clear
    failure = ''; unavailable = False
    try:
        stats = policy.run()
    except Exception as exc:
        failure = repr(exc); unavailable = isinstance(exc, ComponentUnavailable)
        stats = policy.stats.copy()
        if unavailable:
            stats['stop_reason'] = 'ablation_component_unavailable'
            client.exit()  # explicit failed completion; zero virtual cost
    measurements = switches = misses = successes = 0
    distance = 0.; position = (0., 0.); channel = 1
    for event in sim.trace:
        if not event['response'].get('accepted'):
            continue
        if event['path'] in ('/measure', '/clear'):
            q = event['request']['position']; q = (q['x'], q['y'])
            distance += math.dist(position, q); position = q
        if event['path'] == '/measure':
            measurements += 1
            new = event['request']['channel']; switches += int(new != channel); channel = new
        if event['path'] == '/clear':
            misses += event['response']['clear_result'] == 'no_target_in_range'
            successes += event['response']['clear_result'] == 'success'
    assert misses == sum(not e['success'] for e in events)
    ledger = distance/5 + 5*measurements + switches + 5*successes + 3*misses
    assert abs(ledger - sim.virtual_time_s) < 1e-6 * max(1, len(sim.trace))
    row = dict(problem=p, setting=setting, case_id=fixture['case_id'], category=fixture['category'],
               sources=len(scenario.sources), cleared=len(sim.cleared),
               all_cleared=len(sim.cleared) == len(scenario.sources) and not failure,
               failure=failure, unavailable=unavailable, total_virtual_s=sim.virtual_time_s,
               measurements=measurements, switches=switches, misses=misses, distance_m=distance,
               certified_failures=sum(e['certified'] and not e['success'] for e in events),
               ledger_error_s=ledger-sim.virtual_time_s, stats=stats)
    if failure:
        # Retain the complete accepted prefix for replay and failure attribution.
        row['failure_trace'] = sim.trace
        row['unresolved_channels'] = sorted(set(sim.sources) - sim.cleared)
    return row


def summarize(rows, out):
    results = []; pairs = []
    for p in (3, 4):
        base = {r['case_id']: r for r in rows if r['problem'] == p and r['setting'] == 'baseline'}
        for setting in dict.fromkeys(r['setting'] for r in rows if r['problem'] == p):
            group = [r for r in rows if r['problem'] == p and r['setting'] == setting]
            assert len(group) == len(base) and {r['case_id'] for r in group} == set(base)
            n = np.array([r['sources'] for r in group])
            d = np.array([r['total_virtual_s'] - base[r['case_id']]['total_virtual_s'] for r in group])
            comparable = np.array([r['all_cleared'] and base[r['case_id']]['all_cleared'] for r in group])
            ids = np.random.default_rng(20260912).integers(len(group), size=(4000, len(group)))
            ci = np.quantile(d[ids].sum(1)/n[ids].sum(1), [.025, .975]).tolist()
            base_t = sum(base[r['case_id']]['total_virtual_s'] for r in group)/n.sum()
            count = sum(r['all_cleared'] for r in group)
            item = dict(problem=p, setting=setting, label=NAMES[setting], runs=len(group),
                        sources=int(n.sum()), all_cleared=count, clear_rate_percent=100*count/len(group),
                        clear_rate_delta_pp=100*(count-sum(b['all_cleared'] for b in base.values()))/len(group),
                        seconds_per_source=sum(r['total_virtual_s'] for r in group)/int(n.sum()),
                        delta=float(d.sum()/n.sum()), delta_percent=float(100*d.sum()/n.sum()/base_t),
                        ci=ci, completion_time_comparable=bool(comparable.all()),
                        faster=int((d < -1e-6).sum()), slower=int((d > 1e-6).sum()),
                        same=int((abs(d) <= 1e-6).sum()),
                        paired_complete=int(comparable.sum()),
                        complete_faster=int(((d < -1e-6)&comparable).sum()),
                        complete_slower=int(((d > 1e-6)&comparable).sum()),
                        complete_same=int(((abs(d) <= 1e-6)&comparable).sum()),
                        worst_s=float(max(0., d.max())),
                        worst_percent=max(0., max(100*x/base[r['case_id']]['total_virtual_s'] for x, r in zip(d, group))),
                        worst_case=group[int(d.argmax())]['case_id'],
                        missing_sources=sum(r['sources']-r['cleared'] for r in group),
                        unexpected_errors=sum(bool(r['failure']) and not r['unavailable'] for r in group))
            for key in ('measurements', 'switches', 'misses', 'distance_m', 'certified_failures'):
                item[key] = sum(r[key] for r in group)
                item['delta_'+key] = item[key] - sum(r[key] for r in base.values())
            for key in ('shared_known_measurements', 'active_measurements', 'source_interruptions',
                        'packet_fallbacks', 'optical_fallback_calls', 'bracket_pair_cuts',
                        'omni_negative_cuts', 'ablation_disabled_negative_calls',
                        'ablation_missing_grid', 'ablation_blocked_uncertified', 'ablation_scoring_calls'):
                item[key] = sum(r['stats'].get(key, 0) for r in group)
            results.append(item)
            for r, delta, good in zip(group, d, comparable):
                pairs.append(dict(problem=p, setting=setting, case_id=r['case_id'], sources=r['sources'],
                                  paired_complete=bool(good), all_cleared=r['all_cleared'],
                                  delta_s=float(delta), delta_percent=100*float(delta)/base[r['case_id']]['total_virtual_s']))
    (out/'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    for name, data in (('summary.csv', results), ('paired.csv', pairs)):
        with (out/name).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    return results


def run_phase(out, fixtures, workers):
    out.mkdir(); (out/'fixtures.json').write_text(json.dumps(fixtures))
    tasks = [(p, setting, f) for p in (3, 4) for f in fixtures[p] for setting in SETTINGS[p]]
    rows = []; began = time.perf_counter()
    with (out/'trials.jsonl').open('x') as stream, ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(execute, tasks, chunksize=2):
            rows.append(row); stream.write(json.dumps(row)+'\n')
            if len(rows) % 100 == 0:
                stream.flush()
            if len(rows) % 500 == 0:
                print(f'{out.name}: {len(rows)}/{len(tasks)} ({time.perf_counter()-began:.1f}s)', flush=True)
    summary = summarize(rows, out)
    (out/'completion.json').write_text(json.dumps(dict(runs=len(rows),
        failed=sum(not r['all_cleared'] for r in rows),
        unexpected_errors=sum(bool(r['failure']) and not r['unavailable'] for r in rows),
        wall_s=time.perf_counter()-began), indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--train-repeats', type=int, default=2)
    parser.add_argument('--validation-repeats', type=int, default=10)
    args = parser.parse_args()
    assert args.train_repeats > 0 and args.validation_repeats > 0 and args.workers > 0
    assert args.train_repeats*105 < 10000
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    snap = out/'code_snapshot'; snap.mkdir()
    for path in ROOT.glob('*.py'):
        shutil.copy2(path, snap/path.name)
    shutil.copytree(ROOT/'layouts', snap/'layouts')
    shutil.copytree(Path(harness.mock.__file__).parent, out/'mock_snapshot',
                    ignore=shutil.ignore_patterns('.venv', '__pycache__', '.git'))
    protected = list(ROOT.glob('*.py')) + [ROOT.parent/'models/paper-full.md']
    hashes = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in protected if f.exists()}
    config = dict(python=sys.executable, mock_path=harness.mock.__file__, settings=SETTINGS, names=NAMES,
                  baseline_specs=harness.builders.SPECS,
                  train_seeds=[202650000, 202650000+args.train_repeats*105-1],
                  validation_seeds=[202660000, 202660000+args.validation_repeats*105-1],
                  definitions_frozen_before_training=True, validation_retuning=False,
                  train_repeats=args.train_repeats, validation_repeats=args.validation_repeats,
                  workers=args.workers, sha256=hashes, official_calls=0,
                  missing_component='Fail fast at first unavailable completion step; prefix time is censored, never efficiency gain.')
    (out/'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2))
    run_phase(out/'training', {p:list(harness.cases(p,args.train_repeats,202650000)) for p in (3,4)}, args.workers)
    (out/'frozen_validation.json').write_text(json.dumps(dict(settings=SETTINGS, selection='Validate every predefined removal; no selection or retuning'), indent=2))
    run_phase(out/'validation', {p:list(harness.cases(p,args.validation_repeats,202660000)) for p in (3,4)}, args.workers)
    integrity = {f: hashlib.sha256(Path(f).read_bytes()).hexdigest() == h for f,h in hashes.items()}
    (out/'integrity.json').write_text(json.dumps(dict(files=integrity, original_files_unchanged=all(integrity.values()), official_calls=0), indent=2))
    assert all(integrity.values())
    print('Completed:', out, flush=True)

if __name__ == '__main__':
    main()
