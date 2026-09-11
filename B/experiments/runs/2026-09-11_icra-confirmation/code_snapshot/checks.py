"""Meaningful geometry/physics/protocol invariants, independent of policy success."""
import ast
import json
import math
from pathlib import Path
import time
import numpy as np
from client import Client, HttpTransport, Rejected
from coverage import square_stations, triangle_stations, route
from geometry import (ANGLE_BOUND_DEG, bearing_planes, halfplane_region, solve_bearings,
                      minimum_circle, minimum_circle_enumerated, update_region, optical_cover)
from simulator import Source, World, Protocol

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_independent"


def run_checks():
    results=[]
    def check(name,condition,**details):
        if not bool(condition):
            raise AssertionError(f"{name}: {details}")
        results.append({"check":name,"passed":True,**details})
    rng=np.random.default_rng(42)
    began=time.perf_counter()
    # Construct a literal equilateral feasible region using three valid 2-degree wedges.
    tri=np.array([[0.,0.],[40.,0.],[20.,20*math.sqrt(3)]])
    observations=[]
    for a,b in zip(tri,np.roll(tri,-1,axis=0)):
        u=(b-a)/np.linalg.norm(b-a)
        observations.append((a-1100*u,math.degrees(math.atan2(u[1],u[0]))+1))
    example=solve_bearings(observations)
    check("actual_bearing_region_equilateral_counterexample",abs(example["diameter"]-40)<1e-7 and
          abs(example["radius"]-40/math.sqrt(3))<1e-7,diameter=example["diameter"],radius=example["radius"])
    (OUT/"q1_triangle_example.json").write_text(json.dumps({"observations":[[p.tolist(),a] for p,a in observations],"solution":example},indent=2))
    check("parallel_bearings_unbounded",solve_bearings([([0,0],0),([0,1],0)])["status"]=="unbounded")
    check("inconsistent_bearings_empty",solve_bearings([([0,0],180),([1,0],0)])["status"]=="empty")
    check("point_degeneracy",halfplane_region([[1,0],[-1,0],[0,1],[0,-1]],[0,0,0,0])["status"]=="point")
    segment=halfplane_region([[1,0],[-1,0],[0,1],[0,-1]],[1,0,0,0])
    check("segment_degeneracy",segment["status"]=="segment" and abs(segment["diameter"]-1)<1e-8)
    skinny=halfplane_region([[1,0],[-1,0],[0,1],[0,-1]],[1000,0,1e-6,0])
    check("thin_polygon_not_mislabeled_segment",skinny["status"]=="bounded" and len(skinny["vertices"])==4)
    check("no_observations_unbounded",solve_bearings([])["status"]=="unbounded")
    check("zero_error_is_ray_not_line",solve_bearings([([0,0],0),([-1,0],180)],0)["status"]=="empty")
    differences=[]
    for i in range(180):
        points=rng.normal(size=(int(rng.integers(1,12)),2))*10**rng.uniform(-2,4)
        a=minimum_circle(points); b=minimum_circle_enumerated(points)
        differences.append(abs(a[1]-b[1]))
    check("incremental_circle_vs_support_enumeration_180",max(differences)<1e-6,max_absolute_radius_difference=max(differences))
    for truth_angle,reported,old_bound,label in [(10.0051,11.01,1.,"nearest"),(10.0099,9.,1.005,"truncate"),(359.9951,1.,1.,"wrap")]:
        g=1000*np.array([math.cos(math.radians(truth_angle)),math.sin(math.radians(truth_angle))])
        a,b=bearing_planes([0,0],reported,old_bound)
        a2,b2=bearing_planes([0,0],reported,ANGLE_BOUND_DEG)
        check("rounding_"+label,np.max(a@g-b)>0 and np.max(a2@g-b2)<1e-8)
    max_cover=0.
    # Independently test truth containment at extremal, rounded errors, including close/collinear observations.
    for i in range(600):
        g=rng.uniform(-900,900,2)
        poly=None
        first=None
        for j in range(3):
            theta=rng.uniform(-math.pi,math.pi)
            distance=rng.uniform(5.001,1500.)
            p=g-distance*np.array([math.cos(theta),math.sin(theta)])
            e=[-1.,1.,rng.uniform(-1.,1.)][j]
            angle=round((math.degrees(theta)+e)%360,2)%360
            first=angle if first is None else first
            poly=update_region(poly,p,angle)
            normals=np.roll(poly,-1,axis=0)-poly
            side=normals[:,0]*(g-poly)[:,1]-normals[:,1]*(g-poly)[:,0]
            check_name="bearing_truth_containment_1800_updates"
            if side.min() < -1e-5:
                raise AssertionError(check_name)
        cover,radius=optical_cover(poly,first)
        max_cover=max(max_cover,radius)
        if np.linalg.norm(cover-g,axis=1).min()>20:
            raise AssertionError("optical coverage")
    check("bearing_truth_containment_1800_updates",True)
    check("optical_cover_600_posteriors",max_cover<20.,max_radius=max_cover)
    # Rule checks use diagnostics with fewer than 10 sources, deliberately outside the official case distribution.
    w=World([Source(1,100,0,1000,0),Source(2,300,0,1000,None)])
    p=Protocol(w)
    c=Client(p.dispatch)
    c.enter()
    check("directional_back_no_signal",c.measure((90,0),1)["measure_result"]=="no_signal")
    check("directional_closed_boundary",c.measure((100,100),1)["measure_result"]=="direction")
    x=c.measure((200,0),1); y=c.measure((200.,-0.),1)
    check("fixed_error_same_numeric_location",x["svd_deg"]==y["svd_deg"])
    check("near_in_coverage_inclusive_5",c.measure((105,0),1)["measure_result"]=="near")
    check("optics_work_from_back_at_20",c.clear((80,0),1)["clear_result"]=="success")
    check("clear_does_not_change_channel",c.clear((300,0),2)["clear_result"]=="success" and w.channel==1 and c.channel==1)
    check("already_cleared_returns_not_found",c.clear((100,0),1)["clear_result"]=="no_target_in_range")
    check("cleared_signal_absent",c.measure((110,0),1)["measure_result"]=="no_signal")
    w=World([Source(1,0,0)])
    c=Client(Protocol(w).dispatch); c.enter()
    check("radius_inclusive_1000",c.measure((1000,0),1)["measure_result"]=="direction")
    check("radius_outside_1000",c.measure((1000.0001,0),1)["measure_result"]=="no_signal")
    w=World([]); p=Protocol(w); c=Client(p.dispatch); c.enter()
    times=[c.measure((300,400),1)["virtual_time_s"],c.measure((300,400),2)["virtual_time_s"],
           c.clear((300,0),3)["virtual_time_s"],c.measure((300,0),2)["virtual_time_s"],c.exit()["virtual_time_s"]]
    check("official_document_199_seconds_example",times==[105,111,194,199,199],times=times)
    w=World([]); p=Protocol(w)
    base={"arena_id":"default","robot_id":"offline-robot","request_id":"entry"}
    def dispatch(path,payload,**kw):
        return p.dispatch(path,json.dumps(payload,allow_nan=True).encode(),**kw)
    check("enter_does_not_reveal_truth",set(dispatch("/enter",base)[1])=={"accepted","real_timestamp_ms","virtual_time_s","max_virtual_duration_s","max_real_duration_s","remaining_real_duration_s"})
    action={**base,"request_id":"m","position":{"x":300,"y":400},"channel":1}
    first=dispatch("/measure",action)
    check("idempotent_exact_response",dispatch("/measure",action)==first and w.time_us==105_000000)
    check("idempotency_conflict_409",dispatch("/clear",action)[0]==409)
    invalid={**action,"request_id":"invalid","channel":1.5}
    check("fractional_channel_400",dispatch("/measure",invalid)[0]==400)
    invalid["channel"]=True
    check("boolean_channel_400",dispatch("/measure",invalid)[0]==400)
    invalid["channel"]=1.
    check("integer_float_channel_accepted",dispatch("/measure",invalid)[1]["accepted"])
    for i,value in enumerate([math.nan,math.inf,2000000.01]):
        check("bad_coordinate_"+str(i),dispatch("/measure",{**action,"request_id":f"bad{i}","position":{"x":value,"y":0}})[0]==400)
    bad={**action,"request_id":"fixable","chanell":1}
    response=dispatch("/measure",bad)
    check("unknown_field_rejected_without_time",response[0]==200 and response[1]["accepted"] is False and response[1]["virtual_time_s"]==0)
    del bad["chanell"]
    check("rejected_id_reusable",dispatch("/measure",bad)[1]["accepted"])
    for key,value in [("arena_id","other"),("robot_id","other")]:
        check("identity_"+key,dispatch("/measure",{**action,key:value})[1]["accepted"] is False)
    check("duplicate_json_400",p.dispatch("/enter",b'{"arena_id":"default","arena_id":"default"}')[0]==400)
    check("bom_400",p.dispatch("/enter",b'\xef\xbb\xbf{}')[0]==400)
    check("body_limit_413",p.dispatch("/enter",b' '*65537)[0]==413)
    check("exact_path_404",dispatch("/measure?x=1",action)[0]==404)
    check("method_405",dispatch("/measure",action,method="GET")[0]==405)
    check("content_type_415",dispatch("/measure",action,content_type="application/json; x=y")[0]==415)
    check("content_encoding_415",dispatch("/measure",action,encoding="gzip")[0]==415)
    check("utf8_content_type",dispatch("/measure",{**action,"request_id":"utf8"},content_type="application/json; charset=utf-8")[1]["accepted"])
    # Inject loss *after* execution, then retry identical raw body against idempotent fixture.
    import client as client_module
    from urllib.error import URLError
    calls=[]
    w=World([]); p=Protocol(w)
    class Response:
        status=200
        def __init__(self,data): self.data=data
        def __enter__(self): return self
        def __exit__(self,*args): return None
        def read(self): return json.dumps(self.data).encode()
    def fake_urlopen(request,timeout):
        calls.append(request.data)
        status,body=p.dispatch(request.full_url.rsplit(":2026",1)[1],request.data)
        if len(calls)==1:
            raise URLError("response lost after accepted action")
        return Response(body)
    old=client_module.urlopen
    client_module.urlopen=fake_urlopen
    try:
        cli=Client(HttpTransport("http://127.0.0.1:2026"))
        cli.enter()
        check("http_transport_lost_response_retry_identical",len(calls)==2 and calls[0]==calls[1] and w.commands==1)
    finally:
        client_module.urlopen=old
    # This test exercises HTTP construction/handling by injection; no listener or official server is contacted.
    calls=[]
    def rejected_transport(path,raw):
        return 200,{"accepted":False,"virtual_time_s":0,"real_timestamp_ms":0}
    cli=Client(rejected_transport); cli.virtual_s=199
    try:
        cli.measure((0,0),2)
        ok=False
    except Rejected:
        ok=cli.virtual_s==199 and cli.channel==1
    check("client_does_not_apply_rejected_state",ok)
    tree=ast.parse((ROOT/"policies.py").read_text())
    imported=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    attributes=[n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)]
    check("policy_static_no_truth_access","simulator" not in imported and not set(attributes)&{"sources","score","_sources","seed","radius","facing","__transport"})
    result={"seed":42,"passed":len(results),"wall_s":time.perf_counter()-began,"checks":results,
            "http_test_scope":"Injected urllib HTTP request/response and raw JSON fixture, no TCP listener, no official requests"}
    (OUT/"checks.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="checks"},ensure_ascii=False),flush=True)
    return result


if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    run_checks()
