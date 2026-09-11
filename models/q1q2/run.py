"""Explicit offline q1/q2/examples/figures commands; import has no experiment side effects."""
from __future__ import annotations
import argparse
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import numpy as np
from .geometry import NumericPolicy, BearingMeasurement, point, unit, bearing
from .adapters import read_measurements
from .q1 import solve
from .feasible import PhysicsConfig, build_source_set, check_candidate, posterior_contains
from .q2 import (SearchConfig, select_second_point, sample_sources, movement_frontier,
                 short_baseline_lower_bound, _sample_sources)
from .diagnostics import (analytic_cases, sensitivity_cases, compare_heuristics,
                          compare_geometry, DiagnosticConfig, reassess_old_point)
from .plots import ResultBundle, PlotStyle, render


def jsonable(value):
    if is_dataclass(value):
        result = {f.name: jsonable(getattr(value, f.name)) for f in fields(value)}
        if hasattr(value, 'diameter_estimate_m'):
            result['diameter_estimate_m'] = value.diameter_estimate_m
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(jsonable(value), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _q1_panel(result, name, global_view=False, truth=None):
    r, d, c = result.region, result.diameter, result.coverage
    panel = {'kind': 'geometry', 'title': f'{name}: {r.kind.value if r.kind else r.status}', 'polygons': [],
             'circles': [], 'points': [], 'lines': [], 'arrows': []}
    if r.vertices:
        panel['polygons'].append({'vertices': r.vertices, 'label': '纯角锥 P', 'fill': True})
    if d.endpoints:
        panel['lines'].append({'values': d.endpoints, 'label': f'd={d.length:.6g} m'})
    if c.forced_center:
        panel['circles'].append({'center': c.forced_center, 'radius': d.length/2, 'label': f'强制直径圆 {c.status}'})
    if result.minimum_circle.center:
        panel['circles'].append({'center': result.minimum_circle.center, 'radius': result.minimum_circle.radius,
                                 'color': 'C2', 'style': ':', 'label': f'最小覆盖圆 R={result.minimum_circle.radius:.6g} m'})
    if global_view or not r.vertices:
        panel['points'].append({'values': [o.position for o in result.measurements], 'label': '检测点'})
        for obs in result.measurements:
            theta = math.radians(obs.bearing_deg)
            for offset in (-obs.half_width_deg, 0, obs.half_width_deg):
                end = np.asarray(obs.position)+1600*unit(theta+math.radians(offset))
                panel['lines'].append({'values': (obs.position, point(end)), 'style': ':' if offset else '--',
                                       'label': f'{obs.bearing_deg:g}° ±{obs.half_width_deg:g}°' if offset == 0 else None})
    if truth is not None:
        panel['points'].append({'values': [truth], 'label': '合成真值', 'color': 'black', 'size': 30})
    if r.recession_direction and r.feasible_point:
        panel['arrows'].append({'start': r.feasible_point,
                                'end': point(np.asarray(r.feasible_point)+100*np.asarray(r.recession_direction))})
        panel['title'] += '（绘图范围非约束）'
    return panel


def q1_bundle(results, cases=None):
    figures, rows = [], []
    for name, result in results.items():
        case = (cases or {}).get(name, {})
        code = 'F2' if name == 'orthogonal' else 'F3' if name == 'equilateral20' else 'F3_36' if name == 'equilateral36' else f'F4_{name}' if name in ('empty', 'segment', 'thin', 'unbounded') else 'F1'
        panels = [_q1_panel(result, name)]
        if name.startswith('equilateral'):
            panels.insert(0, _q1_panel(result, name, True, case.get('synthetic_truth')))
        figures.append({'id': code, 'panels': panels,
                        'caption': f"{case.get('origin', 'manual')}；纯角锥；T={result.coverage.thales_max}；κ={result.coverage.kappa}；η={result.coverage.eta}"})
        rows.append({'case': name, 'N': len(result.measurements), 'kind': result.region.kind,
                     'vertices': len(result.region.vertices), 'area_m2': result.area_m2,
                     'diameter_m': result.diameter.length, 'radius_m': result.minimum_circle.radius,
                     'kappa': result.coverage.kappa, 'eta': result.coverage.eta, 'T': result.coverage.thales_max,
                     'cover': result.coverage.status})
    return ResultBundle(tuple(figures), {'T2': rows, 'T3': [
        {'operation': 'feasibility/recession', 'complexity': 'O(M^2)'},
        {'operation': 'exact_enumeration: bounded intersections and constraint checks', 'complexity': 'O(M^3)'},
        {'operation': 'diameter: all vertex pairs', 'complexity': 'O(V^2)'},
        {'operation': 'Welzl with exact support recheck', 'complexity': 'expected O(V), worst O(V^3)'},
        {'operation': 'circle enumeration fallback', 'complexity': 'O(V^4)',
         'note': 'Arithmetic operation counts; high-precision/rational bit-length costs are additional'}]}, {'design': 'PLAN v3'})


def q2_bundle(ss, result):
    if ss.status != 'OK' or ss.actual_point is None or result.q_best is None:
        return ResultBundle(tables={'T4': [{'status': result.status, 'stop_reason': result.stop_reason,
                                           'q': result.q_best, 'J_hat': result.diameter_estimate_m}]},
                            metadata={'source_status': ss.status, 'result_status': result.status,
                                      'figures_skipped': 'source_or_recommendation_unavailable'})
    source_samples = _sample_sources(ss, 2, result.config.source_grids, result.q_best,
                                     result.config.near_offset_m,
                                     second_half_width_deg=result.config.second_half_width_deg)
    p, s = ss.physics, ss.first.position
    candidate_points = {'IN': [], 'BOUNDARY': [], 'OUT': []}
    for row in result.grid_records:
        candidate_points[row['status'] if row['status'] in candidate_points else 'BOUNDARY'].append(row['q'])
    panel = {'kind': 'geometry', 'title': 'F 与解析保收候选域',
             'points': [{'values': source_samples.points, 'label': 'F 合法样本', 'color': 'C0'},
                        {'values': candidate_points['IN'], 'label': 'C_sig 解析检查 IN', 'color': 'C2'}],
             'circles': [{'center': p.arena_center, 'radius': p.arena_radius, 'label': '目标圆'}]}
    direction_points = [q for q in candidate_points['IN'] if check_candidate(ss, q, True, ss.policy).status == 'IN']
    panel['points'].append({'values': direction_points, 'label': 'C_dir 已判定内点', 'color': 'C3'})
    if result.q_best:
        panel['points'].append({'values': [result.q_best], 'label': '数值推荐点', 'color': 'black', 'size': 30})
    if s == p.arena_center and p.arena_radius >= p.rho_hi and p.rho_hi >= p.rho_lo:
        for r in (p.near_radius, p.rho_lo):
            centers = [point(np.asarray(s)+r*unit(math.radians(ss.first.bearing_deg+sign*ss.first.half_width_deg))) for sign in (-1, 1)]
            panel['points'].append({'values': centers, 'label': '5米极限位置' if r == p.near_radius else '半径分界位置', 'open': r == p.near_radius})
            panel['circles'].extend({'center': c, 'radius': p.rho_lo, 'label': '四圆盘约化', 'style': ':'} for c in centers)
    figures = [{'id': 'F5', 'panels': [panel], 'caption': f'{ss.first.error_mode}；保收不等于获得新示向信息'},
               {'id': 'F6', 'kind': 'heatmap', 'records': result.grid_records,
                'title': '最坏物理后验直径数值估计',
                'caption': f'{result.completed_stages}；{result.stop_reason}；非全局最优保证'}]
    for i, clear in enumerate(result.clearance_diagnostics):
        q, feedback = result.q_best, clear.feedback
        pts = np.asarray(source_samples.points)
        legal = pts[posterior_contains(ss, q, feedback, pts, ss.policy)]
        physical = {'kind': 'geometry', 'title': f'K 条件反馈 {feedback.kind}: {clear.status}',
                    'points': [{'values': legal.tolist(), 'label': 'K 合法样本'}], 'circles': [], 'polygons': []}
        if clear.estimated_center is not None:
            physical['circles'].append({'center': clear.estimated_center, 'radius': clear.R_hat, 'label': '条件 R_hat 样本圆（非保证）'})
        if clear.cover_center is not None:
            physical['circles'].append({'center': clear.cover_center, 'radius': clear.r_U, 'label': '保守覆盖圆', 'color': 'C2'})
        if clear.outer_vertices:
            physical['polygons'].append({'vertices': clear.outer_vertices, 'label': '保守外包 U'})
        # A global pair belongs only in panels accepting both endpoints (including beta).
        if result.score.witness and posterior_contains(
                ss, q, feedback, (result.score.witness.x, result.score.witness.y), ss.policy).all():
            physical['lines'] = [{'values': (result.score.witness.x, result.score.witness.y), 'label': '不可区分位置对'}]
        panels = [physical]
        angular = next((x for x in result.angular_comparison if x['feedback'] == feedback), None)
        if angular:
            panels.append(_q1_panel(angular['result'], '同反馈纯角锥 P'))
        figures.append({'id': f'F7_{i}', 'panels': panels,
                        'caption': f'绘图样本按结果配置重建，非终选完整点集；条件R_hat={clear.R_hat}；r_U={clear.r_U}；{clear.evidence}；不是 J_R'})
    assumed = ss.actual_point
    distances, area, exact_area = [], [], []
    for y in np.linspace(10, 1000, 80):
        q = point(np.asarray(s)+750*unit(math.radians(ss.first.bearing_deg))+y*unit(math.radians(ss.first.bearing_deg+90)))
        diagnostic = compare_geometry(assumed, (s, q), DiagnosticConfig(half_widths_deg=(ss.first.half_width_deg, result.config.second_half_width_deg),
                                                                            source_origin='assumed_source_in_F'))
        distances.append(float(y))
        area.append(diagnostic.linear_area_m2)
        exact = solve((BearingMeasurement(s, bearing(s, assumed), ss.first.half_width_deg),
                       BearingMeasurement(q, bearing(q, assumed), result.config.second_half_width_deg)), ss.policy)
        exact_area.append(exact.area_m2)
    figures.append({'id': 'F8', 'kind': 'curve', 'series': [{'x': distances, 'y': area, 'label': '局部条带面积近似'},
                                                          {'x': distances, 'y': exact_area, 'label': '同构型纯角锥面积'}],
                    'xlabel': '侧移 / m', 'ylabel': '面积 / m²', 'caption': f'假定源位置；两曲线半宽均为 ({ss.first.half_width_deg}, {result.config.second_half_width_deg})°；r2 与交角同时变化；90°仅固定距离最优'})
    table = [{'q': result.q_best, 'J_hat': result.diameter_estimate_m, 'movement_m': result.movement_m,
              'source_change_m': result.source_change_m, 'station_change_m': result.station_change_m,
              'tolerance_change_m': result.tolerance_change_m, 'status': result.status,
              'conditional_clearance': jsonable(result.clearance_diagnostics)}]
    return ResultBundle(tuple(figures), {'T4': table, 'T6': list(result.refinement_history)},
                        {'first': jsonable(ss.first), 'physics': jsonable(p), 'config': jsonable(result.config)})


def _config(path):
    data = json.loads(Path(path).read_text(encoding='utf-8')) if path else {}
    physics = PhysicsConfig(**data.get('physics', {}))
    policy = NumericPolicy(**data.get('policy', {}))
    search = dict(data.get('search', {}))
    if 'source_grids' in search:
        search['source_grids'] = tuple(tuple(x) for x in search['source_grids'])
    if 'station_steps_m' in search:
        search['station_steps_m'] = tuple(search['station_steps_m'])
    return physics, policy, SearchConfig(**search, policy=policy)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('q1', 'q2', 'examples'):
        p = sub.add_parser(name)
        if name != 'examples':
            p.add_argument('input', type=Path)
        p.add_argument('--config', type=Path)
        p.add_argument('--output', type=Path)
        if name in ('examples', 'q2'):
            p.add_argument('--frontier', action='store_true')
            p.add_argument('--sensitivity', action='store_true')
        if name == 'examples':
            p.add_argument('--include-q2', action='store_true')
    p = sub.add_parser('figures')
    p.add_argument('bundle', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--font', default='Noto Sans CJK SC')
    args = parser.parse_args(argv)
    if args.command == 'figures':
        payload = json.loads(args.bundle.read_text(encoding='utf-8'))
        render(ResultBundle(tuple(payload['figures']), payload.get('tables', {}), payload.get('metadata', {})),
               args.output, PlotStyle(font_family=args.font))
        return
    output = args.output or Path(__file__).parent/'outputs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    physics, policy, config = _config(args.config)
    payload, bundles = {}, []
    if args.command == 'q1':
        measurements = read_measurements(args.input)
        result = solve(measurements, policy)
        payload['q1'] = result
        bundles.append(q1_bundle({'input': result}))
    elif args.command == 'examples':
        cases = analytic_cases()
        results = {name: solve(case['measurements'], policy) for name, case in cases.items()}
        payload.update(q1=results, analytic_inputs=cases)
        bundles.append(q1_bundle(results, cases))
    if args.command == 'q2' or (args.command == 'examples' and args.include_q2):
        measurements = read_measurements(args.input) if args.command == 'q2' else (BearingMeasurement((0., 0.), 0., measurement_id='standard'),)
        if len(measurements) != 1:
            raise ValueError('Q2 requires exactly one first omnidirectional direction measurement')
        first = measurements[0]
        # The configured second bound is explicit; the example config follows the first error mode.
        if args.config is None:
            config = replace(config, second_half_width_deg=first.half_width_deg)
        ss = build_source_set(first, physics, policy)
        result = select_second_point(ss, config)
        payload.update(q2=result, source_set=ss)
        write_json(output/'results.json', payload)
        bundles.append(q2_bundle(ss, result))
        payload['heuristics'] = compare_heuristics(ss, config, result.q_best) if ss.status == 'OK' else ()
        rows = [{'strategy': r['strategy'], 'J_hat': r['score'].J_hat if r['score'] else None,
                 'conditional_R_hat': r['clearance'].R_hat if r['clearance'] else None,
                 'clearance': r['clearance'].status if r['clearance'] else 'INFEASIBLE',
                 'movement_m': r['movement_m']} for r in payload['heuristics']]
        bundles.append(ResultBundle(({'id': 'F10', 'kind': 'bars', 'labels': [r['strategy'] for r in rows if r['J_hat'] is not None],
                                      'values': [r['J_hat'] for r in rows if r['J_hat'] is not None], 'ylabel': 'J_hat / m',
                                      'caption': '同信息、同精度；条件覆盖状态另列 T5'},), {'T5': rows}))
        if args.frontier and ss.status == 'OK':
            budgets = (0, 10, 50, 100, 200, 400, 600, 800, 1000, 1500, 2000, 3000)
            frontier = movement_frontier(ss, budgets, config)
            payload['frontier'] = frontier
            bound = short_baseline_lower_bound(ss, 500, 1500, 10, config.second_half_width_deg)
            payload['short_baseline_bound'] = bound
            series = [{'x': list(budgets), 'y': [r.score.J_hat if r.score else r.baseline.J_hat if r.baseline else None for r in frontier],
                       'label': '预算最坏直径样本估计'}]
            if bound:
                series.append({'x': [10], 'y': [bound['lower_bound_m']], 'label': 'B=10解析下界（非最优值）', 'style': 'x'})
            bundles.append(ResultBundle(({'id': 'F9', 'kind': 'curve', 'series': series, 'xlabel': '预算 B / m',
                                          'ylabel': 'V(B) 数值估计 / m', 'caption': '实际移动与预算分列；有限网格结果'},)))
        if args.sensitivity and ss.status == 'OK':
            experiments = []
            for group, name, variant, overrides in sensitivity_cases(first, physics, policy):
                cfg = replace(config, second_half_width_deg=variant.first.half_width_deg, **overrides)
                old_assessment = reassess_old_point(variant, result.q_best, cfg)
                new = select_second_point(variant, cfg)
                experiments.append({'group': group, 'name': name, 'old_q_check': old_assessment['signal_check'],
                                    'old_q_admissibility': {k: v for k, v in old_assessment.items() if k != 'score'},
                                    'old_q_score': old_assessment['score'], 'new_result': new})
            payload['sensitivity'] = experiments
            s1 = [r for r in experiments if r['group'] == 'S1']
            bundles.append(ResultBundle(({'id': 'F11', 'kind': 'bars', 'labels': [r['name'] for r in s1],
                                          'values': [r['new_result'].diameter_estimate_m for r in s1], 'ylabel': 'J_hat / m',
                                          'caption': '理论1° 与最近舍入外包1.005°；非官方舍入事实'},),
                                        {'T6_sensitivity': jsonable(experiments)}))
    tables = {k: v for b in bundles for k, v in b.tables.items()}
    tables['T1'] = [
        {'category': '题面事实', 'statement': '每源固定未知半径1000—1500米；5米near；20米清除；东0°逆时针', 'source': '题面附录2'},
        {'category': '附件事实', 'statement': '允许域外检测；合法反馈direction/near/no_signal；示向度两位小数', 'source': '附件2'},
        {'category': '合理推断', 'statement': '同一定位时段静止源、同一会话与未清除阶段', 'source': 'PLAN §0.5'},
        {'category': '主动简化', 'statement': '异点未知固定有界误差场的全组合外包；最坏直径优先且保收', 'source': 'PLAN §0.5—0.6'},
        {'category': '待明确', 'statement': '官方舍入顺序及±1°是否包含量化未知；1.005°仅最近舍入外包', 'source': 'PLAN §0.6'}]
    bundle = ResultBundle(tuple(f for b in bundles for f in b.figures), tables,
                          {'design': 'PLAN.md v3', 'numerical_claim': 'NUMERICAL_CANDIDATE; refinement spread is not a bound'})
    write_json(output/'results.json', payload)
    write_json(output/'bundle.json', bundle)
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}
    manifest = {'input': str(getattr(args, 'input', 'analytic')), 'config': config, 'physics': physics,
                'seed': config.seed, 'source_sha256': sources, 'python': platform.python_version(),
                'dependencies': {name: version(name) for name in ('numpy', 'matplotlib', 'pytest')},
                'files': ['results.json', 'bundle.json', 'manifest.json'], 'command': vars(args)}
    write_json(output/'manifest.json', manifest)


if __name__ == '__main__':
    main()
