"""Check deferred scan movement and negative-pair certificates."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

from client import Client
from deferred_skip_policy import DeferredCompletionPolicy, DeferredWidthPolicy, DeferredFastWidthPolicy, pair_nonreception_certificate
from deferred_replay import expanded_plan, verify_actual_cost
from geometry import hull
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
from mock.scenario_gen import Source
from mock.geometry import covered
import faithful_skip_experiments as builders
import coupled_dispatch_experiments as coupled
import fast_dispatch_experiments as fast
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_deferred-scans"
FAMILIES = ((3,"area7","faithful_area7","area_return1_7","deferred_completion"),
            (4,"width015","faithful_width015","width40_f015_22","deferred_width"),
            (4,"arc05_width015","faithful_arc05_width015","arc05_noskip_width015","deferred_fast_width"),
            (4,"locked_width015","faithful_locked_width015","locked_noskip_width015","deferred_fast_width"))
SPECS = {p:{name:spec.copy() for name,spec in methods.items()} for p,methods in builders.SPECS.items()}
for problem,label,old,baseline,kind in FAMILIES:
    source = dict(builders.SPECS[problem][old],kind=kind)
    SPECS[problem]["deferred_"+label] = source.copy()
    for size in (4,8):
        SPECS[problem][f"predict{size}_"+label] = dict(source,predict_negatives=True,prediction_history=size)
EXPECTED = sum(map(len,SPECS.values()))*93
assert EXPECTED == 2232


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("deferred_"):
        return builders.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind = params.pop("kind")
    points = all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = {"deferred_completion": DeferredCompletionPolicy, "deferred_width": DeferredWidthPolicy,
           "deferred_fast_width": DeferredFastWidthPolicy}[kind]
    return cls(client, points, mixed=problem == 4, **params)


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving passed checks")
    checks,details = [],[]
    rng=np.random.default_rng(42)
    q=np.array([0.,0.]);a=np.array([500.,-100.]);b=np.array([500.,100.])
    poly=hull([[800.,-10.],[1000.,-10.],[1000.,10.],[800.,10.]])
    assert pair_nonreception_certificate(poly,q,a,b) is not None
    source=Source(1,900.,0.,1000.,0.)
    assert covered(source,(1200.,0.)) and all(not covered(source,tuple(x)) for x in (q,a,b))
    assert np.linalg.norm(q-[900.,0.])<1000.
    checks.append(dict(test="within_minimum_radius_directional_negative_prediction",passed=True))
    for i in range(80):
        angle=rng.uniform(0,2*np.pi);rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        shift=rng.uniform(-1000,1000,size=2)
        transformed=poly@rot.T+shift
        p0,a0,b0=(x@rot.T+shift for x in (q,a,b))
        assert pair_nonreception_certificate(transformed,p0,a0,b0) is not None
        checks.append(dict(test=f"pair_prediction_rotation_translation_{i}",passed=True))
    for i,(a,b) in enumerate((([100,0],[200,0]),([0,0],[100,100]),([-100,0],[100,0]))):
        assert pair_nonreception_certificate(poly,q,np.array(a),np.array(b)) is None
        checks.append(dict(test=f"degenerate_pair_no_certificate_{i}",passed=True))
    all_paths=paths()
    for problem,label,old,baseline,kind in FAMILIES:
        for case_id,category,split,scenario,error in training_cases(problem):
            folder=builders.OUT
            traces={}
            for name in (old,baseline):
                with gzip.open(folder / "traces" / f"q{problem}__{case_id}__{name}.jsonl.gz","rt") as stream:
                    traces[name]=[json.loads(line) for line in stream]
            for control,reference in ((dict(faithful_skip=False),baseline),(dict(defer_scan=False),old)):
                spec=dict(SPECS[problem]["deferred_"+label],**control)
                trace=traces[reference];index=0
                def transport(endpoint,raw):
                    nonlocal index
                    entry=trace[index]
                    assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(label,case_id,index)
                    index+=1
                    return 200,entry["response"]
                build(Client(transport,robot_id="mock-robot"),spec,problem,all_paths).run()
                assert index==len(trace)
                checks.append(dict(test=f"zero_change_{reference}_q{problem}_{case_id}",passed=True))
            for name in ("deferred_"+label,"predict4_"+label,"predict8_"+label):
                detail=expanded_plan(traces[baseline],SPECS[problem][name],problem,all_paths,build)
                details.append(dict(problem=problem,method=name,case_id=case_id,**detail))
                checks.append(dict(test=f"public_expanded_plan_q{problem}_{name}_{case_id}",passed=True,
                                   pair_skips=detail["pair_skips"],nonstationary_skips=detail["nonstationary_skips"]))
                if split=="stress" and case_id.endswith(("n16__negative","n10__spatial")):
                    sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                    stats=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][name],problem,all_paths).run()
                    assert len(sim.cleared)==len(scenario.sources)
                    assert not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
                    cost=verify_actual_cost(traces[baseline],sim.trace,detail,traces[baseline][-1]["response"]["virtual_time_s"],sim.virtual_time_s)
                    checks.append(dict(test=f"actual_cost_path_q{problem}_{name}_{case_id}",passed=True,**cost))
    write_json(OUT / "expanded_plan_checks.json",details)
    write_json(OUT / "checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0,official_calls=0))
    print("Passed",len(checks),"checks; nonstationary",sum(d["nonstationary_skips"] for d in details),
          "pair",sum(d["pair_skips"] for d in details),flush=True)


def freeze(all_paths):
    if (OUT / "run_config.json").exists():
        raise RuntimeError("Preserving training archive")
    result = json.loads((OUT / "checks.json").read_text())
    assert result["failed"] == 0
    snapshot = OUT / "code_snapshot"
    snapshot.mkdir()
    hashes = {}
    for path in ROOT.glob("*.py"):
        raw = path.read_bytes()
        (snapshot / path.name).write_bytes(raw)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67, 72)),
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(137,147)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; prior training streams",
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=EXPECTED,
        skip_certificate="Known-source range or two-negative certificate; preserve full logical plan; at least four retained unknown RF requests per scan realize deferred movement",
        dominance_scope="Versus respective no-skip deterministic plans, virtual time and commands; no CPU dominance claim",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 延后移动及负点预测训练前检查\n\n{result['passed']}项通过：方向盲区证书/旋转平移/退化、744条关闭功能/原地版严格反馈重放、1116条展开计划、72次实际协议及费用公式。24候选×93=2232，137—146未生成，正式请求0。\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    engine.OUT, engine.SPECS, engine.build, engine.freeze, engine.all_layouts = OUT, SPECS, build, freeze, paths
    if args.check:
        check()
    elif args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving scored run")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())], cwd=ROOT.parent,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid)+"\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
