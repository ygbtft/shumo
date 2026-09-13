"""Fresh confirmation after packet and discovery-priority training are frozen."""
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
import discovery_priority_experiments as builders
import replacement_experiments as certificates
import icra_confirmation as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_task-confirmation"
SPECS = {3: {
    "peer_layout9_proxy": dict(kind="base", layout="ring9"),
    "clearance7": dict(kind="clearance", layout="ring7"),
    "clearance9": dict(kind="clearance", layout="ring9"),
    "packet_center7": dict(kind="packet_clearance", layout="ring7"),
    "packet_center9": dict(kind="packet_clearance", layout="ring9"),
}, 4: {
    "quarter22": dict(kind="probe", layout="convex22", fraction=.25, share_cooldown=150.),
    "clearance_f015_22": dict(kind="clearance_probe", layout="convex22", fraction=.15, share_cooldown=150.),
    "packet_center22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150.),
    "packet_action4_22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=4),
    "packet_action24_22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=24),
    "packet_discover300_22": dict(kind="discovery_packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=4, discovery_weight=300.),
}}
_prior_freeze, _prior_summary = engine.freeze, engine.summarize


def all_paths():
    return builders.paths()


def cases(problem):
    cfg = ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(97, 107):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    index = 0
    for li, layout in enumerate(("boundary_outward", "boundary_tangent", "near_collinear", "cluster_far20", "range_transition")):
        for count in (10, 13, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42, 115, problem, li, count]))
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
                seed = 42 + 1700 + 100 * problem + index
                index += 1
                scenario = Scenario(seed, tuple(sources), dict(stress_layout=layout, source_rng=[42, 115, problem, li, count]))
                yield f"{layout}__n{count}__{sign}", layout, "stress", scenario, ErrorConfig(model="adversarial", adversarial_sign=sign)


def freeze(paths):
    _prior_freeze(paths)
    config = json.loads((OUT / "run_config.json").read_text())
    config.update(confirmation_seeds=list(range(97, 107)), expected_executions=2145,
        derivation="42+55+repeat,repeat0..9; not generated in any earlier run",
        stress_derivation="SeedSequence([42,115,problem,layout_index,count]); errors42+1700+100*problem+index",
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="After 2790 scored training runs; packet candidates preserve mean/CPU/tail tradeoffs; only discovery300 packet retained for lower training tail; clear-reward assumption rejected",
        virtual_upper_bound_s=314016, instruction_upper_bound=9766)
    write_json(OUT / "run_config.json", config)
    (OUT / "precheck.md").write_text("# 冻结前检查\n\n分包252项、发现排序276项检查通过；两轮2790计分训练全清。clear_weight省后续RF的假设因精确频道已跳过检测而重复记账，不作为成本模型推荐，未纳入新确认。11候选先冻结，再生成97—106和新压力流，2145次；初始化单列，正式请求0。\n")


def summarize(rows):
    _prior_summary(rows)
    path = OUT / "summary.md"
    text = path.read_text().replace("seed42派生77—86", "seed42派生97—106").replace("Q4旧方格保守", "Q4已有四分之一探测")
    text = text.replace("# 冻结后确认：未用于调参的场景", "# 分包任务与发现排序：冻结后确认")
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
