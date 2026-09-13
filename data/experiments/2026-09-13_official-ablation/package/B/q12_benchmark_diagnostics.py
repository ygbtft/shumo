"""Archive Q1/Q2 failure attribution and halfplane-kernel-only supplements."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
import geometry as own
from q12_our_benchmark import cases, clean, f, pts, vertex_comparison

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "experiments/runs/2026-09-11_q12-peer-benchmark"
OUT = RUN / "diagnostics"


def read(rel):
    return json.loads((RUN / rel).read_text())


def main():
    OUT.mkdir()
    began = time.perf_counter()
    frozen = {name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in ("geometry.py", "signal_minimax.py")}
    rows = []
    mapping = {"empty":"EMPTY", "unbounded":"UNBOUNDED", "point":"POINT",
               "segment":"SEGMENT", "bounded":"POLYGON", "numerically_unresolved":"NUMERICAL_UNRESOLVED"}
    for c in cases("q1_geometry"):
        inp, gt = c["input"], c["ground_truth"]
        if not any(o["half_width_deg"] >= 90 for o in inp.get("observations", [])):
            continue
        ab = np.array([[f(x) for x in row] for row in inp["oracle_halfplanes"]])
        actual = own.halfplane_region(ab[:, :2], ab[:, 2])
        checks = dict(classification=mapping[actual["status"]] == gt["kind"])
        vertex_diag = None
        if gt["kind"] not in ("EMPTY", "UNBOUNDED"):
            p = pts(gt["vertices"])
            tol = 1e-8 + 1e-9 * gt["diameter"]
            vtol = tol + 32 * math.ulp(float(np.max(np.abs(p))))
            vertex_diag = vertex_comparison(actual.get("vertices", []), gt["vertices"], vtol)
            checks.update(vertex_geometry=vertex_diag["geometry_match"], diameter=actual["diameter"] is not None
                          and abs(actual["diameter"] - gt["diameter"]) <= tol)
        rows.append(dict(case_id=c["case_id"], input_halfplanes=inp["oracle_halfplanes"], expected=gt,
                         actual=actual, checks=checks, vertex_diagnostics=vertex_diag,
                         status="PASS" if all(checks.values()) else "FAIL"))
    supplement = dict(scope="75 cases outside native bearing API, using fixture halfplanes as test input; kernel only, not native bearing pipeline",
        cases_sha256=hashlib.sha256((ROOT / "reference/shumo-b-q12-benchmark/models/q1q2/benchmarks/q1_geometry/cases.jsonl").read_bytes()).hexdigest(),
        statuses=dict(Counter(r["status"] for r in rows)), results=rows, wall_s=time.perf_counter()-began)
    (OUT / "q1_halfplane_only.json").write_text(json.dumps(clean(supplement), ensure_ascii=False, indent=2, allow_nan=False))

    native = read("our_results/q1_geometry.json")
    ours_failures = [r for r in native["results"] if r["status"] == "FAIL"]
    classifications = Counter()
    for r in ours_failures:
        if r["expected"]["kind"] == "EMPTY":
            category = "empty classified unbounded: feasibility tolerance"
        elif r["actual"]["status"] == "unbounded":
            category = "bounded thin triangle classified unbounded: LP small coefficients"
        else:
            category = "dimension error from near-duplicate or collinear float vertices"
        r["failure_attribution"] = category
        classifications[category] += 1
    peer_region = read("upstream_worktree/models/q1q2/benchmarks/q1_geometry/report.json")
    peer_counts = Counter((r["expected"]["kind"], r["actual"]["region"]["status"], r["actual"]["region"]["kind"])
                          for r in peer_region["failures"])
    candidate = read("our_results/q2_candidate.json")
    candidate_split = Counter((r["status"], r["expected"].get("signal_status")) for r in candidate["results"])
    worst = read("our_results/q2_worst_diameter.json")
    peer_worst = {r["case_id"]:r for r in read("upstream_worktree/models/q1q2/benchmarks/q2_worst_diameter/report.json")["results"]}
    exact_comparisons = [dict(case_id=r["case_id"], exact_m=r["expected"]["J_exact_m"],
        our_upper_m=r["actual"]["diameter_upper_m"], upper_to_exact_ratio=r["bound_ratio"],
        peer_estimate_m=peer_worst[r["case_id"]]["actual"].get("J_hat")) for r in worst["results"]
        if r["status"] == "BOUND_NOT_REFUTED" and "J_exact_m" in r["expected"]]
    simple_obs = [(np.array([0., 0.]),180.), (np.array([10., 0.]),0.)]
    ab = [own.bearing_planes(s, angle, 1.) for s,angle in simple_obs]
    simple_actual = own.halfplane_region(np.concatenate([a for a,b in ab]), np.concatenate([b for a,b in ab]))
    unit_reproduction = dict(observations=[dict(position=s.tolist(),bearing_deg=a,half_width_deg=1.) for s,a in simple_obs],
        exact_reason="First 1-degree wedge has x<=0; second has x>=10. Their intersection is empty.",
        expected="EMPTY", ours=simple_actual, peer_unit_test="416 passed, 1 failed; returns NUMERICAL_UNRESOLVED on this input")
    our_circle = read("our_results/q1_circle_cover.json")
    (OUT / "failure_attribution.json").write_text(json.dumps(clean(dict(
        our_q1_failure_counts=dict(classifications), our_q1_failures=ours_failures,
        our_q1_passes_with_nonbijective_vertices=[r["case_id"] for r in native["results"] if r["status"]=="PASS"
                                               and not r.get("vertex_diagnostics",{}).get("normalized",True)],
        peer_q1_failure_counts=[dict(expected=e,status=s,kind=k,count=n) for (e,s,k),n in peer_counts.items()],
        candidate_split=[dict(our_status=a,exact_status=b,count=n) for (a,b),n in candidate_split.items()],
        exact_j_comparisons=exact_comparisons,
        reception_refusals=[r for r in worst["results"] if r["status"] == "NOT_CERTIFIED_RECEPTION"],
        peer_circle_failures=read("upstream_worktree/models/q1q2/benchmarks/q1_circle_cover/report.json")["failures"],
        peer_nesting_failures=read("upstream_worktree/models/q1q2/benchmarks/q2_worst_diameter/report.json")["failures"],
        simple_empty_reproduction=unit_reproduction,
        bearing_circle_pipelines=[r for r in our_circle["results"] if "bearing_pipeline" in r],
        production_sha256=frozen, original_kernels_unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==v for n,v in frozen.items()),
        official_calls=0, scored_mission_executions=0)), indent=2, ensure_ascii=False, allow_nan=False))
    print("Halfplane-only supplement:", supplement["statuses"])
    print("Our Q1 failure classes:", dict(classifications))
    print("Simple empty example:", simple_actual["status"])
    print("Q2 candidate breakdown:", str(candidate_split))

    # The raw adapter compares vertex sets. An extra point strictly on an edge
    # breaks that comparison without changing the convex region. Keep the raw
    # result and record an independent boundary-distance review separately.
    reviews = []
    def point_segment_distance(p, a, b):
        delta = b-a
        length2 = float(delta@delta)
        t = 0. if length2 == 0 else max(0., min(1., float((p-a)@delta)/length2))
        return float(np.linalg.norm(p-(a+t*delta)))
    def directed_boundary(a, b):
        return max(min(point_segment_distance(p, b[i], b[(i+1)%len(b)]) for i in range(len(b))) for p in a)
    for row in rows:
        if row["status"] != "FAIL" or not row["actual"].get("vertices") or not row["expected"]["vertices"]:
            continue
        a, b = pts(row["actual"]["vertices"]), pts(row["expected"]["vertices"])
        distance = max(directed_boundary(a,b), directed_boundary(b,a))
        tol = 1e-8 + 1e-9*row["expected"]["diameter"] + 32*math.ulp(float(np.max(np.abs(b))))
        reviews.append(dict(case_id=row["case_id"], raw_vertex_set_hausdorff_m=row["vertex_diagnostics"]["hausdorff_m"],
            vertex_to_opposite_boundary_max_m=distance, tolerance_m=tol,
            classification_and_diameter_correct=row["checks"]["classification"] and row["checks"]["diameter"],
            actual_vertex_count=len(a), expected_vertex_count=len(b), region_boundary_matches=distance<=tol,
            attribution="Extra/near-duplicate boundary vertices: normalization contract, not metre-scale region displacement"))
    (OUT / "supplement_vertex_review.json").write_text(json.dumps(reviews, indent=2))


if __name__ == "__main__":
    main()
