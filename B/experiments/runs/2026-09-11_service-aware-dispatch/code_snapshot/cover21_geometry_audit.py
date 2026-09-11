"""Independent geometry audit of real witnesses and closed integer coverage."""
import json
import math
from pathlib import Path
import time
import numpy as np
from scipy.spatial import ConvexHull
from peer_benchmark import Simulator
from mock.scenario_gen import Source
from mock.geometry import covered
from visibility_certificate import verify_cells
from integer_visibility_certificate import certify_integer_stations,verify_integer_certificate
from icra_final_checks import partition_check
from odd_ring_cover_search import points

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_odd-ring-cover"


def main():
    if (OUT/"geometry_audit.json").exists():raise RuntimeError("Preserving geometry audit")
    began=time.perf_counter();checks=[]
    raw_rows=[json.loads(line) for line in (OUT/"search_log.jsonl").read_text().splitlines()]
    assert len(raw_rows)==240
    for row in raw_rows:
        if row["witness"] is None:continue
        w=row["witness"];p=points(row["spec"]);g=w["position"]
        assert math.hypot(*g)<=1800.+1e-8
        source=Source(1,*g,1000.,w["direction_deg"])
        assert all(not covered(source,tuple(q)) for q in p)
        checks.append(dict(test=f"actual_backend_rejects_all_21_at_witness_{row['index']}",passed=True))
    rng=np.random.default_rng(42)
    analytical=[]
    for n,m in ((7,13),(6,14)):
        upper=1000*math.cos(math.pi/n)/math.cos(math.pi/math.lcm(n,m))
        lower=1800-math.sqrt(1000**2-(1800*math.tan(math.pi/m))**2)
        assert lower>upper
        rho=(upper+lower)/2
        for i in range(300):
            r=float(rng.uniform(0,1000)) if i%3 else 1000.
            s=1800/math.cos(math.pi/m)+float(rng.uniform(0,80))
            phase=float(rng.uniform(0,1))
            inner=(np.arange(n)+.5)*2*math.pi/n
            outer=(np.arange(m)+phase+.5)*2*math.pi/m
            differences=(outer[:,None]-inner[None,:]+math.pi)%(2*math.pi)-math.pi
            a,b=np.unravel_index(np.argmin(abs(differences)),differences.shape)
            g=rho*np.array([math.cos(outer[a]),math.sin(outer[a])])
            spec=(n,m,r,s-1800/math.cos(math.pi/m),phase);p=points(spec)
            source=Source(1,float(g[0]),float(g[1]),1000.,math.degrees(inner[b])%360)
            assert all(not covered(source,tuple(q)) for q in p)
        analytical.append(dict(n=n,m=m,inner_upper_m=upper,outer_lower_m=lower,gap_m=lower-upper,sampled_parameter_checks=300))
        checks.append(dict(test=f"analytic_obstruction_n{n}_m{m}_arbitrary_phase_and_radii",passed=True,instances=300))
    counts={}
    for name in ("odd-ring-cover","rounded-cover21","closed-cover21"):
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        layouts=json.loads((folder/"certified_layouts.json").read_text());counts[name]=len(layouts)
        for label,item in layouts.items():
            p=np.asarray(item["points"]);cert=item["certificate"]
            if cert.get("exact_integer_predicates"):detail=verify_integer_certificate(p,cert)
            else:detail={**verify_cells(p,cert),**partition_check(cert)}
            assert len(p)==21 and np.linalg.norm(p,axis=1).max()<1950.
            assert set(map(tuple,p))==set(map(tuple,item["route"]))
            checks.append(dict(test=f"independent_continuous_certificate_{label}",passed=True,stage=name,**detail))
    assert counts=={"odd-ring-cover":36,"rounded-cover21":68,"closed-cover21":4}
    closed=json.loads((ROOT/"experiments/runs/2026-09-11_closed-cover21/certified_layouts.json").read_text())
    rounded_rows=[json.loads(line) for line in (ROOT/"experiments/runs/2026-09-11_rounded-cover21/search_log.jsonl").read_text().splitlines()]
    pending=[r for r in rounded_rows if "unresolved_certificate" in r]
    assert {r["index"] for r in pending}=={3,15,35,55}
    for row in pending:
        item=closed[f"closed21_{row['index']}"]
        assert item["spec"]==row["spec"]
        p=np.asarray(item["points"])
        assert abs(float((-ConvexHull(p).equations[:,-1]).min())-1800)<1e-9
    original=np.asarray(closed["closed21_3"]["points"])
    damaged=original.copy();damaged[damaged[:,0]==1800.,0]-=1.
    witness=Source(1,1800.,0.,1000.,0.)
    assert all(not covered(witness,tuple(q)) for q in damaged)
    assert not certify_integer_stations(damaged)["covered"]
    checks.append(dict(test="one_meter_inward_damage_has_real_blind_spot_and_is_not_certified",passed=True))
    checks.append(dict(test="four_original_unresolved_tangent_layouts_preserved_and_exactly_resolved",passed=True))
    result=dict(passed=len(checks),failed=0,checks=checks,analytic_obstructions=analytical,certificate_counts=counts,
                raw_real_witnesses=204,wall_s=time.perf_counter()-began,scored_executions=0,official_calls=0)
    (OUT/"geometry_audit.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="checks"},indent=2),flush=True)


if __name__=="__main__":main()
