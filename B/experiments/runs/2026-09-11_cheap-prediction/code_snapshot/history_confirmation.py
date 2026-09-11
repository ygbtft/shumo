"""Freeze historical exclusion and plan-preserving skips before new scenes."""
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
import faithful_skip_experiments as builders
import historical_pair_experiments as historical
import coupled_dispatch_experiments as coupled
import replacement_experiments as certificates
import icra_confirmation as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_history-confirmation"
SPECS = {3: {
    "peer_layout9_proxy": dict(kind="base", layout="ring9"),
    "area_return1_7": builders.SPECS[3]["area_return1_7"].copy(),
    "range_area7": builders.SPECS[3]["range_area7"].copy(),
    "faithful_area7": builders.SPECS[3]["faithful_area7"].copy(),
}, 4: {
    "packet_center22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150.),
    **{k: builders.SPECS[4][k].copy() for k in ("width40_f015_22", "range_width015", "faithful_width015",
        "arc05_noskip_width015", "fast_arc05_width015", "faithful_arc05_width015",
        "locked_noskip_width015", "faithful_locked_width015")},
    **{k: historical.SPECS[4][k].copy() for k in ("history_first8_width015", "history_recent8_width015")},
}}
build = builders.build
_prior_freeze, _prior_summary = engine.freeze, engine.summarize


def all_paths():
    return builders.paths()


def cases(problem):
    cfg = ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(127, 137):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    index = 0
    for li, layout in enumerate(("boundary_outward", "boundary_tangent", "near_collinear", "cluster_far20", "range_transition")):
        for count in (10, 13, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42, 118, problem, li, count]))
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
                seed = 42 + 2600 + 100 * problem + index
                index += 1
                scenario = Scenario(seed, tuple(sources), dict(stress_layout=layout, source_rng=[42, 118, problem, li, count]))
                yield f"{layout}__n{count}__{sign}", layout, "stress", scenario, ErrorConfig(model="adversarial", adversarial_sign=sign)


def freeze(paths):
    import hashlib
    checked_runs=(("historical-negatives",1302,665),("faithful-skips",1116,848))
    for name,count,expected_checks in checked_runs:
        folder=ROOT / "experiments/runs" / f"2026-09-11_{name}"
        result=json.loads((folder / "completion.json").read_text())
        tests=json.loads((folder / "checks.json").read_text())
        config=json.loads((folder / "run_config.json").read_text())
        assert result["executions"]==result["all_cleared"]==count and result["errors"]==0
        assert tests["passed"]==expected_checks and tests["failed"]==0
        names=["coupled_dispatch_policy.py","fast_dispatch_policy.py","geometry.py","policies.py","client.py","historical_pair_policy.py"]
        if name=="faithful-skips": names.append("faithful_skip_policy.py")
        for filename in names:
            assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()==config["code_sha256"][filename]
    _prior_freeze(paths)
    config=json.loads((OUT / "run_config.json").read_text())
    config.update(confirmation_seeds=list(range(127,137)),expected_executions=2925,
        derivation="42+85+repeat,0..9; not generated in prior runs",
        stress_derivation="SeedSequence([42,118,problem,layout_index,count]); errors42+2600+100*problem+index",
        untouched_future_seeds=list(range(137,147)),freeze_before_truth_generation=True,
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="After 2418 scored training runs; retain four faithful/no-skip pairs and existing range/packet/paper-layout comparators; historical first8 is modest ordinary and stress gain, recent8 is training stress-best with CPU cost. Q3 historical candidates have identical virtual scores and higher CPU; not advanced. Arc historical stress regressed and was not advanced. No parameter selection on confirmation",
        virtual_upper_bound_s=335136,instruction_upper_bound=9766,
        proof_files=["FAITHFUL_SKIP_GUARANTEE.md","HISTORICAL_PAIR_GUARANTEE.md","WIDE_PROBE_GUARANTEE.md"])
    write_json(OUT / "run_config.json",config)
    (OUT / "precheck.md").write_text("# 历史推断与保序删除确认前冻结\n\n2418次训练全清，历史665/保序848项检查通过。15候选先冻结，再生成127—136及新压力流，2925次；未来137—146未生成。408个21站候选均有独立真实盲区见证，不进入策略。保留无收益/压力退步/CPU代价，正式请求0。\n")


def summarize(rows):
    _prior_summary(rows)
    path = OUT / "summary.md"
    text = path.read_text().replace("seed42派生77—86", "seed42派生127—136").replace("Q4旧方格保守", "Q4已有中心分包")
    text = text.replace("# 冻结后确认：未用于调参的场景", "# 历史排除约束与保序检测删除：冻结后确认")
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
