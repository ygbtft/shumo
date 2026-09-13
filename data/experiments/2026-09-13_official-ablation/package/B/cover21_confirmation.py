"""Frozen confirmation of integer 21-station layouts and cheaper scan decisions."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import numpy as np
from peer_benchmark import ScenarioConfig,ErrorConfig,mandatory_conditions,generate
from mock.scenario_gen import Scenario,Source
from metaheuristic_experiments import write_json
import cover21_experiments as training
import lean_scan_experiments as lean
import public_count_experiments as count
import deferred_confirmation as prior
import cheap_prediction_experiments as cheap
import replacement_experiments as original_certificates
import icra_confirmation as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_cover21-confirmation"
SPECS={3:{
 "peer_layout9_proxy":dict(kind="base",layout="ring9"),
 **{name:prior.SPECS[3][name].copy() for name in ("area_return1_7","range_area7","deferred_area7")},
 "lean_deferred_area7":lean.SPECS[3]["lean_deferred_area7"].copy(),
},4:{
 **{name:training.SPECS[4][name].copy() for name in ("width_convex22","range_convex22","predict_convex22","locked_full_convex22","count_locked_convex22")},
 "original_predict_convex22":cheap.SPECS[4]["cheap_predict8_width015"].copy(),
 "lean_locked_convex22":lean.SPECS[4]["lean_cheap_predict8_locked_width015"].copy(),
 **{name:training.SPECS[4][name].copy() for name in ("width_grid21_29","range_grid21_29","predict_grid21_29","locked_full_grid21_29","count_locked_grid21_29")},
 "lean_locked_grid21_29":dict(lean.SPECS[4]["lean_cheap_predict8_locked_width015"],layout="grid21_29"),
 **{name:training.SPECS[4][name].copy() for name in ("range_grid21_7","range_closed21_3")},
}}
assert sum(map(len,SPECS.values()))==20
EXPECTED=3900
build=training.build
all_paths=training.paths
COMPARISONS=[(3,c,b) for c in ("range_area7","deferred_area7","lean_deferred_area7") for b in ("peer_layout9_proxy","area_return1_7")]
COMPARISONS += [(3,"lean_deferred_area7","deferred_area7"),(3,"lean_deferred_area7","range_area7")]
COMPARISONS += [(4,c,"range_convex22") for c in SPECS[4] if c!="range_convex22"]
COMPARISONS += [(4,"predict_convex22","original_predict_convex22"),(4,"count_locked_convex22","lean_locked_convex22"),
 (4,"count_locked_grid21_29","lean_locked_grid21_29"),(4,"predict_grid21_29","predict_convex22"),
 (4,"count_locked_grid21_29","count_locked_convex22"),(4,"predict_convex22","width_convex22"),
 (4,"count_locked_convex22","locked_full_convex22"),(4,"predict_grid21_29","width_grid21_29"),
 (4,"count_locked_grid21_29","locked_full_grid21_29"),(4,"predict_grid21_29","range_grid21_29"),
 (4,"count_locked_grid21_29","range_grid21_29")]
_prior_freeze,_prior_summary=engine.freeze,engine.summarize


def cases(problem):
    cfg = ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(147, 157):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    index = 0
    for li, layout in enumerate(("boundary_outward", "boundary_tangent", "near_collinear", "cluster_far20", "range_transition")):
        for count in (10, 13, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42, 120, problem, li, count]))
            channels = list(rng.choice(np.arange(1, 20), count - 1, replace=False)) + [20]
            phase = rng.uniform(0, 2 * math.pi)
            angles = np.arange(count) * 2 * math.pi / count + phase
            if layout.startswith("boundary"):
                points = 1800 * np.column_stack([np.cos(angles), np.sin(angles)])
            elif layout == "near_collinear":
                angle = rng.uniform(0, math.pi)
                u = np.array([math.cos(angle), math.sin(angle)])
                v = np.array([-u[1], u[0]])
                points = np.linspace(-1790, 1790, count)[:, None] * u + rng.uniform(-.001, .001, count)[:, None] * v
            elif layout == "cluster_far20":
                points = rng.normal(0, 120, (count, 2))
                points[-1] = 1800 * np.array([math.cos(phase), math.sin(phase)])
            else:
                points = np.linspace(850, 1500, count)[:, None] * np.column_stack([np.cos(angles), np.sin(angles)])
            sources = []
            for i, (ch, g) in enumerate(zip(channels, points)):
                direction = None
                if problem == 4 and i > 0:
                    direction = math.degrees(math.atan2(g[1], g[0]))
                    if layout == "boundary_tangent":
                        direction += 90. if i % 2 else -90.
                    elif layout == "range_transition":
                        direction += 89.999 if i % 2 else -89.999
                    direction %= 360
                radius = 1500. if layout == "range_transition" and i % 3 == 0 else 1000.
                sources.append(Source(int(ch), float(g[0]), float(g[1]), radius, direction))
            for sign in ("positive", "negative", "spatial"):
                seed = 42 + 3200 + 100 * problem + index
                index += 1
                scenario = Scenario(seed, tuple(sources), dict(stress_layout=layout, source_rng=[42, 120, problem, li, count]))
                yield f"{layout}__n{count}__{sign}", layout, "stress", scenario, ErrorConfig(model="adversarial", adversarial_sign=sign)


def freeze(paths):
    for name,expected,checks in (("lean-scan",1116,570),("public-count-scan",744,780),("cover21-training",1860,560)):
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        done=json.loads((folder/"completion.json").read_text());passed=json.loads((folder/"checks.json").read_text())
        assert done["executions"]==done["all_cleared"]==expected and done["errors"]==0
        assert passed["passed"]==checks and passed["failed"]==0
        frozen=json.loads((folder/"run_config.json").read_text())["code_sha256"]
        for filename in frozen:
            if filename.endswith("_policy.py") or filename in ("policies.py","geometry.py","client.py"):
                assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==frozen[filename],filename
    audit=json.loads((ROOT/"experiments/runs/2026-09-11_odd-ring-cover/geometry_audit.json").read_text())
    assert audit["failed"]==0 and audit["certificate_counts"]=={"odd-ring-cover":36,"rounded-cover21":68,"closed-cover21":4}
    _prior_freeze(paths)
    config=json.loads((OUT/"run_config.json").read_text())
    config.update(confirmation_seeds=list(range(147,157)),expected_executions=3900,
        derivation="42+105+repeat,0..9; not generated in prior runs",
        stress_derivation="SeedSequence([42,120,problem,layout_index,count]); errors42+3200+100*problem+index",
        untouched_future_seeds=list(range(157,167)),freeze_before_truth_generation=True,
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="After 3720 scored old-training executions: grid21_29 offers balanced mean/tail/CPU improvements in training; advance its simple range, prediction, locked and count variants with matched no-skip references. Retain grid21_7 for ordinary mean alternative and closed21_3 for tangent-boundary sensitivity, despite their worse training stress tails. Lean old-decision CPU controls and public-count disabled controls retained. No Q3 count variant advanced: no training deletions. No tuning on fresh confirmation.",
        virtual_upper_bound_s=335136,instruction_upper_bound=9766,
        proof_files=["REGULAR_RING_OBSTRUCTION.md","PUBLIC_COUNT_SCAN_GUARANTEE.md","DEFERRED_SCAN_GUARANTEE.md","WIDE_PROBE_GUARANTEE.md"],
        layout_files_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ("experiments/runs/2026-09-11_rounded-cover21/certified_layouts.json","experiments/runs/2026-09-11_closed-cover21/certified_layouts.json")})
    write_json(OUT/"run_config.json",config)
    write_json(OUT/"selected_layouts.json",training.certificates())
    (OUT/"precheck.md").write_text("# 21站与计算优化的新确认冻结\n\n3720计分训练全清，570/780/560项前置检查及独立连续几何审计通过。20候选先冻结，再生成147—156与新压力流，共3900次。对全部指标与逐例回退作比较；固定240/460算术每源目标不改。未来157—166不生成。正式请求0。\n")


def summarize(rows):
    _prior_summary(rows)
    path=OUT/"summary.md"
    text=path.read_text().replace("seed42派生77—86","seed42派生147—156").replace("Q4旧方格保守","Q4已有22站基础限幅")
    path.write_text(text.replace("# 冻结后确认：未用于调参的场景","# 21站整数布局与计算优化：冻结后确认"))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--launch",action="store_true");args=parser.parse_args()
    engine.OUT,engine.SPECS,engine.all_paths,engine.cases=OUT,SPECS,all_paths,cases
    engine.freeze,engine.summarize=freeze,summarize
    engine.builders=SimpleNamespace(build=build,CERTIFICATES=original_certificates.CERTIFICATES)
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving frozen confirmation")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:engine.run()


if __name__=="__main__":main()
