"""Frozen route optimization then paired offline evaluation. B-only artifacts."""
import argparse
from dataclasses import asdict
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import numpy as np
from coverage import square_stations, triangle_stations, route_length
from route_algorithms import METHODS, STOCHASTIC, optimize
from adaptive_routes import AdaptivePolicy
from client import Client
from policies import Policy
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, mandatory_conditions, Simulator, Limits, Protocol
from mock.scenario_gen import Scenario, Source

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"experiments/runs/2026-09-10_metaheuristics"
SETS = {"square650": square_stations(), "square700": square_stations(700, True),
        "q3_triangle": triangle_stations(1700), "q4_triangle": triangle_stations(990)}
STRATEGIES = METHODS + ("adaptive_greedy", "adaptive_two_opt")
TASKS = (("q3_active", "q3_triangle", False, True),
         ("q4_active", "q4_triangle", True, True),
         ("q4_conservative", "square700", True, False))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        writer.writeheader()
        writer.writerows(rows)


def freeze():
    if (OUT/"run_config.json").exists():
        raise RuntimeError("Refusing to overwrite this experiment; use a fresh --output")
    check = json.loads((OUT/"checks.json").read_text())
    assert check["failed"] == 0
    (OUT/"code_snapshot").mkdir()
    code = {}
    for path in sorted(ROOT.glob("*.py")):
        raw = path.read_bytes()
        (OUT/"code_snapshot"/path.name).write_bytes(raw)
        code[path.name] = hashlib.sha256(raw).hexdigest()
    cfg = {"base_seed": 42, "optimizer_seeds": list(range(42, 47)),
           "optimizer_derivation": "42 + repeat, repeat = 0..4",
           "comparison_budget": 100000, "budget_unit": "one full candidate cost or one 2-opt delta; common seed preprocessing outside this count; wall time includes preprocessing",
           "early_stop": "certified geometric length lower bound attained",
           "methods": METHODS, "strategies": STRATEGIES, "tasks": TASKS,
           "station_sets": {k: p.tolist() for k, p in SETS.items()},
           "evaluation_seeds": list(range(52, 57)), "evaluation_derivation": "42 + 10 + repeat, repeat = 0..4; not used in earlier peer run",
           "stress_seed": "SeedSequence([42, 20, layout_index, count]); error_seed=42+100+case_index",
           "policy_parameters": {"max_active": 3, "time_weight": .08, "optimized": True},
           "selection": "Per method choose smallest static route length across optimizer repeats; stable first seed tie. Never select route from online outcomes.",
           "paired_rule": "Identical source locations/channels/radii/faces and fixed spatial error field across all methods in a case",
           "peer_commit": "c477d3660368f27c7131a0591426b4c4f107ea5d",
           "handoff_commit_same_core": "ededa9e13f1864be88add579b6724f45bc01fc50",
           "official_requests": 0, "policy_truth_access": False, "source_counts_to_policy": False,
           "cpu_threads": 1, "python": sys.version, "executable": sys.executable,
           "numpy": np.__version__, "platform": platform.platform(), "pid": os.getpid(), "code_sha256": code}
    write_json(OUT/"run_config.json", cfg)
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{check['passed']}项算法检查通过；不修改共享策略、上游或原始附件。\n\nPython：`{sys.executable}`；NumPy：{np.__version__}；单线程CPU；基础种子42。新配置与代码快照已保存。命令事先写入 command.sh；长实验后台运行，逐条刷新日志。全部传输为同学 Protocol.handle 的进程内调用，正式连接次数0。\n")


def static_experiment():
    rows, selected, details = [], {}, {}
    for name, points in SETS.items():
        selected[name] = {}
        for method in METHODS:
            runs = []
            for seed in (range(42,47) if method in STOCHASTIC else [42]):
                path, meta = optimize(points, method, seed=seed, budget=100000)
                rows.append({"point_set": name, **{k:v for k,v in meta.items() if k not in ("history", "indices")}})
                key = f"{name}__{method}__{seed}"
                details[key] = {**meta, "points": path.tolist()}
                runs.append((path, meta))
                print(f"static {key}: {meta['best_m']:.6f} m, {meta['comparisons']} comparisons, {meta['wall_s']:.3f}s, optimal={meta['certified_optimal']}", flush=True)
            best = min(runs, key=lambda r: round(r[1]["best_m"], 6))
            selected[name][method] = {"points": best[0].tolist(), "seed": best[1]["seed"], "length_m": best[1]["best_m"],
                                      "precompute_total_s": sum(m["wall_s"] for p,m in runs)}
        write_csv(OUT/"static_trials.csv", rows)
        write_json(OUT/"static_runs.json", details)
    write_json(OUT/"selected_routes.json", selected)
    frozen = hashlib.sha256((OUT/"selected_routes.json").read_bytes()).hexdigest()
    write_json(OUT/"routes_frozen_before_evaluation.json", {"sha256": frozen, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "selection_uses_online_feedback": False})
    return selected


def cases(mixed):
    cfg = ScenarioConfig(directional_fraction=.5 if mixed else 0.)
    for label, scfg, ecfg in mandatory_conditions(cfg, ErrorConfig()):
        for seed in range(52,57):
            yield f"{label}__{seed}", label, "ordinary", generate(seed, scfg), ecfg
    case_index = 0
    for layout_index, layout in enumerate(("boundary_outward_min", "near_collinear_min", "unknown_count_late")):
        for count in (10, 16):
            rng = np.random.default_rng(np.random.SeedSequence([42,20,layout_index,count]))
            channels = list(rng.choice(np.arange(1,20), count-1, replace=False)) + [20]
            angles = (np.arange(count)/count + .037)*2*math.pi
            if layout == "boundary_outward_min":
                points = 1800*np.column_stack((np.cos(angles), np.sin(angles)))
            elif layout == "near_collinear_min":
                axis = np.array([math.cos(.317), math.sin(.317)])
                normal = np.array([-axis[1],axis[0]])
                points = np.linspace(-1750,1750,count)[:,None]*axis + rng.uniform(-.05,.05,count)[:,None]*normal
            else:
                points = rng.normal(0,170,size=(count,2))
                points[-1] = (1800.,0.)
            sources = []
            for i, (ch, point) in enumerate(zip(channels,points)):
                direction = None
                if mixed and i != 0:
                    direction = math.degrees(math.atan2(point[1],point[0])) % 360
                sources.append(Source(int(ch),float(point[0]),float(point[1]),1000.,direction))
            for sign in ("positive", "negative", "spatial"):
                seed = 42+100+case_index
                label = f"{layout}__n{count}__{sign}"
                scenario = Scenario(seed, tuple(sources), {"stress_layout":layout,"count":count,"source_rng":[42,20,layout_index,count]})
                yield label, layout, "stress", scenario, ErrorConfig(model="adversarial",adversarial_sign=sign)
                case_index += 1


def trace_metrics(trace):
    position, channel = (0.,0.), 1
    move, measures, clears, switches = 0., 0, 0, 0
    for entry in trace:
        if entry["path"] not in ("/measure", "/clear"):
            continue
        request = entry["request"]
        q = (request["position"]["x"], request["position"]["y"])
        move += math.dist(position, q)
        position = q
        if entry["path"] == "/measure":
            measures += 1
            switches += int(request["channel"] != channel)
            channel = request["channel"]
        else:
            clears += 1
    return dict(move_m=move, measurements=measures, clear_calls=clears, switches=switches)


def evaluate(selected):
    (OUT/"traces").mkdir()
    (OUT/"scenarios_scoring_only").mkdir()
    rows = []
    started = time.perf_counter()
    with (OUT/"trials.jsonl").open("x") as stream:
        for task, point_set, mixed, active in TASKS:
            for case_index, (case_id, category, split, scenario, ecfg) in enumerate(cases(mixed)):
                case_name = f"{task}__{case_id}"
                write_json(OUT/"scenarios_scoring_only"/f"{case_name}.json", {"scenario":scenario.to_dict(),"error":asdict(ecfg)})
                for method in STRATEGIES:
                    points = np.array(selected[point_set]["two_opt" if method.startswith("adaptive_") else method]["points"])
                    sim = Simulator(scenario, ErrorField(scenario.seed,ecfg), Limits(countdown_s=0))
                    client = Client(PeerTransport(Protocol(sim)), robot_id="mock-robot")
                    if method.startswith("adaptive_"):
                        policy = AdaptivePolicy(client,points,polish=method=="adaptive_two_opt",mixed=mixed,active=active,optimized=True)
                    else:
                        policy = Policy(client,points,mixed=mixed,active=active,optimized=True)
                    began, cpu = time.perf_counter(), time.process_time()
                    failure, extra = "", {}
                    try:
                        extra = policy.run()
                    except Exception as exc:
                        failure = repr(exc)
                        (OUT/"traces"/f"{case_name}__{method}.error.txt").write_text(traceback.format_exc())
                    row = {"case_id":case_id, "task":task, "point_set":point_set, "method":method,
                           "category":category, "split":split, "seed":scenario.seed,
                           "sources":len(scenario.sources),"cleared":len(sim.cleared),
                           "all_cleared":len(scenario.sources)==len(sim.cleared),
                           "total_virtual_s":sim.virtual_time_s,
                           "per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                           "commands":len(sim.trace), "wall_s":time.perf_counter()-began,"cpu_s":time.process_time()-cpu,
                           "failure":failure, "missed_channels":sorted(set(sim.sources)-sim.cleared),
                           **trace_metrics(sim.trace), **extra}
                    rows.append(row)
                    stream.write(json.dumps(row, allow_nan=False)+"\n")
                    stream.flush()
                    with gzip.open(OUT/"traces"/f"{case_name}__{method}.jsonl.gz", "wt") as f:
                        for entry in sim.trace:
                            f.write(json.dumps(entry,separators=(",",":"))+"\n")
                    if failure or not row["all_cleared"]:
                        print(f"FAIL {case_name} {method}: {failure} {row['missed_channels']}",flush=True)
                if (case_index+1) % 5 == 0 or split == "stress":
                    print(f"online {task} {case_index+1}/93; {len(rows)} executions; elapsed {time.perf_counter()-started:.1f}s",flush=True)
    write_csv(OUT/"trials.csv",rows)
    write_json(OUT/"completion.json", {"executions":len(rows), "all_cleared":sum(r["all_cleared"] for r in rows),
               "errors":sum(bool(r["failure"]) for r in rows), "evaluation_wall_s":time.perf_counter()-started})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch",action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    global OUT
    if args.output:
        OUT = Path(args.output).resolve()
        if not OUT.is_relative_to(ROOT):
            parser.error("Only B/ output is authorized")
    OUT.mkdir(parents=True,exist_ok=True)
    if args.launch:
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            process = subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"--output",str(OUT)],
                cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(process.pid)+"\n")
        print(f"Background PID {process.pid}; log {OUT/'log.txt'}")
        return
    freeze()
    selected = static_experiment()
    evaluate(selected)


if __name__ == "__main__":
    main()
