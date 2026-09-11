"""Synthetic, rule-based B probes; these are NOT official simulator scores."""
import hashlib
import math
import time

import numpy as np
import pandas as pd

from common import DATA, OUT, SEED, log, record_environment, save_json

ERROR = math.radians(1.005)  # One-degree bound plus rounding to 0.01 degree.


def cross(a, b):
    return a[..., 0]*b[..., 1]-a[..., 1]*b[..., 0]


def clip(poly, normal, bound):
    """Intersect a convex polygon with normal @ x <= bound."""
    if len(poly) == 0:
        return poly
    signed = poly@normal-bound
    out=[]
    for i in range(len(poly)):
        a, b = poly[i-1], poly[i]
        fa, fb = signed[i-1], signed[i]
        inside_a, inside_b = fa <= 1e-8, fb <= 1e-8
        if inside_a != inside_b:
            out.append(a+(b-a)*(fa/(fa-fb)))
        if inside_b:
            out.append(b)
    return np.asarray(out).reshape(-1, 2)


def update_region(poly, point, angle_deg, first):
    if first:
        # A square encloses the known disk; circumscribed polygon encloses range disk.
        poly=np.array([[-1800.,-1800.],[1800.,-1800.],[1800.,1800.],[-1800.,1800.]])
        for theta in np.arange(16)*2*np.pi/16:
            normal=np.array([np.cos(theta),np.sin(theta)])
            poly=clip(poly, normal, normal@point+1500)
    theta=math.radians(angle_deg)
    low, high=theta-ERROR, theta+ERROR
    for normal in [np.array([np.sin(low),-np.cos(low)]),np.array([-np.sin(high),np.cos(high)])]:
        poly=clip(poly, normal, normal@point)
    if len(poly) == 0:
        raise RuntimeError("Empty feasible polygon under bounded-noise synthetic model")
    return poly


def stations(spacing):
    m=math.ceil(1800/spacing)
    values=np.arange(-m,m+1)*spacing
    points=np.array([(x,y) for y in values for x in values],float)
    # Deterministic nearest-neighbor order, starting at the origin.
    order=[]; current=np.zeros(2)
    while len(points):
        j=np.argmin(np.sum((points-current)**2,axis=1))
        current=points[j]; order.append(current)
        points=np.delete(points,j,axis=0)
    return np.array(order)


def coverage_probe():
    rng=np.random.default_rng(SEED)
    r=1800*np.sqrt(rng.random(20000)); theta=rng.random(20000)*2*np.pi
    points=np.column_stack([r*np.cos(theta),r*np.sin(theta)])
    orient=rng.random(len(points))*2*np.pi
    edge_angle=np.arange(720)*2*np.pi/720
    edge=1800*np.column_stack([np.cos(edge_angle),np.sin(edge_angle)])
    rows=[]
    for h in [650,500]:
        full=stations(h)
        inner=full[np.linalg.norm(full,axis=1) < 1800-1e-8]
        for name, grid in [("with_exterior",full),("strict_interior_only",inner)]:
            for case, locations, angles in [("uniform_random",points,orient),("outward_boundary",edge,edge_angle)]:
                offsets=grid[None,:,:]-locations[:,None,:]
                distance=np.linalg.norm(offsets,axis=2)
                directions=np.column_stack([np.cos(angles),np.sin(angles)])
                side=np.einsum("ijk,ik->ij",offsets,directions)
                detectable=(distance<=1000+1e-7)&(side>=-1e-7)
                rows.append({"spacing_m":h,"grid_type":name,"stations":len(grid),
                             "case":case,"sources":len(locations),
                             "discovered":int(detectable.any(axis=1).sum()),
                             "discovery_rate":float(detectable.any(axis=1).mean())})
                if name=="with_exterior":
                    assert detectable.any(axis=1).all()
    pd.DataFrame(rows).to_csv(OUT/"b_coverage.csv", index=False)
    return rows


def triangulation_probe():
    rng=np.random.default_rng(SEED+1)
    rows=[]
    for angle in [5,15,30,60,90,120,150,165,175]:
        half=math.radians(angle/2)
        p1=1000*np.array([-np.cos(half),-np.sin(half)])
        p2=1000*np.array([-np.cos(half),np.sin(half)])
        error=rng.uniform(-1,1,(10000,2))*np.pi/180
        b1=half+error[:,0]; b2=-half+error[:,1]
        v1=np.column_stack([np.cos(b1),np.sin(b1)])
        v2=np.column_stack([np.cos(b2),np.sin(b2)])
        t=cross(p2-p1,v2)/cross(v1,v2)
        estimate=p1+t[:,None]*v1
        distances=np.linalg.norm(estimate,axis=1)
        rows.append({"intersection_angle_deg":angle,"range_each_m":1000,"trials":len(error),
                     "median_error_m":float(np.median(distances)),
                     "p95_error_m":float(np.quantile(distances,.95)),
                     "max_sample_error_m":float(distances.max()),
                     "within_20m_fraction":float((distances<=20).mean())})
    pd.DataFrame(rows).to_csv(OUT/"b_bearing_geometry.csv",index=False)
    return rows


class SyntheticEnvironment:
    """Policy sees only measure/clear responses; truth is retained for scoring."""
    def __init__(self, seed, mixed, adversarial=False):
        rng=np.random.default_rng(seed)
        n=int(rng.integers(10,17)); channels=rng.choice(np.arange(1,21),n,replace=False)
        radii=1800*np.sqrt(rng.random(n)); theta=rng.random(n)*2*np.pi
        if adversarial:
            radii[:n//2]=1800
        points=np.column_stack([radii*np.cos(theta),radii*np.sin(theta)])
        facing=rng.random(n)*2*np.pi
        directed=rng.random(n)<.5 if mixed else np.zeros(n,bool)
        if adversarial and mixed:
            directed[:n//2]=True; facing[:n//2]=theta[:n//2]
        receptions=rng.uniform(1000,1500,n)
        if adversarial:
            receptions[:n//2]=1000
        self._sources={int(ch):{"point":p,"radius":r,"directed":bool(d),
                               "facing":np.array([np.cos(a),np.sin(a)])}
                       for ch,p,r,d,a in zip(channels,points,receptions,directed,facing)}
        self._seed=seed
        self.position=np.zeros(2); self.channel=1
        self.virtual_s=0.; self.move_m=0.; self.measurements=0; self.clear_calls=0
        self.cleared=set(); self.switches=0

    def _move(self, point):
        length=float(np.linalg.norm(point-self.position))
        self.move_m+=length; self.virtual_s+=length/5; self.position=point.copy()

    def measure(self, point, channel):
        self._move(point)
        if self.channel!=channel:
            self.virtual_s+=1; self.switches+=1
        self.channel=channel; self.virtual_s+=5; self.measurements+=1
        source=self._sources.get(channel)
        if source is None or channel in self.cleared:
            return {"result":"no_signal"}
        offset=point-source["point"]; distance=np.linalg.norm(offset)
        if distance>source["radius"] or (source["directed"] and offset@source["facing"] < -1e-8):
            return {"result":"no_signal"}
        if distance<=5:
            return {"result":"near"}
        bearing=math.degrees(math.atan2(-offset[1],-offset[0]))
        # Fixed at the same location/channel, independent of repeated measurements.
        text=f"{self._seed}:{channel}:{float(point[0]).hex()}:{float(point[1]).hex()}"
        digest=hashlib.blake2b(text.encode(),digest_size=8).digest()
        noise=2*int.from_bytes(digest,"big")/(2**64-1)-1
        return {"result":"direction","angle":round((bearing+noise)%360,2)%360}

    def clear(self, point, channel):
        self._move(point); self.clear_calls+=1; self.virtual_s+=3
        source=self._sources.get(channel)
        if source is not None and channel not in self.cleared and np.linalg.norm(point-source["point"])<=20+1e-8:
            self.cleared.add(channel); self.virtual_s+=2
            return True
        return False

    def score(self):
        return {"sources":len(self._sources),"cleared":len(self.cleared),
                "clear_fraction":len(self.cleared)/len(self._sources),
                "average_virtual_s_per_clear":self.virtual_s/max(len(self.cleared),1),
                "total_virtual_s":self.virtual_s,"move_m":self.move_m,
                "measurements":self.measurements,"clear_calls":self.clear_calls,
                "switches":self.switches}


def policy(environment, grid):
    regions={}; cleared=set(); fallback_calls=0; certified_clears=0
    for point in grid:
        for channel in range(1,21):
            if channel in cleared:
                continue
            response=environment.measure(point,channel)
            if response["result"]=="near":
                assert environment.clear(point,channel)
                cleared.add(channel); continue
            if response["result"]!="direction":
                continue
            poly=update_region(regions.get(channel),point,response["angle"],channel not in regions)
            regions[channel]=poly
            center=poly.mean(axis=0)
            if np.linalg.norm(poly-center,axis=1).max() <= 20-1e-7:
                assert environment.clear(center,channel)
                certified_clears+=1; cleared.add(channel)
    # All possible channels have now been surveyed on a provably sufficient grid.
    remaining=set(regions)-cleared
    while remaining:
        channel=min(remaining,key=lambda ch:np.linalg.norm(regions[ch].mean(axis=0)-environment.position))
        poly=regions[channel]; center=poly.mean(axis=0)
        if environment.clear(center,channel):
            cleared.add(channel); remaining.remove(channel); continue
        # Optical actions work from either side of a directional source.
        # Cover the posterior bounding rectangle at spacing 20 m (radius <= sqrt(2)*20/2).
        low=poly.min(axis=0); high=poly.max(axis=0)
        x=np.arange(low[0],high[0]+20,20); y=np.arange(low[1],high[1]+20,20)
        candidates=np.array([(a,b) for a in x for b in y])
        order=np.argsort(np.linalg.norm(candidates-center,axis=1))
        success=False
        for i in order:
            fallback_calls+=1
            if environment.clear(candidates[i],channel):
                success=True; break
        if not success:
            raise AssertionError("Optical covering fallback failed")
        cleared.add(channel); remaining.remove(channel)
    return {"posterior_certified_clears":certified_clears,"fallback_clear_calls":fallback_calls,
            "channels_discovered":len(set(regions)|cleared)}


def main():
    start=time.perf_counter()
    record_environment("b",[DATA/"B题/B题.pdf",DATA/"B题/附件/附件1.docx",DATA/"B题/附件/附件2.docx"])
    log("B","Synthetic rule-based simulator only; no official tests, accounts, or requests.")
    coverage=coverage_probe(); geometry=triangulation_probe(); rows=[]
    for h in [650,500]:
        grid=stations(h)
        for mixed in [False,True]:
            for trial in range(30):
                adversarial=trial>=20
                env=SyntheticEnvironment(SEED+trial,mixed,adversarial)
                t0=time.perf_counter(); extra=policy(env,grid); score=env.score()
                assert score["cleared"]==score["sources"]
                rows.append({"spacing_m":h,"mixed_directional":mixed,"case_seed":SEED+trial,
                             "boundary_stress":adversarial,"policy_wall_s":time.perf_counter()-t0,
                             **score,**extra})
            log("B",f"Grid {h}m; mixed={mixed}; finished 30 cases, including 10 outward-boundary cases.")
    frame=pd.DataFrame(rows); frame.to_csv(OUT/"b_synthetic_trials.csv",index=False)
    summary=frame.groupby(["spacing_m","mixed_directional"]).agg(
        cases=("case_seed","count"), min_clear_fraction=("clear_fraction","min"),
        mean_average_virtual_s=("average_virtual_s_per_clear","mean"),
        max_total_virtual_s=("total_virtual_s","max"),
        mean_measurements=("measurements","mean"),
        median_policy_wall_s=("policy_wall_s","median"),
        max_fallback_clear_calls=("fallback_clear_calls","max"))
    summary.to_csv(OUT/"b_synthetic_summary.csv")
    results={"coverage":coverage,"bearing_geometry":geometry,"synthetic_summary":summary.reset_index().to_dict("records"),
             "wall_s":time.perf_counter()-start,
             "coverage_proof":"For any source in a square cell of side h, all four vertices are <=sqrt(2)h away. Because the source belongs to their convex hull, every closed half-plane through the source contains at least one vertex. h<=1000/sqrt(2) therefore guarantees reception even for unknown 180-degree orientation, provided exterior vertices are retained.",
             "limitations":["Synthetic location/range/orientation distribution and noise field differ from unknown official generator.",
                            "No HTTP, network, login, encrypted logging or real 20-minute deadline tested.",
                            "Coverage grid and posterior optical fallback are conservative; not optimized virtual time.",
                            "Perfect synthetic completion is not evidence of official competitive ranking."]}
    save_json("b_results.json",results)
    log("B",summary.to_string())
    log("B",f"Finished in {results['wall_s']:.2f}s.")


if __name__=="__main__":
    main()
