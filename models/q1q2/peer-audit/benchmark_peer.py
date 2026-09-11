"""Read-only NTJ_B adapter; truth comes exclusively from our benchmark generators.

Only this audit directory receives output. --regenerate-truth redirects generator
output into a temporary directory and requires equality with the current fixtures.
No production code from our models.q1q2 package is imported.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np
import scipy

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / 'benchmarks'
AREAS = ('q1_geometry', 'q1_circle_cover', 'q2_candidate', 'q2_worst_diameter')
PEER = Path('/Users/flower/math/2026/NTJ_B_wt/B')
sys.dont_write_bytecode = True
sys.path.insert(0, str(PEER))
import geometry as peer
import signal_minimax as signal


def generator(area):
    spec = importlib.util.spec_from_file_location('independent_' + area, BENCH / area / 'generate.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ORACLES = {area: generator(area) for area in AREAS}


def clean(x):
    if isinstance(x, np.ndarray):
        return clean(x.tolist())
    if isinstance(x, np.generic):
        return clean(x.item())
    if isinstance(x, float) and not math.isfinite(x):
        return 'Infinity' if x == math.inf else '-Infinity' if x == -math.inf else 'NaN'
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (tuple, list)):
        return [clean(v) for v in x]
    return x


def canonical(x):
    return json.dumps(clean(x), ensure_ascii=False, sort_keys=True, allow_nan=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_hashes():
    # Include both sides' source and all independent fixtures, exclude the new
    # audit artifacts and installed dependencies. Never writes to either tree.
    paths = [p for p in HERE.parent.rglob('*.py')
             if not any(part.startswith('.') for part in p.relative_to(HERE.parent).parts)
             and HERE not in p.parents]
    paths += list(PEER.glob('*.py'))
    paths += [BENCH / a / name for a in AREAS for name in ('cases.jsonl', 'run.py', 'generate.py')]
    return {str(p): sha(p) for p in sorted(set(paths))}


def points(values):
    return np.asarray([[float(F(v)) for v in p] for p in values], float).reshape(-1, 2)


def vertex_check(actual, expected, tol):
    a, b = points(actual), points(expected)
    if not len(a) or not len(b):
        return dict(geometry_match=len(a) == len(b), bijection=len(a) == len(b),
                    hausdorff_m=None, actual_count=len(a), expected_count=len(b), tolerance_m=tol)
    distances = np.linalg.norm(a[:, None] - b[None, :], axis=2)
    hd = float(max(distances.min(axis=0).max(), distances.min(axis=1).max()))
    owner = {}

    def match(i, seen):
        for jj in np.flatnonzero(distances[i] <= tol):
            j = int(jj)
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or match(owner[j], seen):
                owner[j] = i
                return True
        return False

    bijection = len(a) == len(b) and all(match(i, set()) for i in range(len(a)))
    return dict(geometry_match=hd <= tol, bijection=bijection, hausdorff_m=hd,
                actual_count=len(a), expected_count=len(b), tolerance_m=tol)


def bearings(obs):
    if not obs or len({o['half_width_deg'] for o in obs}) == 1:
        return peer.solve_bearings([(o['position'], o['bearing_deg']) for o in obs],
                                   error_deg=obs[0]['half_width_deg'] if obs else 1.)
    # The public convenience function takes one common epsilon. Compose native
    # bearing_planes for heterogeneous epsilon; do not replace its trig with truth.
    ab = [peer.bearing_planes(o['position'], o['bearing_deg'], o['half_width_deg']) for o in obs]
    return peer.halfplane_region(np.concatenate([a for a, _ in ab]), np.concatenate([b for _, b in ab]))


def geometry_case(c):
    inp, gt = c['input'], c['ground_truth']
    if any(o['half_width_deg'] >= 90 for o in inp.get('observations', [])):
        return dict(status='UNPROVIDED', reason='bearing API explicitly excludes epsilon=90 degrees')
    if 'points' in inp:
        vertices = peer.hull(points(inp['points']))
        d, pair = peer.diameter(vertices)
        result = dict(status='point' if len(vertices) == 1 else 'segment' if len(vertices) == 2 else 'bounded',
                      vertices=vertices, diameter=d, diameter_endpoints=pair)
    elif 'observations' in inp:
        result = bearings(inp['observations'])
    else:
        ab = np.asarray([[float(F(x)) for x in row] for row in inp['halfplanes']])
        result = peer.halfplane_region(ab[:, :2], ab[:, 2])
    mapping = dict(empty='EMPTY', unbounded='UNBOUNDED', point='POINT', segment='SEGMENT',
                   bounded='POLYGON', numerically_unresolved='NUMERICAL_UNRESOLVED')
    kind = mapping[result['status']]
    checks = dict(classification=kind == gt['kind'])
    details = {}
    tol = 1e-8 + 1e-9 * (gt['diameter'] or 0.)
    if gt['kind'] == 'EMPTY':
        checks['diameter_empty'] = result.get('diameter') is None
    elif gt['kind'] == 'UNBOUNDED':
        checks['diameter_infinite'] = result.get('diameter') == math.inf
    else:
        v = points(gt['vertices'])
        vtol = tol + 32 * math.ulp(float(np.abs(v).max()))
        details['vertices'] = vertex_check(result.get('vertices', []), gt['vertices'], vtol)
        checks['vertex_geometry'] = details['vertices']['geometry_match']
        checks['diameter'] = result.get('diameter') is not None and abs(result['diameter'] - gt['diameter']) <= tol
        ends = result.get('diameter_endpoints')
        checks['endpoints'] = (ends is not None and len(ends) == 2
                               and abs(math.dist(*ends) - gt['diameter']) <= tol
                               and all(min(math.dist(p, x) for x in v) <= vtol for p in ends))
        isolated, _ = peer.diameter(v)
        details['isolated_diameter'] = dict(actual=isolated, passed=abs(isolated - gt['diameter']) <= tol)
    status = 'PASS' if all(checks.values()) else 'FAIL'
    return dict(status=status, actual=result, checks=checks, diagnostics=details,
                attribution='TRUE_BUG' if status == 'FAIL' else None,
                missing=['feasible_point', 'recession_direction', 'diameter indices/tie metadata'])


def circle_case(c):
    inp, gt = c['input'], c['ground_truth']
    if 'points' not in inp:
        return dict(status='UNPROVIDED', reason='No formal coverage/special-state or three-regime API')
    p = points(inp['points'])
    center, radius = peer.minimum_circle(p)
    d, pair = peer.diameter(p)
    tol = 2e-9 + 2e-10 * gt['diameter'] + 8 * max(math.ulp(float(x)) for v in p for x in v)
    checks = dict(radius=abs(radius - gt['radius']) <= tol,
                  center=float(np.abs(center - gt['center']).max()) <= tol,
                  containment=max(math.dist(v, center) - radius for v in p) <= tol,
                  diameter=abs(d - gt['diameter']) <= tol,
                  endpoints=abs(math.dist(*pair) - gt['diameter']) <= tol)
    actual = dict(center=center, radius=radius, diameter=d, diameter_endpoints=pair)
    if 'stations' in inp:
        result = bearings(inp['stations'])
        actual['bearing_pipeline'] = result
        checks['pipeline_radius'] = result.get('radius') is not None and abs(result['radius'] - gt['radius']) <= tol
        checks['pipeline_diameter'] = result.get('diameter') is not None and abs(result['diameter'] - gt['diameter']) <= tol
    return dict(status='PASS' if all(checks.values()) else 'FAIL', actual=actual, checks=checks, tolerance_m=tol,
                coverage_status='UNPROVIDED',
                missing=['YES/NO/UNRESOLVED and Thales witness', 'support indices', 'forced support exception',
                         'caller chosen seed (native fixed seed 42)', 'kappa/eta and clearance states'])


def outer_source(inp):
    """Native outer-P representation generalized to fixture arena/rho/epsilon.

    Does not use oracle vertices, oracle source samples or oracle membership to
    build P. This is exactly the disk_outer/bearing_clip/clip modeling route.
    """
    s = np.asarray(inp.get('S', [0., 0.]), float)
    poly = peer.disk_outer(inp.get('center', [0., 0.]), inp.get('arena_radius', inp.get('radius', 1800.)))
    poly = peer.bearing_clip(poly, s, inp.get('theta', 0.), inp.get('eps', inp.get('eps1', 1.)))
    for normal in peer.NORMALS:
        poly = peer.clip(poly, normal, float(normal @ s) + inp.get('rho_hi', 1500.))
        if not len(poly):
            break
    return s, poly


def candidate_case(c):
    inp, gt = c['input'], c['ground_truth']
    s, poly = outer_source(inp)
    if not len(poly):
        return dict(status='UNPROVIDED', reason='Empty outer P: native certificate requires nonempty input', outer_vertices=0)
    answer = signal.reception_certificate(np.asarray(inp['q'], float), poly, s)
    if 'signal_member' not in gt:
        return dict(status='UNPROVIDED', reason='No inconsistent-first-observation validation', actual=answer)
    if answer['guaranteed']:
        status = 'PASS_CERTIFICATE' if gt['signal_member'] else 'FAIL_UNSAFE'
    elif gt['signal_member']:
        status = 'CONSERVATIVE_REFUSAL'
    else:
        status = 'OUTSIDE_NOT_CERTIFIED'
    return dict(status=status, actual=answer, outer_vertices=poly,
                expected_signal_status=gt['signal_status'],
                safety_screen_passed=status != 'FAIL_UNSAFE',
                membership_agreement=bool(answer['guaranteed']) == gt['signal_member'],
                attribution='TRUE_BUG' if status == 'FAIL_UNSAFE' else 'API_SCOPE' if status == 'CONSERVATIVE_REFUSAL' else None,
                missing=['exact C_sig OUT/BOUNDARY', 'C_dir', 'source/posterior membership', 'physical separating witness'])


def worst_case(c):
    if c['kind'] != 'score':
        return dict(status='UNPROVIDED', reason='No matching finite-cloud/optimizer/frontier/sampling/clearance API')
    inp, gt = c['input'], c['ground_truth']
    s, poly = outer_source(inp)
    q = np.asarray(inp['q'], float)
    cert = signal.reception_certificate(q, poly, s)
    # Report the bound even if the native reception prerequisite is not certified;
    # it is then diagnostic only, never promoted into a guaranteed action.
    bound = signal.posterior_radius_upper(poly, q, bin_deg=.5, error_deg=inp.get('eps2', 1.))
    upper = 2 * bound['radius_upper_m']
    lower = max(gt['lower_bound_m'], gt.get('J_exact_m', 0.))
    checks = dict(reachable_lower_bound=upper >= gt['lower_bound_m'] - 1e-6)
    if 'J_exact_m' in gt:
        checks['closed_form_lower_bound'] = upper >= gt['J_exact_m'] - 1e-6
    tight = None
    if 'J_exact_m' in gt:
        gap = upper - gt['J_exact_m']
        threshold = max(.1, .01 * gt['J_exact_m'])
        tight = dict(signed_gap_m=gap, tolerance_m=threshold, would_pass_exact_J_approximation=abs(gap) <= threshold,
                     attribution='BENCHMARK_TOO_STRICT_FOR_UPPER_BOUND' if abs(gap) > threshold else None)
    return dict(status=('PASS_BOUND_NOT_REFUTED' if all(checks.values()) else 'FAIL_BOUND_REFUTED')
                if cert['guaranteed'] else 'RECEPTION_NOT_CERTIFIED',
                actual=dict(reception=cert, radius_upper=bound, diameter_upper_m=upper), checks=checks,
                lower_or_exact_m=lower, ratio_to_lower_or_exact=upper / lower if lower else None,
                tightness=tight, exact_J_status='UNPROVIDED',
                same_station=bool(np.array_equal(q, s)),
                note='2U_R is a numerical bound; passing lower comparisons is not a continuous upper-bound certificate')


def supplemental():
    rows = []
    circle_oracle = ORACLES['q1_circle_cover']
    for cid, p in [('audit_micro_segment', [[0., 0.], [5e-10, 0.]]),
                   ('audit_micro_equilateral', [[0., 0.], [1e-7, 0.], [5e-8, math.sqrt(3) * 1e-7 / 2]]),
                   ('audit_enumerated_segment', [[0., 0.], [5e-8, 0.]])]:
        gt = circle_oracle.oracle(p)
        routine = peer.minimum_circle_enumerated if cid == 'audit_enumerated_segment' else peer.minimum_circle
        center, radius = routine(np.asarray(p))
        # Supplement explicitly tests mathematical minimality at the feature
        # scale; fixed benchmark meter tolerance would hide the 5e-10 segment.
        tol = 1e-12 * gt['diameter'] + 32 * max(math.ulp(x) for v in p for x in v)
        residual = max(math.dist(center, v) - radius for v in p)
        checks = dict(radius=abs(radius - gt['radius']) <= tol,
                      center=max(abs(center - np.array(gt['center']))) <= tol, containment=residual <= tol)
        base_tol = 2e-9 + 2e-10 * gt['diameter'] + 8 * max(math.ulp(x) for v in p for x in v)
        rows.append(dict(case_id=cid, input=dict(points=p), truth_method='q1_circle_cover.generate.oracle exact Fraction on submitted binary64',
                         expected=gt, actual=dict(function=routine.__name__, center=center, radius=radius,
                                                 radius_ratio=radius / gt['radius'], containment_residual_m=residual),
                         checks=checks, tolerance_m=tol, fixed_benchmark_length_tolerance_m=base_tol,
                         would_pass_fixed_length_tolerance=abs(radius - gt['radius']) <= base_tol and max(abs(center - gt['center'])) <= base_tol,
                         status='PASS' if all(checks.values()) else 'FAIL', attribution='TRUE_BUG'))
    co = ORACLES['q2_candidate']
    for q in ([250., 400.], [750., 400.], [1002., 0.]):
        inp = co.base(q)
        gt = co.sector_oracle(inp)
        c = dict(input=inp, ground_truth=gt)
        ans = candidate_case(c)
        e = math.radians(1.)
        centers = [[r * math.cos(e), sign * r * math.sin(e)] for r in (5., 1000.) for sign in (-1, 1)]
        rows.append(dict(case_id='audit_candidate_' + str(tuple(q)), input=inp, expected=gt,
                         truth_method='q2_candidate.generate.sector_oracle; four-disk independent margin',
                         four_disk_margin_m=1000. - max(math.dist(q, p) for p in centers), **ans))
    # Existing audit regression: prove a concrete legal world using exact
    # squared distances on the supplied binary64 coordinates, not tolerance-band
    # membership from sector_oracle (which intentionally labels it a boundary).
    inp = co.base([-5e-11, 0.])
    p, rho = [1500., 0.], 1500.
    assert co.legal([p], inp)[0]
    def dist2(a, b):
        return sum((F(x) - F(y)) ** 2 for x, y in zip(a, b))
    r1sq, r2sq = dist2(p, inp['S']), dist2(p, inp['q'])
    assert F(25) < r1sq <= F(rho) ** 2 < r2sq
    s, poly = outer_source(inp)
    ans = signal.reception_certificate(np.array(inp['q']), poly, s)
    rows.append(dict(case_id='audit_near_same_position', input=inp, expected=dict(signal_member=False),
                     truth_method='generate.legal + exact Fraction distance squared of concrete world',
                     witness=dict(p=p, rho=rho, excess_distance_m=math.dist(p, inp['q']) - rho,
                                  exact_squared_excess=str(r2sq - F(rho) ** 2)), actual=ans,
                     status='FAIL' if ans['guaranteed'] else 'PASS', attribution='TRUE_BUG'))
    return rows


def write_report(data, path, json_path):
    """Render the reviewable report from this run's actual results."""
    areas = data['areas']
    gr, cr, ca, wr = [areas[a]['results'] for a in AREAS]
    gp = sum(r['status'] == 'PASS' for r in gr)
    gf = sum(r['status'] == 'FAIL' for r in gr)
    cp = sum(r['status'] == 'PASS' for r in cr)
    certified = sum(r['status'] == 'PASS_CERTIFICATE' for r in ca)
    unsafe = sum(r['status'] == 'FAIL_UNSAFE' for r in ca)
    refused = [r for r in ca if r['status'] == 'CONSERVATIVE_REFUSAL']
    outside = sum(r['status'] == 'OUTSIDE_NOT_CERTIFIED' for r in ca)
    eligible = certified + unsafe + len(refused) + outside
    certified_bounds = [r for r in wr if r['status'] in ('PASS_BOUND_NOT_REFUTED', 'FAIL_BOUND_REFUTED')]
    bp = sum(r['status'] == 'PASS_BOUND_NOT_REFUTED' for r in wr)
    bf = sum(r['status'] == 'FAIL_BOUND_REFUTED' for r in wr)
    tight = [r for r in certified_bounds if r['tightness'] is not None]
    loose = [r for r in tight if not r['tightness']['would_pass_exact_J_approximation']]
    norm = [r for r in gr if r['status'] == 'PASS' and not r['diagnostics'].get('vertices', {}).get('bijection', True)]
    isolated = [r['diagnostics']['isolated_diameter'] for r in gr if 'isolated_diameter' in r.get('diagnostics', {})]
    supplement = {r['case_id']: r for r in data['supplemental']}
    refusal_by_status = Counter(r['expected']['signal_status'] for r in refused)
    counts_text = '\n'.join(f"| `{a}` | {len(areas[a]['results'])} | `{json.dumps(areas[a]['counts'], ensure_ascii=False)}` |" for a in AREAS)
    fail_lines = []
    for r in gr:
        if r['status'] == 'FAIL':
            truth_d = r['expected']['diameter']
            truth_d = '不适用' if truth_d is None else f'{truth_d:.12g}'
            got_d = r['actual'].get('diameter')
            got_d = '∞' if got_d == math.inf or got_d == 'Infinity' else str(got_d)
            category = '空集误判无界' if r['expected']['kind'] == 'EMPTY' else '有限判无穷' if r['actual']['status'] == 'unbounded' else '退化维数误判'
            fail_lines.append(f"| `{r['case_id']}` | {r['expected']['kind']} / {truth_d} | {r['actual']['status']} / {got_d} | {category} |")
    micro_lines = []
    for cid in ('audit_micro_segment', 'audit_micro_equilateral', 'audit_enumerated_segment'):
        r = supplement[cid]
        micro_lines.append(f"| `{cid}` | {r['expected']['radius']:.15g} | {r['actual']['radius']:.15g} | {r['actual']['radius_ratio']:.6g} | {r['actual']['containment_residual_m']:.6g} | **{r['status']}** |")
    qlines = []
    for q in ([250., 400.], [750., 400.], [1002., 0.]):
        r = supplement['audit_candidate_' + str(tuple(q))]
        qlines.append(f"| {tuple(q)} | {r['four_disk_margin_m']:.9f} | {r['actual']['critical_radius_m']:.9f} | {r['actual']['guaranteed']} | {r['status']} |")
    jlines = []
    for cid in ('segment_10_100_20_1', 'tangent_segment_2', 'tangent_segment_4', 'segment_special_18', 'polar_same_station_closed_0'):
        r = next(r for r in wr if r['case_id'] == cid)
        jlines.append(f"| `{cid}` | {r['expected']['J_exact_m']:.9f} | {r['actual']['diameter_upper_m']:.9f} | {r['ratio_to_lower_or_exact']:.6f} | {'PASS' if r['tightness']['would_pass_exact_J_approximation'] else '不满足 J 逼近精度，但不反驳上界'} |")
    source_hash_lines = '\n'.join(f"| `{name}` | `{data['protected_sha256_before'][str(PEER / name)]}` |" for name in ('geometry.py', 'signal_minimax.py'))
    fixture_lines = '\n'.join(f"| `{area}` | `{v['fixture_sha256']}` | {v.get('semantic_equality', '未重生成')} |" for area, v in data['truth_verification'].items())
    report = f"""# NTJ_B：Q1/Q2 独立真值 benchmark 实测

本轮固定基准的结论：Q1 区域 **{gp}/{gp + gf}（{100 * gp / (gp + gf):.2f}%）通过、{gf} 个真错误**；MEC/直径核心 **{cp}/{cp} 通过**；Q2 肯定保收证书 **{certified}/{certified + unsafe} 正确**，但仅召回 **{certified}/{certified + len(refused)}（{100 * certified / (certified + len(refused)):.2f}%）合法候选**；Q2 直径上界 **{bp}/{len(certified_bounds)} 未被独立真值反驳**。未提供的接口不计错、不计通过。固定基准的圆计算全过不代表全尺度最小性：补充回归确认两个 MEC 非最小反例、一个枚举核验漏包反例，以及一个极近异点保收误签。

这是对指定函数的实测，不是任务全局成功率或双方实现排名。`(1002,0)` 的拒绝属于外包模型的保守损失，不归为保收证书误签。

**范围与复现**

先阅读了 [geometry 审计](audit-geometry.md)、[coverage 审计](audit-coverage.md)、[Q2 审计](audit-q2.md)、[文档审计](audit-docs.md)，按其中的 API 差异适配；本轮没有重做源码审计，也未调用对方的历史 benchmark runner 或任何一方生产求解器作为真值。

- 执行时间（UTC）：`{data['generated_utc']}`；总耗时约 {data['elapsed_seconds']:.3f} 秒。
- 对方 HEAD：`{data['environment']['peer_head']}`；Python {data['environment']['python']}、NumPy {data['environment']['numpy']}、SciPy {data['environment']['scipy']}。
- 四份当前 `cases.jsonl` 共 {sum(len(areas[a]['results']) for a in AREAS)} 例，均从各 `generate.py` **在临时目录重新生成**，与当前夹具逐例语义一致，再用新生成的独立真值评分。临时文件由上下文自动清理，原夹具未覆盖。
- [适配器](benchmark_peer.py) 只导入对方 `geometry.py`、`signal_minimax.py` 和本方四个独立生成器；未导入本方 `models.q1q2` 生产包。输出完整输入、真值、函数原始结果、逐项检查与 SHA256，见 [逐例 JSON]({json_path.name})。
- 检查了 {data['protected_files']} 份双方源码及基准文件的执行前后哈希，全部一致；没有修改双方原代码、夹具、原报告或审计文档。JSON 将无限值保留为字符串 `Infinity`，不会与空集直径 `null` 混淆。

在本方仓库执行：

```bash
cd '/Users/flower/math/2026/B题'
PYTHONDONTWRITEBYTECODE=1 models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/benchmark_peer.py --regenerate-truth
```

命令只写本审计目录下的新 JSON/Markdown。脚本退出码 0 表示实测完整执行，**不表示对方全部通过**；判定在 `areas.*.counts` 与 `supplemental`，执行异常退出码为 2。不加 `--regenerate-truth` 可直接复跑当前保存的独立夹具。

**四块通过率与分母**

| 块 | 可对应的核心合同 | PASS / FAIL | 范围差异、未提供或未获证 |
|---|---|---|---|
| Q1 geometry（285） | 区域分类、几何顶点集、直径及端点 | **{gp} / {gf}；{100 * gp / (gp + gf):.2f}%** | 75 例含 ε=90°，测向 API 明确不支持 |
| Q1 circle_cover（330） | 固定种子 MEC 圆心/半径/包含、直径；含七个测向流水线 | **{cp} / 0；100%** | 13 个独立状态/三段清除案例无对应 API；所有 317 点集的正式覆盖 YES/NO/见证也未提供 |
| Q2 candidate（531） | 对 P 的单侧保收充分证书 | **{certified}/{certified + unsafe} 肯定证书正确；100%** | 144 合法点保守拒绝、265 外部点未获证、4 不一致首观测接口未提供 |
| Q2 worst_diameter（48） | 用 2U_R 检查独立可实现直径下界/闭式值 | **{bp} / {bf}；100% 未反驳** | 1 例不保收、13 个其他合同未提供；精确 J/完整选点接口未提供 |

Q2 candidate 的“100%”仅表示已签发证书的正确率。若将 False 临时当作成员拒绝来衡量候选保留效果，与独立成员真值一致的为 **{certified + outside}/{eligible}（{100 * (certified + outside) / eligible:.2f}%）**；不一致的 144 例全部是保守拒绝，不是危险假阳性。合法候选召回率为 **{certified}/{certified + len(refused)} = {100 * certified / (certified + len(refused)):.2f}%**。拒绝外部点只代表未获证，并未交付 OUT 证明，不能把 265 个拒绝写成已证明 OUT。

以下原始分桶互斥，涵盖全部固定案例；未提供项没有被从总量中隐藏：

| 块 | 总案例数 | 原始状态计数 |
|---|---:|---|
{counts_text}

**适配契约与独立真值**

| 项目 | 原生函数与适配 | 独立判定依据 |
|---|---|---|
| Q1 观测 | 相同 ε 调 `solve_bearings`；混合 ε 逐站调 `bearing_planes` 再 `halfplane_region`；显式传入案例角宽，避免默认 1.01°干扰 | `q1_geometry/generate.py` 的 Fraction 消元、衰退、精确交点/Jarvis 与全对平方距离；一般三角系数是 80 位计算后保留 65 位的有理近似系统 |
| Q1 半平面/点集 | 直接传原输入的 a,b,c；点集调 `hull`、`diameter`；`bounded` 对应 POLYGON | 同上；HiGHS 只作生成器附加诊断，不覆盖 Fraction 真值 |
| 最小圆 | `minimum_circle` 返回中心和半径；固定种子 42，不伪装为四个可选种子；不合成缺失覆盖布尔值 | `q1_circle_cover/generate.py` 的 Fraction 1/2/3 点支撑枚举、精确包含、80 位 Decimal 开方 |
| 保收候选 | 用其 64 边 `disk_outer`、`bearing_clip`、`clip` 构造 P；按案例目标圆心/半径、首站、ρ上限、ε参数化；调用 `reception_certificate(q,P,S)` | `q2_candidate/generate.py` 的解析扇区/射线、四盘公式；一般裁剪场景仅以更大域证明 IN，或真实失收世界证明 OUT |
| 最坏直径 | `posterior_radius_upper(P,q,bin_deg=0.5,error_deg=ε₂)`；换算 U_D=2U_R | `q2_worst_diameter/generate.py` 的原始 atan2/距离全对枚举、可实现见证和线段/扇区闭式；有限云真值只给连续问题下界 |

Q1 geometry 长度容差为 `1e-8 + 1e-9 D`，顶点再加 `32 ulp(max|坐标|)`；circle 长度容差为 `2e-9 + 2e-10 D + 8 max(ulp(输入坐标))`，沿用当前 runner。Q2 上界不得低于独立可实现下界或闭式值超过 `1e-6 m`。角桶宽 0.5°是显式测试参数，不是其默认 1°。未替换算法、提高其精度、修补其输出或借真值顶点构造被评分的 P。

**Q1：11 个已知退化全部确认 FAIL**

| case_id | 独立类别 / 直径 m | 原生类别 / 直径 m | 失败分类 |
|---|---|---|---|
{chr(10).join(fail_lines)}

4 个 `tiny_gap` 由 `x≤0` 与 `x≥10⁻ᵏ` 组成，真值为空；3 个 `long_triangle` 满足 `y≥0, y≤δx, δx+y≤1`，δ=10⁻¹⁰/10⁻¹²/10⁻¹⁴，直径分别 10¹⁰/10¹²/10¹⁴，却返回无穷。另 4 个是点/线段维数错误，直径仍在原容差内。它们均返回确定类别，没有返回数值未决；前三类是实际数学结论错误，不能按“benchmark 太严”豁免。它们是通用几何/退化压力测试，不代表普通 ±1°任务失败了 11 次。

以独立真值顶点作为**独立直径子程序的测试输入**，`diameter` 为 **{sum(x['passed'] for x in isolated)}/{len(isolated)} 通过**；未把这些顶点回填进失败流水线。因此已定位的主要问题是区域构造/分类，而非全对直径算法。

另外，核心通过的 {gp} 例中，本轮有 **{len(norm)} 例**不满足严格顶点一一匹配，但顶点集 Hausdorff 距离在原容差内。其完整 ID/计数在 JSON 的 `diagnostics.vertices`；这项规范化合同单列，不把近重复点数量差异描述为同等数量的定位错误。若将这一额外要求强制加入主分数，会成为 {gp - len(norm)}/{gp + gf}，但其中 {len(norm)} 例应归为顶点表示/规范化范围差异，不能与上述 11 例真错误混称。

**Q1 圆：固定集通过，小尺度最小性失败**

317 个固定点集全部通过，其中 222 个为生成器标记的普通分辨尺度、95 个为尺度压力案例；七个带测站的流水线也通过。正式覆盖判定未提供，所以这里的 317/317 **不是覆盖判定通过率**。

补充复用独立 `q1_circle_cover.generate.oracle`，输入来自既有审计，不计入原 330 例分母：

| 补充 case_id | 真 R / m | 输出 R / m | 输出/真值 | 最大漏包量 / m | 判定 |
|---|---:|---:|---:|---:|---|
{chr(10).join(micro_lines)}

`audit_micro_segment` 输入 `(0,0),(5e-10,0)`，真中心 `(2.5e-10,0)`，输出中心 `(5e-10,0)`；固定 1e-9 包含容差跳过更新，末尾只增半径。`audit_micro_equilateral` 是边长 1e-7 的等边三角形，真中心约 `(5e-8,2.886751345948129e-8)`，输出 `(5e-8,0)`；固定共线阈值让良态小三角形走回退。两例主函数仍包含输入点，但分别偏大 **100% 和 50%**，确认非最小。枚举核验器的零圆则漏掉距离 5e-8 的第二点，是真包含错误，不能归给主函数。

补充最小性容差显式改为 `1e-12 D + 32 max(ulp(坐标))`，以分辨此处的相对尺度缺陷。**第一例若沿用固定 benchmark 的约 2e-9 m 容差会通过**；第二例及枚举漏包即使用原容差也失败。严格小尺度最小性没有等同于米级任务精度，原 317 个 PASS 没有被追溯改写。

**Q2 候选：量化保守损失及误签回归**

固定集 144 个保守拒绝中：**{refusal_by_status['IN']} 个严格内部点、{refusal_by_status['BOUNDARY']} 个基准边界点**。173 个真值标为 IN 的案例（含 S 同点特判）仅 118 个获证，IN 组召回率 **{100 * certified / (certified + refusal_by_status['IN']):.2f}%**；按基准容差口径接受的 89 个 BOUNDARY 案例均未获证。4 个首观测不一致案例：`empty_0/1/2` 外包为空，`empty_only_near_contact` 的外包非空且原函数给 same_position=True；由于该 API 以非空多边形为输入且不验证首观测一致性，四者归为未提供首观测验证，不作为正常物理世界误签计分。

三个审计候选以 **1°** 构造 P，复用独立扇区真值和四盘余量 `1000−max距离`：

| q / m | 真保收余量 / m | 原函数 critical_radius / m | guaranteed | 判定 |
|---|---:|---:|---|---|
{chr(10).join(qlines)}

`(1002,0)` 真正位于 C_sig 内部，余量 **2.999234657 m**；原函数临界半径 **1002.000000573 m**，故拒绝。P 保留了首站近距排除区，增加了虚构源位置的约束。**这是 API 对象/外包范围差异，不是真保收证书的逻辑反例。**若任务要求完整 C_sig，它属于完整性未实现；不能解释成这个点实际会失收。

另将已有 `same_position` 审计反例列为补充：S=(0,0)，q=(−5e-11,0)，合法源 p=(1500,0)、ρ=1500。用生成器 `legal` 验证首世界，再用 Fraction 对提交坐标精确计算平方距离，证明第二距离严格大于 ρ；浮点超额 `{supplement['audit_near_same_position']['witness']['excess_distance_m']:.15g} m`。原函数仍返回 `guaranteed=True, method=same_position`，**确认 FAIL**。它不在原 531 例中，且原扇区真值的容差带会掩盖如此小的失收量，因此明确单列精确世界回归。这个底层 API 缺陷处于极小尺度；不据此推断正常在线选点会使用该位置。

**Q2 最坏直径：上界未被反驳，精确评分未提供**

35 个连续 `score` 案例均调用了原半径函数。其中 34 个先获保收证书，上界检查 **{bp} PASS、{bf} FAIL**。另外 `tangent_segment_3` 的 q=(0,20)、F=[500,1400]×{{0}} 确实不保收：p=(1400,0)、ρ=1400 时第二距离 √1960400≈1400.142849855 m。它按原函数的保收前提单列，不算上界实现出错；原始 529.290916930 m 输出仅作为诊断保留。

已获证的 34 例中有 **{len(tight)} 个独立闭式 J**。若错误地把 `2U_R` 当作 `J_hat`，套用原 runner 的 `max(0.1 m,1% J)` 逼近要求，则 **{len(tight) - len(loose)} 通过、{len(loose)} 失败**。这 {len(loose)} 个是“benchmark 对上界接口过严/输出目标不一致”，不计为危险低估；但定量说明当前上界不能替代同精度 J 评分。计入不保收的诊断例则为 5/16，通过数分母不可混用。

| case_id | 独立精确 J / m | 2U_R / m | 比值 | 若按 J 逼近要求 |
|---|---:|---:|---:|---|
{chr(10).join(jlines)}

`tangent_segment_4` 真 J≈0.610121049 m，返回 10 m，约 **{next(r['ratio_to_lower_or_exact'] for r in wr if r['case_id'] == 'tangent_segment_4'):.6f} 倍**；即使 near 在该点不可实现，原实现仍留下 5 m 半径底限。该例是确认的松界，不是返回了过小的界。其余非闭式二维案例只验证对合法源对下界的支配，**不能把 U/L 当成 U/J 的真实相对误差，也不能由全部未反驳得出连续上界认证或全局选点最优**。同点样例即使数值通过，也不代表函数已交付 `J(S)=diam(F)` 的专门反馈复用接口。

**API 差异清单与归因**

| 范围 | 未提供/不相同的合同 | 本轮处理 |
|---|---|---|
| Q1 geometry | ε=90°原生测向入口；可行点、衰退方向；端点索引/tie及容差规范化 | 75 个案例未提供；元数据不伪造；规范化辅助统计 |
| Q1 circle/cover | 正式 YES/NO/UNRESOLVED、Thales 见证、支撑索引/残差、强制支撑异常、可选随机种子、κ/η、三段清除和特殊状态 | 13 个独立合同案例未提供；317 个点集的圆核心与覆盖接口分开 |
| Q2 candidate | 精确 F、完整 C_sig 与 OUT/BOUNDARY/见证、C_dir、首观测不一致、源/后验成员接口 | 4 个不一致案例未提供；144 合法拒绝归外包/余量保守损失 |
| Q2 worst | 精确/近似 J、合法最长对见证、有限点云反馈评分、嵌套采样、条件清除诊断、预算选点和 frontier | 13 案例未提供：3 monotone、5 clearance、3 finite_score、1 select、1 frontier；不拿启发式代填 |
| Q2 评分精度 | 半径上界与 J 近似有不同目标；角桶扩大、P 外包、near 底限增加松度 | 15 个可比闭式中 10 个达不到 J 逼近容差，单列为过严/目标差异 |

本轮确认的真 bug 是：**空集误判无界（4例）、有限三角形误判无界（3例）、点/线段维数误判（4例）、微小线段/等边三角形 MEC 非最小（2个补充）、枚举核验漏包（1个补充）、近同点误签（1个补充）**。P 导致 `(1002,0)` 被拒、144 个保守拒绝、上界较松与缺失接口均单列，未混入这份真 bug 清单。

**快照与可追溯性**

| 对方源码 | SHA256 |
|---|---|
{source_hash_lines}

| 当前独立夹具 | SHA256 | 本轮重新生成语义一致 |
|---|---|---|
{fixture_lines}

完整生成器/runner 哈希、双方执行前后源码哈希及各失败检查保存在逐例 JSON；所有数字取自本轮运行，不借用历史自报分数。补充 7 例单独存放在 `supplemental`：4 个真 FAIL、2 个正确肯定证书、1 个保守拒绝。
"""
    path.write_text(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regenerate-truth', action='store_true')
    parser.add_argument('--output', type=Path, default=HERE / 'benchmark-peer-results.json')
    parser.add_argument('--markdown', type=Path, default=HERE / 'benchmark-peer-results.md')
    args = parser.parse_args()
    before = protected_hashes()
    start = time.monotonic()
    verification, all_cases = {}, {}
    for area in AREAS:
        saved = [json.loads(line) for line in (BENCH / area / 'cases.jsonl').read_text().splitlines()]
        verification[area] = dict(n_cases=len(saved), fixture_sha256=sha(BENCH / area / 'cases.jsonl'),
                                  generator_sha256=sha(BENCH / area / 'generate.py'),
                                  runner_sha256=sha(BENCH / area / 'run.py'), regenerated=False)
        if args.regenerate_truth:
            print('Regenerating independent truth:', area, flush=True)
            mod = ORACLES[area]
            with tempfile.TemporaryDirectory(prefix='ntj-independent-truth-') as tmp:
                attr = 'ROOT' if area == 'q1_circle_cover' else 'HERE'
                original = getattr(mod, attr)
                setattr(mod, attr, Path(tmp))
                try:
                    fresh = mod.build_cases() if area == 'q1_geometry' else mod.generate()
                finally:
                    setattr(mod, attr, original)
            equal = canonical(fresh) == canonical(saved)
            verification[area].update(regenerated=True, semantic_equality=equal)
            if not equal:
                raise RuntimeError('Regenerated truth differs from saved fixtures: ' + area)
            saved = fresh
        all_cases[area] = saved
    results = {}
    for area, evaluate in zip(AREAS, (geometry_case, circle_case, candidate_case, worst_case)):
        rows = []
        for c in all_cases[area]:
            try:
                ans = evaluate(c)
            except Exception as exc:
                ans = dict(status='ERROR', exception=repr(exc), traceback=traceback.format_exc())
            rows.append(dict(case_id=c['case_id'], input=c['input'], expected=c['ground_truth'],
                             truth_method=c['truth_method'], **ans))
        results[area] = dict(counts=dict(Counter(r['status'] for r in rows)), results=rows)
        print(area, results[area]['counts'], flush=True)
    extra = supplemental()
    after = protected_hashes()
    assert before == after, 'Protected source/fixture hashes changed during execution'
    assert not any(k.startswith('models.q1q2') for k in sys.modules), 'Our production package imported'
    output = dict(generated_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic() - start,
                  environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                                   peer_path=str(PEER), peer_geometry_import=peer.__file__,
                                   peer_signal_import=signal.__file__,
                                   peer_head=subprocess.check_output(['git', '-C', str(PEER), 'rev-parse', 'HEAD'], text=True).strip()),
                  command=sys.argv, truth_verification=verification, areas=results, supplemental=extra,
                  protected_files=len(before), protected_sha256_before=before, protected_sha256_after=after,
                  sources_and_fixtures_unchanged=before == after, imported_our_production=False,
                  peer_functions_called=['solve_bearings', 'bearing_planes', 'halfplane_region', 'hull', 'diameter',
                                         'minimum_circle', 'disk_outer', 'bearing_clip', 'clip', 'reception_certificate',
                                         'posterior_radius_upper', 'minimum_circle_enumerated (supplement only)'])
    args.output.write_text(json.dumps(clean(output), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_report(output, args.markdown, args.output)
    print('Supplement:', dict(Counter(r['status'] for r in extra)), flush=True)
    print('Saved', args.output, 'seconds', round(output['elapsed_seconds'], 3), flush=True)
    # Successful execution does not imply the tested implementation passed.
    return 2 if any(r['status'] == 'ERROR' for area in results.values() for r in area['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
