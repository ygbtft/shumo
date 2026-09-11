"""Independent certificates, feedback-only replay and immutable-input audit."""
import ast
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from client import Client
from policies import Policy
from adaptive_routes import AdaptivePolicy, remaining_route

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_metaheuristics"


def main():
    checks=[]
    routes=json.loads((OUT/"selected_routes.json").read_text())
    config=json.loads((OUT/"run_config.json").read_text())
    expected=config["station_sets"]
    for name,methods in routes.items():
        for method,item in methods.items():
            points=item["points"]
            assert Counter(map(tuple,points))==Counter(map(tuple,expected[name]))
            assert math.dist(points[0],(0,0))<1e-8
            length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
            assert abs(length-item["length_m"])<1e-7
            checks.append({"test":f"independent_permutation_cost_{name}_{method}","passed":True})
    for name,method,length,edge in (("q4_triangle","immune",29700,990),("q3_triangle","two_opt",30600,1700),("square650","two_opt",31200,650)):
        p=routes[name][method]["points"]
        distances=[math.dist(a,b) for a,b in zip(p,p[1:])]
        assert all(abs(d-edge)<1e-8 for d in distances) and abs(sum(distances)-length)<1e-7
        checks.append({"test":f"minimum_edge_length_certificate_{name}","passed":True,"edges":len(distances),"edge_m":edge,"length_m":length})
    p=routes["square700"]["two_opt"]["points"]
    ids=[(round(x/700),round(y/700)) for x,y in p]
    counts=Counter((x+y)%2 for x,y in ids)
    same=sum((sum(a)-sum(b))%2==0 for a,b in zip(ids,ids[1:]))
    assert counts=={0:21,1:24} and same==3
    assert abs(sum(math.dist(a,b) for a,b in zip(p,p[1:]))-(44*700+3*700*(math.sqrt(2)-1)))<1e-7
    checks.append({"test":"checkerboard_lower_bound_attainment","passed":True,"color_counts":dict(counts),"same_color_edges":same})
    # Traces supply feedback but no World/Scenario objects or latent fields.
    for task,point_set,mixed,active in (("q3_active","q3_triangle",False,True),("q4_active","q4_triangle",True,True),("q4_conservative","square700",True,False)):
        for method in ("immune","fireworks","adaptive_greedy","adaptive_two_opt"):
            path=OUT/"traces"/f"{task}__uniform__iid__52__{method}.jsonl.gz"
            with gzip.open(path,"rt") as f:
                trace=[json.loads(line) for line in f]
            index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"], f"Request mismatch at {index}"
                index+=1
                return 200,entry["response"]
            cli=Client(replay,robot_id="mock-robot")
            p=np.array(routes[point_set]["two_opt" if method.startswith("adaptive_") else method]["points"])
            policy=AdaptivePolicy(cli,p,polish=method=="adaptive_two_opt",mixed=mixed,active=active,optimized=True) if method.startswith("adaptive_") else Policy(cli,p,mixed=mixed,active=active,optimized=True)
            result=policy.run()
            assert index==len(trace)
            checks.append({"test":f"feedback_only_exact_replay_{task}_{method}","passed":True,"commands":index,"source_truth_present":False})
    # A smaller optional suffix cannot lose or duplicate an unvisited station.
    rng=np.random.default_rng(42)
    for polish in (False,True):
        points=rng.normal(size=(16,2))*1800
        current=rng.normal(size=2)*2000
        order=remaining_route(points,current,polish)
        assert np.array_equal(np.sort(order),np.arange(len(points)))
        nn=remaining_route(points,current,False)
        def length(ids):return math.dist(current,points[ids[0]])+sum(math.dist(points[a],points[b]) for a,b in zip(ids,ids[1:]))
        assert length(order)<=length(nn)+1e-7
        checks.append({"test":f"adaptive_remaining_station_preservation_{polish}","passed":True})
    originals=json.loads((ROOT/"inputs_readonly_extract/input_sha256.json").read_text())
    for relative,wanted in originals.items():
        assert hashlib.sha256((ROOT.parent/relative).read_bytes()).hexdigest()==wanted
    old_config=json.loads((ROOT/"experiments/runs/2026-09-10_independent/run_config.json").read_text())
    public="project/topic_probes/b_probe.py"
    assert hashlib.sha256((ROOT.parent/public).read_bytes()).hexdigest()==old_config["input_sha256"][public]
    checks.append({"test":"three_original_documents_and_public_probe_unchanged","passed":True})
    for name in ("shumo-b","shumo-b-macos-handoff"):
        result=subprocess.run(["git","-C",str(ROOT/"reference"/name),"status","--porcelain"],capture_output=True,text=True,check=True)
        assert not result.stdout.strip()
        checks.append({"test":f"upstream_readonly_{name}","passed":True})
    for name in ("geometry.py","coverage.py","client.py","policies.py","intelligent.py"):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==config["code_sha256"][name]
    checks.append({"test":"shared_policy_and_geometry_not_changed","passed":True})
    all_rows=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    all_rows += [json.loads(line) for line in (OUT/"confirmation/trials.jsonl").read_text().splitlines()]
    assert len(all_rows)==3969
    assert all(r["stop_reason"] in ("public_upper_bound_16","full_coverage_and_all_discovered_cleared") for r in all_rows)
    assert all(r["cleared"]==16 for r in all_rows if r["stop_reason"]=="public_upper_bound_16")
    # Instrumentation: iterator may calculate one unused next point before a 16-source stop;
    # commands/stations_visited record the actual action count, and this is harmless.
    assert all(r["commands"]<=2774 and r["total_virtual_s"]<=238102 for r in all_rows)
    checks.append({"test":"all_stops_have_public_certificate_and_action_limits","passed":True,"executions":len(all_rows)})
    for p in ROOT.glob("*.py"):
        ast.parse(p.read_text(),filename=str(p))
    checks.append({"test":"top_level_python_syntax","passed":True})
    frozen=json.loads((OUT/"routes_frozen_before_evaluation.json").read_text())
    assert hashlib.sha256((OUT/"selected_routes.json").read_bytes()).hexdigest()==frozen["sha256"]
    checks.append({"test":"pre_evaluation_route_hash_preserved","passed":True})
    result={"passed":len(checks),"failed":0,"checks":checks,"official_calls":0,
            "new_executions":len(all_rows),"all_cleared":sum(r["all_cleared"] for r in all_rows),
            "stop_reason_counts":dict(Counter(r["stop_reason"] for r in all_rows))}
    (OUT/"final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k!="checks"},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
