"""Freeze coupled dispatch and negative-feedback policies before new scenes."""
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
import fast_dispatch_experiments as builders
import coupled_dispatch_experiments as coupled
import replacement_experiments as certificates
import icra_confirmation as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_coupled-confirmation"
SPECS = {3: {
    "peer_layout9_proxy":dict(kind="base",layout="ring9"),
    "area_return1_7":coupled.SPECS[3]["area_return1_7"].copy(),
    "range_area7":coupled.SPECS[3]["range_area7"].copy(),
    "fast_locked_area7":builders.SPECS[3]["fast_locked_area7"].copy(),
},4:{
    "packet_center22":dict(kind="packet_probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "width40_f015_22":coupled.SPECS[4]["width40_f015_22"].copy(),
    "range_width015":coupled.SPECS[4]["range_width015"].copy(),
    "fast_arc05_width015":builders.SPECS[4]["fast_arc05_width015"].copy(),
    "fast_locked_width015":builders.SPECS[4]["fast_locked_width015"].copy(),
    "fast_negative_arc05_width015":builders.SPECS[4]["fast_negative_arc05_width015"].copy(),
}}
build = builders.build
_prior_freeze, _prior_summary = engine.freeze, engine.summarize


def all_paths():
    return builders.paths()


def cases(problem):
    cfg = ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(117, 127):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    index = 0
    for li, layout in enumerate(("boundary_outward", "boundary_tangent", "near_collinear", "cluster_far20", "range_transition")):
        for count in (10, 13, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42, 117, problem, li, count]))
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
                seed = 42 + 2300 + 100 * problem + index
                index += 1
                scenario = Scenario(seed, tuple(sources), dict(stress_layout=layout, source_rng=[42, 117, problem, li, count]))
                yield f"{layout}__n{count}__{sign}", layout, "stress", scenario, ErrorConfig(model="adversarial", adversarial_sign=sign)


def freeze(paths):
    import hashlib
    checked_runs=(("coupled-dispatch",1674,609),("negative-hull",1116,533),("fast-dispatch",744,532))
    for name,count,expected_checks in checked_runs:
        folder=ROOT / "experiments/runs" / f"2026-09-11_{name}"
        result=json.loads((folder / "completion.json").read_text())
        tests=json.loads((folder / "checks.json").read_text())
        config=json.loads((folder / "run_config.json").read_text())
        assert result["executions"]==result["all_cleared"]==count and result["errors"]==0
        assert tests["passed"]==expected_checks and tests["failed"]==0
        names=["coupled_dispatch_policy.py","geometry.py","policies.py","client.py"]
        if name!="coupled-dispatch":names.append("negative_hull_policy.py")
        if name=="fast-dispatch":names.append("fast_dispatch_policy.py")
        for filename in names:
            assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()==config["code_sha256"][filename]
    _prior_freeze(paths)
    config=json.loads((OUT / "run_config.json").read_text())
    config.update(confirmation_seeds=list(range(117,127)),expected_executions=1950,
        derivation="42+75+repeat,0..9; not generated in prior runs",
        stress_derivation="SeedSequence([42,117,problem,layout_index,count]); errors42+2300+100*problem+index",
        untouched_future_seeds=list(range(127,137)),freeze_before_truth_generation=True,
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="After 3534 scored training runs; preserve Q3 paper proxy and current methods; Q4 center packet and width baseline, range skips, two coupled routes, one negative-region candidate; parameters not tuned on confirmation",
        virtual_upper_bound_s=335136,instruction_upper_bound=9766,
        proof_files=["COUPLED_DISPATCH_GUARANTEE.md","NEGATIVE_FEEDBACK_GEOMETRY.md","WIDE_PROBE_GUARANTEE.md"])
    write_json(OUT / "run_config.json",config)
    (OUT / "precheck.md").write_text("# 联动确认前冻结\n\n3534次训练全清；联动609、负反馈533、加速532项检查通过，决策文件与各自训练快照一致。10候选先冻结再生成117—126和新压力流，1950次。负反馈的越界测试夹具异常保留，修复仅限定合法源圆域。入口/出口只用于规划，不当真值；跳过请求需严格距离证书。正式请求0。\n")


def summarize(rows):
    _prior_summary(rows)
    path = OUT / "summary.md"
    text = path.read_text().replace("seed42派生77—86", "seed42派生117—126").replace("Q4旧方格保守", "Q4已有中心分包")
    text = text.replace("# 冻结后确认：未用于调参的场景", "# 保证扫描与定位服务联动：冻结后确认")
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
