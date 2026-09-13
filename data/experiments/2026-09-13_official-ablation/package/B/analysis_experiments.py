"""Q1/Q2 numerical checks, all-heading coverage audit, and explicit failure controls."""
import csv
import json
import math
from pathlib import Path
import time
import numpy as np
from coverage import square_stations,triangle_stations,route_length
from geometry import (ANGLE_BOUND_DEG,update_region,bearing_clip,minimum_circle,solve_bearings,
                      bearing_planes,cross)
from intelligent import choose_second,guaranteed_omni

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_independent"


def csv_write(name,rows):
    with (OUT/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def heading_coverage(points,stations,mixed):
    delta=stations[None,:,:]-points[:,None,:]
    distances=np.linalg.norm(delta,axis=2)
    mask=distances<=1000.+1e-8
    if not mixed:
        return mask.any(axis=1)
    # All headings at each sampled source, not one randomly selected heading.
    angles=np.sort(np.where(mask,np.arctan2(delta[:,:,1],delta[:,:,0]),10.),axis=1)
    count=mask.sum(axis=1)
    gaps=np.diff(angles,axis=1)
    gaps=np.where(np.arange(gaps.shape[1])[None,:] < count[:,None]-1,gaps,0.)
    last=angles[np.arange(len(points)),np.maximum(0,count-1)]
    maximum=np.maximum(gaps.max(axis=1),angles[:,0]+2*math.pi-last)
    return ((count>0)&(maximum<=math.pi+1e-8)) | (distances<=1e-9).any(axis=1)


def coverage_experiment():
    rng=np.random.default_rng(np.random.SeedSequence([42,2,0]))
    r=1800*np.sqrt(rng.random(20000)); a=rng.uniform(0,2*math.pi,len(r))
    points=r[:,None]*np.column_stack([np.cos(a),np.sin(a)])
    a=np.arange(1440)*2*math.pi/1440
    boundary=1800*np.column_stack([np.cos(a),np.sin(a)])
    square=square_stations(650)
    grids={"square650_full":(square,True),"square700_cropped":(square_stations(700,True),True),
           "triangle990_mixed":(triangle_stations(990),True),"triangle1700_omni":(triangle_stations(1700),False),
           "unsafe_interior_square":(square[np.linalg.norm(square,axis=1)<1800-1e-8],True)}
    rows=[]
    for label,(stations,mixed) in grids.items():
        for category,sources in [("uniform",points),("exact_boundary",boundary)]:
            covered=heading_coverage(sources,stations,mixed)
            delta=stations[None,:,:]-sources[:,None,:]
            distance=np.linalg.norm(delta,axis=2)
            outward=((delta*sources[:,None,:]).sum(axis=2)>=-1e-8)&(distance<=1000+1e-8)
            rows.append({"grid":label,"case":category,"stations":len(stations),"source_samples":len(sources),
                         "all_heading_covered":int(covered.sum()),"all_heading_coverage_fraction":float(covered.mean()),
                         "outward_covered":int(outward.any(axis=1).sum()) if mixed else None})
            if not label.startswith("unsafe"):
                assert covered.all()
    csv_write("coverage_independent.csv",rows)
    return rows


def q1_experiment():
    rows=[]
    for angle in [0,1,2,5,15,30,60,90,120,150,175,179,180]:
        t=math.radians(angle/2)
        p1=-1000*np.array([math.cos(t),math.sin(t)])
        p2=-1000*np.array([math.cos(t),-math.sin(t)])
        for e1 in [-1.,0.,1.]:
            for e2 in [-1.,0.,1.]:
                observations=[(p1,angle/2+e1),(p2,-angle/2+e2)]
                exact=solve_bearings(observations,error_deg=1.)
                post=None
                for p,a in observations:
                    post=update_region(post,p,round(a%360,2)%360)
                center,radius=minimum_circle(post)
                row={"intersection_angle_deg":angle,"error1":e1,"error2":e2,"pure_wedge_status":exact["status"],
                     "pure_wedge_diameter_m":exact.get("diameter") if math.isfinite(exact.get("diameter") or 0.) else None,
                     "pure_wedge_mec_radius_m":exact.get("radius") if math.isfinite(exact.get("radius") or 0.) else None,
                     "with_public_prior_outer_radius_m":radius,"certifies_20m":radius<=20.,"ray_intersection_error_m":None}
                u=np.array([math.cos(math.radians(observations[0][1])),math.sin(math.radians(observations[0][1]))])
                v=np.array([math.cos(math.radians(observations[1][1])),math.sin(math.radians(observations[1][1]))])
                denominator=float(cross(u,v))
                if abs(denominator)>1e-10:
                    point=p1+float(cross(p2-p1,v))/denominator*u
                    row["ray_intersection_error_m"]=float(np.linalg.norm(point))
                rows.append(row)
    csv_write("q1_angle_extremes.csv",rows)
    return rows


def q2_experiment():
    poly=update_region(None,np.zeros(2),0.)
    observations=[(np.zeros(2),0.)]
    candidates={"naive_perpendicular_500":np.array([0.,500.]),
                "guessed_distance_orthogonal":np.array([1000.,1000.]),
                "robust_lens_750_350":np.array([750.,350.])}
    for x in [250.,500.,750.,1000.,1250.]:
        for y in [100.,250.,400.,550.]:
            q=np.array([x,y])
            if guaranteed_omni(q,poly,np.zeros(2)):
                candidates[f"safe_grid_{x:g}_{y:g}"]=q
    decisions=[]
    for weight in [0.,.08,.4,1.6]:
        q,rows=choose_second(poly,observations,np.zeros(2),mixed=False,time_weight=weight)
        candidates[f"active_weight_{weight:g}"]=q
        decisions.extend({"time_weight":weight,**row} for row in rows)
    csv_write("q2_candidate_scores.csv",decisions)
    rows=[]
    for label,q in candidates.items():
        for distance in [6.,20.,100.,250.,500.,750.,1000.,1250.,1500.]:
            for initial_error in [-1.,0.,1.]:
                angle=math.radians(-initial_error)
                g=distance*np.array([math.cos(angle),math.sin(angle)])
                actual_radius=max(1000.,distance)
                received=np.linalg.norm(g-q)<=actual_radius+1e-8
                for second_error in [-1.,-.5,0.,.5,1.]:
                    if received:
                        if np.linalg.norm(g-q)<=5:
                            radius=5.
                        else:
                            a=round((math.degrees(math.atan2(g[1]-q[1],g[0]-q[0]))+second_error)%360,2)%360
                            posterior=update_region(poly,q,a)
                            center,radius=minimum_circle(posterior)
                    else:
                        center,radius=minimum_circle(poly)
                    rows.append({"candidate":label,"x":q[0],"y":q[1],"distance_unknown_m":distance,
                                 "initial_error":initial_error,"second_error":second_error,
                                 "received":bool(received),"posterior_outer_radius_m":radius,
                                 "move_measure_s":float(np.linalg.norm(q))/5+5,
                                 "universally_safe_certificate":bool(guaranteed_omni(q,poly,np.zeros(2)))})
    csv_write("q2_distance_error_sweep.csv",rows)
    summaries=[]
    for label,q in candidates.items():
        group=[r for r in rows if r["candidate"]==label]
        summaries.append({"candidate":label,"x":q[0],"y":q[1],"trials":len(group),
                          "reception_fraction":np.mean([r["received"] for r in group]),
                          "mean_radius_m":np.mean([r["posterior_outer_radius_m"] for r in group]),
                          "worst_radius_m":max(r["posterior_outer_radius_m"] for r in group),
                          "move_measure_s":group[0]["move_measure_s"],
                          "universal_certificate":group[0]["universally_safe_certificate"]})
    csv_write("q2_summary.csv",summaries)
    safe=[r for r in summaries if r["universal_certificate"]]
    tradeoffs=[]
    for weight in [0.,.1,.5,1.,2.,5.,10.]:
        row=min(safe,key=lambda r:r["worst_radius_m"]+weight*r["move_measure_s"])
        tradeoffs.append({"seconds_to_radius_weight":weight,**row})
    csv_write("q2_sampled_pareto.csv",tradeoffs)
    return summaries


def negative_controls(q1):
    original=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    counts=[r for r in original if r["sources"]>10]
    examples=[r for r in q1 if r["intersection_angle_deg"]==90 and (r["ray_intersection_error_m"] or 0)>20]
    result={"diameter_circle_counterexample":{"diameter_m":40.,"minimum_circle_radius_m":40/math.sqrt(3),
             "wrong_radius_m":20.,"wrong_clear_can_fail":True},
            "interior_only_outward_source":{"source":[1800.,0.],"radius":1000.,"facing_deg":0.,
             "reason":"For any detector strictly inside the disk, detector.x < 1800, outside the east-facing hemisphere"},
            "stop_at_10":{"cases_with_more_than_10_sources":len(counts),
             "missed_per_case_if_stop_on_tenth_clear_min":min(r["sources"]-10 for r in counts),
             "missed_per_case_if_stop_on_tenth_clear_max":max(r["sources"]-10 for r in counts),
             "interpretation":"Counterfactual prefix of accepted success responses; hidden count used only to score the invalid stop rule"},
            "two_ray_point_at_90deg":{"examples":examples},
            "warning":"Finite +/-1 endpoint tests do not optimize an arbitrary worst-case spatial error field"}
    (OUT/"negative_controls.json").write_text(json.dumps(result,indent=2))


def worst_bounds():
    # The broad bound uses a 3750m radius enclosing every strategy waypoint.
    S=49; N=16; L=3750; active=3; cover=108; chain=3100
    scan_move=(2*S-1)*L
    detour_move=N*(active+3)*2*L
    optical_move=N*chain
    action_seconds=20*S*6+N*active*6+N*(3+cover*3+2)
    bound=(scan_move+detour_move+optical_move)/5+action_seconds
    result={"max_stations":S,"max_sources":N,"waypoint_radius_bound_m":L,
            "max_active_measurements_per_source":active,"max_optical_cover_centers_per_source":cover,
            "optical_serpentine_length_bound_m":chain,"virtual_seconds_upper_bound":bound,
            "virtual_hours_upper_bound":bound/3600,"max_commands":20*S+N*active+N*(1+cover)+2,
            "assumptions":"Mathematical coverage/containment; accepted correct feedback; finite-precision margins; no HTTP failures; available real time sufficient",
            "outer_range_radius_m":1500/math.cos(math.pi/64),
            "first_wedge_rectangle_length_bound_m":1502.,"first_wedge_rectangle_width_bound_m":53.}
    assert bound<360000
    (OUT/"worst_case_bounds.json").write_text(json.dumps(result,indent=2))


if __name__=="__main__":
    started=time.perf_counter()
    coverage_experiment()
    q1=q1_experiment()
    q2_experiment()
    negative_controls(q1)
    worst_bounds()
    (OUT/"analysis_completion.json").write_text(json.dumps({"seed":42,"derived_stream":[42,2,0],"wall_s":time.perf_counter()-started},indent=2))
    print(f"Q1/Q2/coverage/negative controls completed in {time.perf_counter()-started:.2f}s")
