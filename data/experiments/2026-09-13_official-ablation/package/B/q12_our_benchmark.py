"""Test existing B kernels with independent, pinned peer benchmark fixtures.

This runner adapts input/output representations only. It never imports peer
production solvers. Unsupported APIs and conservative refusals stay explicit.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time
import traceback
import numpy as np
import geometry as own
from signal_minimax import reception_certificate, posterior_radius_upper

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"experiments/runs/2026-09-11_q12-peer-benchmark"
FIXTURES = ROOT/"reference/shumo-b-q12-benchmark/models/q1q2/benchmarks"
DEST = OUT/"our_results"


def f(x):
    return float(Fraction(x)) if isinstance(x, str) else float(x)


def pts(values):
    return np.asarray([[f(x) for x in p] for p in values], dtype=float).reshape(-1, 2)


def clean(x):
    if isinstance(x, np.ndarray):
        return clean(x.tolist())
    if isinstance(x, (np.bool_, np.integer, np.floating)):
        return clean(x.item())
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x, (tuple, list)):
        return [clean(v) for v in x]
    return x


def cases(area):
    return [json.loads(line) for line in (FIXTURES/area/"cases.jsonl").read_text().splitlines()]


def save(area, rows, contract, wall_s):
    result = dict(area=area, case_count=len(rows), statuses=dict(Counter(r["status"] for r in rows)),
                  contract=contract, results=rows, wall_s=wall_s, base_seed=42, official_calls=0,
                  scored_mission_executions=0, peer_commit="253bf943a58d6f21de88f14fdc940da66b87ab96",
                  cases_sha256=hashlib.sha256((FIXTURES/area/"cases.jsonl").read_bytes()).hexdigest(),
                  production_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("geometry.py", "signal_minimax.py")})
    (DEST/f"{area}.json").write_text(json.dumps(clean(result), indent=2, ensure_ascii=False, allow_nan=False))
    print(area, result["statuses"], round(wall_s, 3), flush=True)
    return result


def vertex_comparison(actual, expected, tolerance):
    a, b = pts(actual), pts(expected)
    if not len(a) or not len(b):
        return dict(geometry_match=len(a)==len(b), normalized=len(a)==len(b), hausdorff_m=None)
    distances = np.linalg.norm(a[:, None]-b[None, :], axis=2)
    hd = float(max(distances.min(axis=0).max(), distances.min(axis=1).max()))
    owner = {}
    def match(i, seen):
        for j in np.flatnonzero(distances[i] <= tolerance):
            j = int(j)
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or match(owner[j], seen):
                owner[j] = i
                return True
        return False
    bijective = len(a)==len(b) and all(match(i, set()) for i in range(len(a)))
    return dict(geometry_match=hd<=tolerance, normalized=bijective, hausdorff_m=hd)


def geometry_suite():
    began = time.perf_counter(); rows = []
    mapping = {"empty":"EMPTY", "unbounded":"UNBOUNDED", "point":"POINT", "segment":"SEGMENT", "bounded":"POLYGON", "numerically_unresolved":"NUMERICAL_UNRESOLVED"}
    for case in cases("q1_geometry"):
        inp, gt = case["input"], case["ground_truth"]
        item = dict(case_id=case["case_id"], category=case["category"], input=inp, expected=gt, truth_method=case["truth_method"])
        try:
            if any(o["half_width_deg"] >= 90. for o in inp.get("observations", [])):
                item.update(status="UNSUPPORTED", reason="Existing bearing_planes explicitly supports half-width <90 degrees; the benchmark also exercises 90-degree supporting halfplanes.")
                rows.append(item); continue
            if "points" in inp:
                v = own.hull(pts(inp["points"]))
                kind = "POINT" if len(v)==1 else "SEGMENT" if len(v)==2 else "POLYGON"
                d, pair = own.diameter(v)
                result = dict(status=kind, vertices=v.tolist(), diameter=d, diameter_endpoints=pair)
            else:
                if "halfplanes" in inp:
                    ab = np.asarray([[f(x) for x in row] for row in inp["halfplanes"]])
                    result = own.halfplane_region(ab[:, :2], ab[:, 2])
                else:
                    ab = [own.bearing_planes(o["position"], o["bearing_deg"], o["half_width_deg"]) for o in inp["observations"]]
                    result = own.halfplane_region(np.concatenate([a for a,b in ab]) if ab else [], np.concatenate([b for a,b in ab]) if ab else [])
                kind = mapping[result["status"]]
            tol = 1e-8+1e-9*(gt.get("diameter") or 0.)
            checks = dict(classification=kind==gt["kind"])
            if gt["kind"] not in ("EMPTY", "UNBOUNDED"):
                expected = pts(gt["vertices"])
                vtol = tol+32*math.ulp(float(np.max(np.abs(expected))) if len(expected) else 1.)
                vd = vertex_comparison(result.get("vertices", []), gt["vertices"], vtol)
                checks["vertex_geometry"] = vd["geometry_match"]
                checks["diameter"] = result.get("diameter") is not None and abs(result["diameter"]-gt["diameter"]) <= tol
                item["vertex_diagnostics"] = vd
            # Isolated diameter checks use oracle vertices as TEST INPUT, never
            # as a substitute for the pipeline's own returned vertices.
            if gt["vertices"]:
                isolated, _ = own.diameter(pts(gt["vertices"]))
                item["isolated_diameter"] = dict(actual=isolated, passed=abs(isolated-gt["diameter"]) <= tol)
            item.update(actual=result, checks=checks, status="PASS" if all(checks.values()) else "FAIL",
                        unsupported_metadata=["feasible_point", "recession_direction", "diameter indices/tie API"])
        except Exception as exc:
            item.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        rows.append(item)
    return save("q1_geometry", rows, "Native region classification, vertex geometry and diameter. Vertex normalization is separate. Same independent fixtures/tolerances; not the peer's larger metadata API pass count.", time.perf_counter()-began)


def circle_suite():
    began = time.perf_counter(); rows = []
    for case in cases("q1_circle_cover"):
        inp, gt = case["input"], case["ground_truth"]
        item = dict(case_id=case["case_id"], categories=case["categories"], input=inp, expected=gt, truth_method=case["truth_method"])
        if "points" not in inp:
            item.update(status="UNSUPPORTED", reason="No existing standalone clearance-regime or structured special-status API; no peer implementation borrowed.")
            rows.append(item); continue
        try:
            p = pts(inp["points"]); center, radius = own.minimum_circle(p); d, pair = own.diameter(p)
            tol = 2e-9+2e-10*gt["diameter"]+8*max(math.ulp(float(x)) for point in p for x in point)
            checks = dict(radius=abs(radius-gt["radius"])<=tol,
                          center=max(abs(center-np.asarray(gt["center"])))<=tol,
                          containment=max(math.dist(v, center)-radius for v in p)<=tol,
                          diameter=abs(d-gt["diameter"])<=tol)
            midpoint = (pair[0]+pair[1])/2
            midpoint_radius = max(math.dist(v, midpoint) for v in p)
            item.update(actual=dict(center=center, radius=radius, diameter=d, diameter_endpoints=pair,
                                    midpoint=midpoint, midpoint_covering_radius=midpoint_radius,
                                    diameter_circle_contains_by_existing_analysis_tolerance=midpoint_radius<=d/2+1e-7),
                        checks=checks, status="PASS" if all(checks.values()) else "FAIL",
                        unsupported_metadata=["support indices", "forced-support exception API", "caller-selected random seeds"], native_seed=42)
            if "stations" in inp:
                ab = [own.bearing_planes(o["position"], o["bearing_deg"], o["half_width_deg"]) for o in inp["stations"]]
                result = own.halfplane_region(np.concatenate([a for a,b in ab]), np.concatenate([b for a,b in ab]))
                item["bearing_pipeline"] = result
                item["bearing_pipeline_checks"] = dict(diameter=abs(result["diameter"]-gt["diameter"])<=tol,
                                                       radius=abs(result["radius"]-gt["radius"])<=tol)
                if not all(item["bearing_pipeline_checks"].values()):
                    item["status"] = "FAIL"
        except Exception as exc:
            item.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        rows.append(item)
    return save("q1_circle_cover", rows, "Native fixed-seed MEC/diameter, containment and seven bearing pipelines; original point-cloud oracle and tolerances. Peer-only support/status/seed-selection contracts remain unsupported.", time.perf_counter()-began)


def outer_source(inp):
    s = np.asarray(inp.get("S", [0., 0.]), float)
    center = inp.get("center", [0., 0.]); radius = inp.get("arena_radius", inp.get("radius", 1800.))
    p = own.disk_outer(center, radius)
    p = own.bearing_clip(p, s, inp.get("theta", 0.), inp.get("eps", inp.get("eps1", 1.)))
    for normal in own.NORMALS:
        p = own.clip(p, normal, float(normal@s)+inp.get("rho_hi", 1500.))
        if not len(p):
            break
    return s, p


def candidate_suite():
    began = time.perf_counter(); rows = []
    for case in cases("q2_candidate"):
        inp, gt = case["input"], case["ground_truth"]
        item = dict(case_id=case["case_id"], input=inp, expected=gt, truth_method=case["truth_method"], categories=case["categories"])
        try:
            s, p = outer_source(inp)
            if not len(p):
                item.update(status="EMPTY_OUTER", reason="Empty constructed outer region; native reception API requires a nonempty polygon.")
            else:
                answer = reception_certificate(np.asarray(inp["q"], float), p, s)
                item.update(actual=answer, outer_vertices=len(p))
                truth = gt.get("signal_member")
                if truth is None:
                    item.update(status="UNSUPPORTED", reason="Inconsistent-first-observation validation is not part of the native polygon certificate API.")
                elif answer["guaranteed"]:
                    item["status"] = "CERTIFIED_CORRECT" if truth else "UNSAFE_CERTIFICATE"
                elif truth:
                    item["status"] = "CONSERVATIVE_REFUSAL"
                else:
                    item["status"] = "NOT_CERTIFIED_OUTSIDE"
            item["unsupported_contracts"] = ["Exact C_sig OUT/BOUNDARY classification", "C_dir", "source/posterior boolean and witness metadata"]
        except Exception as exc:
            item.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        rows.append(item)
    return save("q2_candidate", rows, "One-sided C_sig certificate on an outer polygon. A false result means unproved, not OUT. Any true result against independently infeasible membership is unsafe. C_dir and exact curved-source-set APIs are not implemented here.", time.perf_counter()-began)


def worst_suite():
    began = time.perf_counter(); rows = []
    for case in cases("q2_worst_diameter"):
        inp, gt = case["input"], case["ground_truth"]
        item = dict(case_id=case["case_id"], kind=case["kind"], input=inp, expected=gt, truth_method=case["truth_method"])
        if case["kind"] != "score":
            item.update(status="UNSUPPORTED", reason="Native API returns a continuous radius upper bound, not finite-point scores, a budget optimizer/frontier, nested source samples or clearance diagnostics.")
            rows.append(item); continue
        try:
            s, p = outer_source(inp); q = np.asarray(inp["q"], float)
            cert = reception_certificate(q, p, s)
            if not cert["guaranteed"]:
                item.update(status="NOT_CERTIFIED_RECEPTION", reception=cert)
            else:
                answer = posterior_radius_upper(p, q, bin_deg=.5, error_deg=inp.get("eps2", 1.))
                upper = 2*answer["radius_upper_m"]
                lower = gt.get("J_exact_m", gt["lower_bound_m"])
                item.update(actual=dict(radius_bound=answer, diameter_upper_m=upper), lower_or_exact_m=lower,
                            bound_ratio=upper/lower if lower else None,
                            status="BOUND_NOT_REFUTED" if upper+1e-7 >= lower else "BOUND_REFUTED")
        except Exception as exc:
            item.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        rows.append(item)
    return save("q2_worst_diameter", rows, "Check native continuous MEC radius bound converted to diameter upper bound 2R against the independent J lower bound or exact formula. Passing is not an exact J estimate or an outer position optimum. No peer score function is called.", time.perf_counter()-began)


def main():
    DEST.mkdir()
    before = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("geometry.py", "signal_minimax.py")}
    results = [geometry_suite(), circle_suite(), candidate_suite(), worst_suite()]
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in before.items())
    (DEST/"completion.json").write_text(json.dumps(dict(areas={r["area"]:r["statuses"] for r in results},
         original_kernels_unchanged=True, official_calls=0, scored_mission_executions=0), indent=2))


if __name__ == "__main__":
    main()
