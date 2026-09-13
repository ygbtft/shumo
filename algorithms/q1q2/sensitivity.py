"""Small, offline PLAN 11.6 experiments. No simulator or measurement client.

Search can stop early; every retained old/new point is subsequently scored on
one frozen, augmented pool per physical model. This is not a global benchmark.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import numpy as np
from .geometry import (BearingMeasurement, NumericPolicy, HalfPlane, point, unit,
                       distance, wedge_halfplanes, intersect_halfplanes, diameter)
from .feasible import PhysicsConfig, Feedback, build_source_set, check_candidate
from .q2 import (SearchConfig, SourceSamples, sample_sources, score_point,
                 select_second_point, check_admissibility, candidate_bbox)
from .diagnostics import clearance_summary, equilateral_case, sensitivity_cases
from .circle import minimum_circle
from .q1 import solve
from .run import write_json, jsonable

GRIDS = ((5, 13), (9, 25), (17, 49))


def samples(ss, cfg, level=2, q=None, **kw):
    return sample_sources(ss, level, cfg.source_grids, q,
                          inward=cfg.near_offset_m,
                          second_half_width_deg=cfg.second_half_width_deg, **kw)


def choose(rows, ss, threshold):
    valid = [r for r in rows if r['score'] is not None and r['q'] != ss.first.position]
    if not valid:
        return None
    best = min(r['score'].J_hat for r in valid)
    return min((r for r in valid if r['score'].J_hat <= best+threshold),
               key=lambda r: (distance(r['q'], ss.first.position), r['q']))


def common_evaluation(ss, cfg, points):
    """Filter first, collect all contacts/witnesses, freeze, then rank fairly."""
    started = time.monotonic()
    points = list(dict.fromkeys(point(q) for q in points if q is not None))
    assessments = {q: check_admissibility(ss, q, cfg) for q in points}
    valid = [q for q in points if assessments[q]['status'] == 'IN']
    base = samples(ss, cfg)
    pool = set(base.points)
    calls = 0
    final_cfg = replace(cfg, refine_pairs=True)
    for q in valid:
        local = samples(ss, cfg, q=q)
        pool.update(local.points)
        sc = score_point(ss, q, local, final_cfg)
        calls += 1
        for w in sc.top_pairs:
            pool.update((w.x, w.y))
    shifted = samples(ss, cfg, shifted=True)
    pool.update(shifted.points)
    frozen = replace(base, points=tuple(sorted(pool)), additional_count=len(pool)-len(base.points))
    # No points are inserted during this last pass: every score sees the same pool.
    rows = []
    for q in points:
        sc = score_point(ss, q, frozen, final_cfg) if q in valid else None
        calls += int(sc is not None)
        clear = None
        if sc and sc.witness:
            w = sc.witness
            fb = Feedback(kind=w.branch, bearing_deg=w.common_bearing_deg,
                          half_width_deg=cfg.second_half_width_deg)
            # Refined witnesses need not belong to frozen samples; include all
            # legal support witnesses for conditional diagnostics (not ranking).
            evidence = set(frozen.points)
            for pair in sc.top_pairs:
                evidence.update((pair.x, pair.y))
            clear = clearance_summary(ss, q, fb, replace(frozen, points=tuple(sorted(evidence))), cfg.policy)
        representatives = []
        if clear is not None:
            representatives.append(clear)
        if sc and any(distance(q, x) <= ss.physics.near_radius for x in frozen.points):
            representatives.append(clearance_summary(ss, q, Feedback(kind='near'), frozen, cfg.policy))
        rows.append(dict(q=q, admissibility=assessments[q], score=sc, clearance=clear,
                         representative_feedbacks=representatives,
                         movement_m=distance(q, ss.first.position),
                         movement_seconds=distance(q, ss.first.position)/5))
    return rows, frozen, dict(sample_count=len(pool), base_sample_count=len(base.points),
        common_additions=len(pool)-len(base.points), shifted_sample_count=len(shifted.points),
        score_calls=calls, elapsed_seconds=time.monotonic()-started)


def scan_counts(result, ss, cfg):
    box = candidate_bbox(ss, cfg)
    out = []
    for step in cfg.station_steps_m:
        planned = math.prod(max(0, math.floor(box[i+1]/step+1e-10)-math.ceil(box[i]/step)+1) for i in (0, 2))
        records = [r for r in result.grid_records if r['step_m'] == step]
        scanned = sum(r['status'] != 'NOT_EVALUATED' for r in records)
        out.append(dict(step_m=step, planned=planned, scanned=scanned,
                        fraction=scanned/planned if planned else None,
                        feasible=sum(r['status'] in ('IN', 'BOUNDARY') for r in records)))
    return out


def run_case(name, ss, cfg, old_q=None):
    started = time.monotonic()
    result = select_second_point(ss, cfg, extra_points=(() if old_q is None else (old_q,)))
    # Retain both the search's cost-aware point and its smallest estimated J.
    best_raw = min(result.alternatives, key=lambda r: r.score.J_hat).q if result.alternatives else None
    qs = [old_q, result.q_best, best_raw]
    # A symmetry partner is a diagnostic candidate, never assumed feasible.
    if result.q_best:
        u = unit(math.radians(ss.first.bearing_deg))
        v = np.asarray(result.q_best)-ss.first.position
        qs.append(point(np.asarray(ss.first.position)+2*np.dot(v, u)*u-v))
    rows, pool, costs = common_evaluation(ss, cfg, qs)
    new = choose(rows, ss, cfg.tie_floor_m)
    old = next((r for r in rows if r['q'] == old_q), None)
    before = {r.q: r.score.J_hat for r in result.alternatives}
    comparable = [r for r in rows if r['score'] and r['q'] in before]
    # Strict inversions only; exact ties do not imply coordinate uniqueness.
    flips = sum((before[a['q']]-before[b['q']])*(a['score'].J_hat-b['score'].J_hat) < 0
                for i, a in enumerate(comparable) for b in comparable[i+1:])
    record = dict(name=name, source_set=ss, config=cfg, search=result, fixed_old=old,
        reselected=new, final_candidates=rows, accounting=costs,
        scan=scan_counts(result, ss, cfg), rank_inversions=flips,
        elapsed_seconds=time.monotonic()-started,
        stop_reason=result.stop_reason, stability=result.stability,
        limitation='finite shortlist; uniform final scoring does not complete interrupted global search')
    return record, pool


def shape_control():
    tri = solve(equilateral_case(36)['measurements'], NumericPolicy())
    return dict(triangle=dict(diameter=tri.diameter.length, R=tri.minimum_circle.radius,
                             single_clear_possible=tri.minimum_circle.radius <= 20),
                segment=dict(diameter=36., R=18., single_clear_possible=True),
                label='analytic shape control; conditional R is not worst J_R')


def clipping(ss, row, pool):
    """F11 data reuse: tangent outer bounds and sampled nonconvex final K."""
    if row is None or row['clearance'] is None:
        return dict(status='NOT_EVALUATED')
    q, fb = row['q'], row['clearance'].feedback
    if fb.kind != 'direction':
        return dict(status='NOT_APPLICABLE_NEAR')
    hps = list(wedge_halfplanes(ss.first))
    if q != ss.first.position:
        hps += list(wedge_halfplanes(BearingMeasurement(q, fb.bearing_deg, fb.half_width_deg)))
    stages = []
    disks = [[], [(ss.physics.arena_center, ss.physics.arena_radius)],
             [(ss.first.position, ss.physics.rho_hi), (q, ss.physics.rho_hi)]]
    for name, add in zip(('P', 'P_intersect_A', 'plus_receiving_disks'), disks):
        for center, radius in add:
            for i in range(64):
                n = unit(2*math.pi*i/64)
                hps.append(HalfPlane(point(n), float(n @ center+radius), name))
        region = intersect_halfplanes(hps, ss.policy)
        d = diameter(region)
        c = minimum_circle(region.vertices, seed=0)
        stages.append(dict(stage=name, status=region.status, kind=region.kind,
                           d=d.length, R=c.radius, label='exact wedges' if name == 'P' else '64-side tangent outer estimate'))
    clear = row['clearance']
    from .feasible import posterior_contains
    legal = np.asarray(pool.points)[posterior_contains(ss, q, fb, pool.points, ss.policy)]
    from .geometry import convex_hull
    hull = convex_hull(legal, ss.policy)
    d_sample = max((distance(a, b) for a in hull for b in hull), default=0.)
    stages.append(dict(stage='exclude_both_5m_disks', status='SAMPLE_AND_OUTER',
        d=d_sample, R=clear.R_hat, r_U=clear.r_U,
        label='nonconvex K sample lower estimates; r_U conservative outer; open disks not polygon clipping'))
    return dict(feedback=fb, q=q, stages=stages,
                dominant_constraint='inspect successive finite diameters; no percent for unbounded',
                q1_object_unchanged=True)


def numerical_audit(ss, cfg, record, pool):
    started = time.monotonic()
    qs = [r['q'] for r in record['final_candidates'] if r['score']]
    variants = []
    calls = 0
    # Full model rebuild for tolerance, offset-only experiments kept separate.
    settings = [('source_'+str(k), cfg, k, False) for k in range(3)]
    settings += [('shifted', cfg, 2, True)]
    for factor in (.1, 10.):
        policy = NumericPolicy(**{k: v*factor for k, v in vars(cfg.policy).items()})
        settings.append((f'tolerance_{factor}', replace(cfg, policy=policy), 2, False))
        settings.append((f'offset_{factor}', replace(cfg, near_offset_m=cfg.near_offset_m*factor), 2, False))
    for name, varied, level, shifted in settings:
        model = build_source_set(ss.first, ss.physics, varied.policy)
        sp = samples(model, varied, level=level, shifted=shifted)
        rows = []
        for q in qs:
            check = check_admissibility(model, q, varied)
            sc = score_point(model, q, sp, replace(varied, refine_pairs=False)) if check['status'] == 'IN' else None
            calls += int(sc is not None)
            rows.append(dict(q=q, score=sc, admissibility=check))
        winner = choose(rows, model, varied.tie_floor_m)
        variants.append(dict(name=name, sample_count=len(sp.points), rows=rows, winner=winner))
    tie = []
    for factor in (0., .5, 1., 2.):
        winner = choose(record['final_candidates'], ss, factor*cfg.tie_floor_m)
        tie.append(dict(factor=factor, threshold_m=factor*cfg.tie_floor_m, fixed_old=record['reselected'], reselected=winner,
                        scope='reselection from identical uniformly scored final shortlist'))
    return dict(variants=variants, tie=tie, score_calls=calls,
                elapsed_seconds=time.monotonic()-started,
                source_delta_scope='unaugmented nested pools; distinct from common-final contact refinement',
                tolerance_scope='F and candidate checks rebuilt; offset held fixed',
                boundary_offset_scope='offset changed independently of tolerance',
                station_history=record['search'].refinement_history,
                status='FINITE_AUDIT_NOT_ERROR_BOUND')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--search-seconds', type=float, default=30.)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    cfg = SearchConfig(source_grids=GRIDS, starts=2, pair_starts=4, pair_rounds=4,
                       time_budget_s=args.search_seconds, boundary_step_deg=15.)
    physics, policy = PhysicsConfig(), cfg.policy
    # Ordinary, wraparound and almost tangent; the last station is legally outside A.
    scenes = dict(standard=BearingMeasurement((0., 0.), 0.),
                  ordinary=BearingMeasurement((0., 0.), 35.),
                  tangent=BearingMeasurement((1900., 0.), 180-math.degrees(math.asin(1800/1900))+.2),
                  edge=BearingMeasurement((1850., 0.), 180.))
    records, cached = {}, {}
    def execute(key, ss, config, old=None):
        print('START', key, flush=True)
        record, pool = run_case(key, ss, config, old)
        records[key] = record
        cached[key] = (ss, config, record, pool)
        write_json(args.output/(key+'.json'), record)
        print('DONE', key, record['stop_reason'], record['accounting'], flush=True)
        return record
    for name, first in scenes.items():
        ss = build_source_set(first, physics, policy)
        baseline = execute(name+'_default', ss, cfg)
        old = baseline['reselected']['q'] if baseline['reselected'] else None
        for group, label, model, overrides in sensitivity_cases(first, physics, policy):
            if group == 'S1' and name in ('standard', 'ordinary', 'tangent') and model.first.half_width_deg > 1:
                execute(name+'_S1', model, replace(cfg, second_half_width_deg=model.first.half_width_deg), old)
            if group == 'S3' and name in ('standard', 'edge'):
                execute(name+'_'+label, model, cfg, old)
            if group == 'S4' and name == 'edge':
                execute('edge_S4', model, replace(cfg, **overrides), old)
    ss, _, base, pool = cached['standard_default']
    old = base['reselected']['q'] if base['reselected'] else None
    # F9 generation is shared with S9. Small budgets plus the main result, no dense sweep.
    for budget in (10., 200., 600.):
        execute('F9_B'+str(int(budget)), ss, replace(cfg, movement_budget_m=budget), old)
    audit = numerical_audit(ss, cfg, base, pool)
    write_json(args.output/'S7.json', audit)
    write_json(args.output/'S2.json', dict(shapes=shape_control(),
        rows={k: dict(fixed_old=r['fixed_old'], reselected=r['reselected']) for k, r in records.items()},
        optimization='J remains objective; no global radius-objective optimization',
        score_calls=0, reuse='uniform final rows'))
    f11 = {k: clipping(*((cached[k][0], records[k]['reselected'], cached[k][3])))
           for k in ('standard_default', 'ordinary_default', 'tangent_default')}
    # A legal repeated first reading explicitly supplies the unbounded P control.
    same_rows, same_pool, same_cost = common_evaluation(ss, cfg, [ss.first.position])
    f11['same_station_unbounded_control'] = clipping(ss, same_rows[0], same_pool)
    write_json(args.output/'F11_S8.json', dict(rows=f11, accounting=same_cost,
        same_station_control='information diagnostic only; excluded from Q2 distinct-station choice'))
    far = (1499., 0.)
    write_json(args.output/'S3_counterexample.json', dict(source=far, candidate=ss.first.position,
        source_in_F=bool(ss.contains([far])[0]), correct_C_sig=check_candidate(ss, ss.first.position, False, policy),
        wrong_uniform_1000_intersection_accepts=distance(far, ss.first.position)<=1000,
        explanation='S always receives its fixed first signal; far source may have rho>=1499, not uniformly 1000'))
    files = ('sensitivity.py', 'diagnostics.py', 'q2.py', 'feasible.py', 'geometry.py', 'circle.py')
    write_json(args.output/'manifest.json', dict(command=sys.argv, python=sys.executable,
        platform=platform.platform(), numpy=np.__version__, config=cfg,
        source_hashes={f: hashlib.sha256((Path(__file__).parent/f).read_bytes()).hexdigest() for f in files},
        design_sha256=hashlib.sha256((Path(__file__).resolve().parents[2]/'docs/q1q2-design.md').read_bytes()).hexdigest(),
        optional={'S5':'NOT_RUN: optional frozen-field synthesis outside minimal scope',
                  'S6':'NOT_RUN: optional direction-only ablation outside minimal scope'},
        warnings=['No simulator; no official test; numerical estimates not certified bounds',
                  'S1 rounding is nearest-rounding outer model, not exact quantization',
                  'S3 known rho is extra information; S4 inside arena is artificial ablation',
                  'S7 symmetric coordinates need not be unique; variations are not error bounds',
                  'S9 B is metres, movement seconds=actual distance/5; B10 lower bound only standard'],
        reuse={'S2':'all final rows', 'S7':'standard default search and final candidates',
               'S8':'F11_S8.json', 'S9':'F9_B*.json plus standard_default'}))
    print('FINISHED', args.output, flush=True)


if __name__ == '__main__':
    main()
