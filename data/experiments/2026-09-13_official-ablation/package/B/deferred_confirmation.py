"""Freeze deferred scans, certified negative prediction and equivalent computation before new scenes."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import numpy as np

from peer_benchmark import ScenarioConfig, ErrorConfig, mandatory_conditions, generate
from mock.scenario_gen import Scenario, Source
from metaheuristic_experiments import write_json
import cheap_prediction_experiments as builders
import deferred_skip_experiments as deferred
import batched_history_experiments as batched
import historical_pair_experiments as historical
import coupled_dispatch_experiments as coupled
import replacement_experiments as certificates
import icra_confirmation as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_deferred-confirmation"
SPECS = {3: {
    "peer_layout9_proxy": dict(kind="base", layout="ring9"),
    **{k: deferred.SPECS[3][k].copy() for k in ("area_return1_7", "range_area7", "faithful_area7", "deferred_area7")},
}, 4: {
    **{k: deferred.SPECS[4][k].copy() for k in ("width40_f015_22", "range_width015", "faithful_width015", "deferred_width015", "predict8_width015",
        "arc05_noskip_width015", "deferred_arc05_width015", "locked_noskip_width015", "deferred_locked_width015")},
    **{k: builders.SPECS[4][k].copy() for k in ("cheap_predict4_width015", "cheap_predict8_width015", "cheap_predict8_arc05_width015", "cheap_predict8_locked_width015")},
    **{k: batched.SPECS[4][k].copy() for k in ("history_first8_width015", "batch_history_first8_width015")},
}}
assert sum(map(len,SPECS.values())) == 20

build = builders.build
_prior_freeze, _prior_summary = engine.freeze, engine.summarize


def all_paths():
    return builders.paths()


def cases(problem):
    cfg = ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(137, 147):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    index = 0
    for li, layout in enumerate(("boundary_outward", "boundary_tangent", "near_collinear", "cluster_far20", "range_transition")):
        for count in (10, 13, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42, 119, problem, li, count]))
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
                seed = 42 + 2900 + 100 * problem + index
                index += 1
                scenario = Scenario(seed, tuple(sources), dict(stress_layout=layout, source_rng=[42, 119, problem, li, count]))
                yield f"{layout}__n{count}__{sign}", layout, "stress", scenario, ErrorConfig(model="adversarial", adversarial_sign=sign)


def freeze(paths):
    import hashlib
    checked_runs=(("deferred-scans",2232,2016),("batched-history",930,1091),("cheap-prediction",1116,1038))
    for name,count,expected_checks in checked_runs:
        folder=ROOT / "experiments/runs" / f"2026-09-11_{name}"
        result=json.loads((folder / "completion.json").read_text())
        tests=json.loads((folder / "checks.json").read_text())
        config=json.loads((folder / "run_config.json").read_text())
        assert result["executions"]==result["all_cleared"]==count and result["errors"]==0
        assert tests["passed"]==expected_checks and tests["failed"]==0
        names=["coupled_dispatch_policy.py","fast_dispatch_policy.py","geometry.py","policies.py","client.py","historical_pair_policy.py","faithful_skip_policy.py","deferred_skip_policy.py"]
        if name=="batched-history": names.append("batched_history_policy.py")
        if name=="cheap-prediction": names.append("cheap_prediction_policy.py")
        for filename in names:
            assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()==config["code_sha256"][filename]
    _prior_freeze(paths)
    config=json.loads((OUT / "run_config.json").read_text())
    config.update(confirmation_seeds=list(range(137,147)),expected_executions=3900,
        derivation="42+95+repeat,0..9; not generated in prior runs",
        stress_derivation="SeedSequence([42,119,problem,layout_index,count]); errors42+2900+100*problem+index",
        untouched_future_seeds=list(range(147,157)),freeze_before_truth_generation=True,
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="After 4278 scored training runs; Q3 negative prediction had zero extra skips and higher CPU, so advance range-only deferred Q3. Keep four no-skip plan references, current simple range/stationary variants, deferred Q4 and cheap 4/8 histories; 8 keeps slightly more certificates with measured CPU cost. Include unfiltered predict8 width and historical first8 as exact-decision CPU comparators. No tuning on confirmation",
        virtual_upper_bound_s=335136,instruction_upper_bound=9766,
        proof_files=["DEFERRED_SCAN_GUARANTEE.md","BATCHED_HISTORY_EQUIVALENCE.md","CHEAP_PREDICTION_GUARD.md","WIDE_PROBE_GUARANTEE.md"])
    write_json(OUT / "run_config.json",config)
    (OUT / "precheck.md").write_text("# 延后扫描/负点预测与加速确认前冻结\n\n4278训练计分全清；2016/1091/1038项前置检查通过。20候选先冻结，再生成137—146和新压力流，3900次；未来147—156未生成。Q3负点预测训练无额外收益，不晋级；Q4保留4/8记忆的CPU权衡。原几何/反馈接纳不改，正式请求0。\n")


def summarize(rows):
    _prior_summary(rows)
    path = OUT / "summary.md"
    text = path.read_text().replace("seed42派生77—86", "seed42派生137—146").replace("Q4旧方格保守", "Q4已有基础限幅")
    text = text.replace("# 冻结后确认：未用于调参的场景", "# 延后扫描、负点预测及等价加速：冻结后确认")
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    engine.OUT, engine.SPECS, engine.all_paths, engine.cases = OUT, SPECS, all_paths, cases
    engine.freeze, engine.summarize = freeze, summarize
    engine.builders = SimpleNamespace(build=builders.build, CERTIFICATES=certificates.CERTIFICATES)
    if args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving frozen confirmation")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())], cwd=ROOT.parent,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid) + "\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
