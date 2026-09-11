"""Independent numerical/analytic audits of the supplied 35-page paper images."""
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np
from geometry import solve_bearings, diameter, minimum_circle, minimum_circle_enumerated
from ring_coverage import DESIGNS, covering_radius, stations, metadata

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_peer-paper-review"


def unit(deg):
    t=math.radians(deg)
    return np.array([math.cos(t),math.sin(t)])


def independent_vertices(obs, epsilon=1.):
    # Independent direct line-line enumeration: no bounding box, no polygon clip.
    aa=[];bb=[]
    for point,theta in obs:
        for angle,sgn in ((theta-epsilon,1),(theta+epsilon,-1)):
            u=unit(angle);n=sgn*np.array([u[1],-u[0]])
            aa.append(n);bb.append(float(n@point))
    a=np.array(aa);b=np.array(bb);vertices=[]
    for i,j in itertools.combinations(range(len(a)),2):
        matrix=a[[i,j]]
        if abs(np.linalg.det(matrix))<1e-12:continue
        p=np.linalg.solve(matrix,b[[i,j]])
        if np.all(a@p<=b+1e-8) and all(np.linalg.norm(p-q)>1e-7 for q in vertices):
            vertices.append(p)
    v=np.array(vertices);center=v.mean(axis=0)
    return v[np.argsort(np.arctan2(v[:,1]-center[1],v[:,0]-center[0]))]


def kappa(v):
    d,pair=diameter(v);mid=(pair[0]+pair[1])/2
    return 2*np.linalg.norm(v-mid,axis=1).max()/d


def save(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results={};checks=[]
    def check(name,condition):
        checks.append({"name":name,"passed":bool(condition)})
    files=sorted((ROOT/"别人的结果/同学一").glob("*.PNG"))
    save(OUT/"paper_sha256.json",[{"name":p.name,"page":int(p.stem[4:])-8615,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in files])
    check("all_35_supplied_pages_present",len(files)==35)

    obs=[(np.array([-1000.,0.]),0.),(np.array([0.,-1000.]),90.)]
    v=independent_vertices(obs);ours=solve_bearings(obs,1.)
    mismatch=np.linalg.norm((v[0]+v[2]-v[1]-v[3])/2)
    check("zero_error_two_wedges_not_parallelogram",len(v)==4 and mismatch>0.1)
    check("independent_vertices_match_our_halfplanes",abs(diameter(v)[0]-ours["diameter"])<1e-7)
    results["two_wedge_counterexample"]={"source":[0,0],"observations":[[p.tolist(),t] for p,t in obs],"measurement_error_deg":0,
           "uncertainty_halfwidth_deg":1,"vertices":v.tolist(),"diagonal_midpoint_mismatch_m":float(mismatch),"kappa":float(kappa(v))}
    # Bounded search is only to exhibit a counterexample, never for strategy tuning.
    best=(0.,None,None)
    for ratio in (.1,.25,.5,1.,2.,4.,10.):
        for angle in np.linspace(3,177,349):
            test=[(np.array([-1000.,0.]),0.),(-1000*ratio*unit(angle),float(angle))]
            p=independent_vertices(test)
            if len(p)<3:continue
            value=kappa(p)
            if value>best[0]:best=(value,test,p)
    value,test,p=best
    d,pair=diameter(p);mid=(pair[0]+pair[1])/2
    check("two_zero_error_bearings_diameter_circle_can_miss",value>1.02 and all(np.linalg.norm(q)<=1500 for q,t in test))
    results["two_wedge_kappa_search"]={"max_kappa":float(value),"observations":[[q.tolist(),t] for q,t in test],"vertices":p.tolist(),
        "diameter_m":d,"diameter_midpoint":mid.tolist(),"diameter_circle_radius_m":d/2,"required_radius_at_that_midpoint_m":float(np.linalg.norm(p-mid,axis=1).max()),
        "source":[0,0],"actual_station_source_distances_m":[float(np.linalg.norm(q)) for q,t in test],
        "caveat":"Finite search is not a universal maximum theorem. The selected example has both station-source distances 1000m and exact representable bearings 0.00 and 90.50, hence is physically valid at zero actual error."}

    a=1200.;source=np.array([a/2,a*math.sqrt(3)/6])
    s=np.array([[0,0],[a,0],[a/2,a*math.sqrt(3)/2]])
    obs=[(p,math.degrees(math.atan2(*(source-p)[::-1]))) for p in s]
    v=independent_vertices(obs);center,r=minimum_circle(v);indcenter,indradius=minimum_circle_enumerated(v);d,_=diameter(v)
    check("paper_equilateral_construction_is_hexagon",len(v)==6)
    check("minimum_circle_independent_support_agrees",abs(r-indradius)<1e-7)
    results["paper_three_station_construction"]={"side_m":a,"source":source.tolist(),"vertices":v.tolist(),"vertex_count":len(v),
        "diameter_m":d,"mec_center":center.tolist(),"mec_radius_m":r,"kappa_about_diameter_midpoint":float(kappa(v)),"twice_mec_radius_over_diameter":2*r/d}
    # Three different collinear stations, two valid source worlds, identical feedback.
    points=np.array([[0.,0.],[100.,0.],[200.,0.]])
    source_a=np.array([600.,0.]);source_b=np.array([1400.,0.])
    check("three_bearings_do_not_certify_15m",all(5<np.linalg.norm(g-q)<=1500 for g in (source_a,source_b) for q in points))
    results["three_bearing_ambiguity"]={"stations":points.tolist(),"returned_bearings_deg":[0,0,0],"consistent_source_a":source_a.tolist(),
        "consistent_source_b":source_b.tolist(),"source_separation_m":800,"radius_m":1500,"error_deg":0,
        "smallest_possible_cover_radius_lower_bound_m":400}

    source=100*unit(30);q=np.array([640.,931.3]);distance=float(np.linalg.norm(q-source))
    check("q2_paper_second_station_can_lose_signal",5<np.linalg.norm(source)<=1000 and distance>1000)
    results["q2_reception_counterexample"]={"first_station":[0,0],"first_bearing_deg":30,"source":source.tolist(),"receive_radius_m":1000,
        "second_station":q.tolist(),"first_distance_m":100,"second_distance_m":distance,"first_feedback":"direction 30.00","second_feedback":"no_signal"}
    sigma=math.radians(1)/math.sqrt(3)
    def ellipse_major(angle):
        return sigma*800/math.sqrt(1-abs(math.cos(math.radians(angle))))
    results["gdop_and_internal_arithmetic"]={"sigma_radians":sigma,"d800_gamma90_major_m":ellipse_major(90),"d800_gamma30_major_m":ellipse_major(30),
        "paper_text_major_m":[9.,17.6],"best105_67_twenty_percent_limit":105.67*1.2,"paper_box_corner_1020_minus40_worst_m":189.13,
        "reduction_304_42_to105_67_percent":100*(304.42-105.67)/304.42,"baseline_excess_percent_using_new_denominator":100*(304.42-105.67)/105.67}
    check("q2_claimed_twenty_percent_box_contradicts_own_table",189.13>1.2*105.67)

    designs=metadata();rng=np.random.default_rng(42)
    # Boundary and interior grid; proof above remains the universal certificate.
    radii=np.linspace(0,1800,181);angles=np.linspace(0,2*math.pi,1440,endpoint=False)
    grid=(radii[:,None,None]*np.column_stack((np.cos(angles),np.sin(angles)))[None,:,:]).reshape(-1,2)
    for name,(n,a) in DESIGNS.items():
        path=stations(n,a);sample_max=0.
        for chunk in np.array_split(grid,30):
            sample_max=max(sample_max,float(np.linalg.norm(chunk[:,None,:]-path[None,:,:],axis=2).min(axis=1).max()))
        analytic=covering_radius(n,a)
        designs[name]["grid_max_m"]=sample_max
        check(f"{name}_sample_agrees_with_exact_radius",abs(sample_max-analytic)<1e-6)
        check(f"{name}_continuous_coverage_margin",analytic<1000)
    results["ring_coverage"]=designs
    # Exact boundary outward source: all stations with ||q|| <= 1800 except q=g
    # are in its rear halfplane.  Include all rings explicitly named in paper.
    rings=[(6,900),(10,1700),(12,1500),(16,1800)]
    ring_points=np.vstack([np.zeros((1,2))]+[a*np.column_stack((np.cos(np.arange(n)*2*math.pi/n),np.sin(np.arange(n)*2*math.pi/n))) for n,a in rings])
    outward=unit(7);g=1800*outward;dots=(ring_points-g)@outward
    check("q4_all_paper_scan_rings_miss_outward_boundary_source",bool(np.all(dots<0)))
    results["q4_boundary_outward_counterexample"]={"source":g.tolist(),"direction_deg":7,"receive_radius_m":1000,
        "paper_rings_n_radius":rings,"nearest_station_distance_m":float(np.linalg.norm(ring_points-g,axis=1).min()),
        "max_front_halfplane_dot_m":float(dots.max()),"stations_tested":len(ring_points),"detectable_stations":0,
        "scope":"Counterexample to proposed finite scan-set coverage; not an execution of unavailable peer policy."}
    save(OUT/"paper_numeric_checks.json",results)
    save(OUT/"checks.json",{"passed":sum(c["passed"] for c in checks),"failed":sum(not c["passed"] for c in checks),"checks":checks})
    print(json.dumps({"checks":len(checks),"failed":sum(not c["passed"] for c in checks),"two_wedge_kappa":results["two_wedge_counterexample"]["kappa"],
        "max_searched_kappa":float(value),"q2_lost_signal_distance":distance,"rings":designs},indent=2))
    assert all(c["passed"] for c in checks)


if __name__=="__main__":main()
