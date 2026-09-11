"""Genetic open-route optimization and bounded-feedback active sensing."""
import math
import time
import numpy as np
from coverage import route, route_length
from geometry import bearing_clip, minimum_circle


def genetic_route(points, seed=42, population=96, generations=180):
    """Elitist order-crossover GA, inversion mutation and local 2-opt polishing."""
    began=time.perf_counter()
    p=np.asarray(points)
    rng=np.random.default_rng(seed)
    n=len(p)
    distances=np.linalg.norm(p[:,None]-p[None,:],axis=2)
    origins=np.linalg.norm(p,axis=1)
    initial=route(p,optimized=True)
    initial_ids=np.array([np.argmin(np.linalg.norm(p-x,axis=1)) for x in initial])
    def length(ids):
        return origins[ids[:,0]]+distances[ids[:,:-1],ids[:,1:]].sum(axis=1)
    def polish(order):
        q=order.copy()
        for _ in range(3):
            changed=False
            for i in range(n-1):
                for j in range(i+1,n):
                    old=origins[q[i]] if i==0 else distances[q[i-1],q[i]]
                    new=origins[q[j]] if i==0 else distances[q[i-1],q[j]]
                    if j+1<n:
                        old+=distances[q[j],q[j+1]]
                        new+=distances[q[i],q[j+1]]
                    if new<old-1e-8:
                        q[i:j+1]=q[i:j+1][::-1]
                        changed=True
            if not changed:
                break
        return q
    members=[initial_ids]
    for k in range(population-1):
        child=initial_ids.copy() if k<population//2 else rng.permutation(n)
        a,b=sorted(rng.choice(n,2,replace=False))
        child[a:b+1]=child[a:b+1][::-1]
        members.append(child)
    members=np.array(members)
    history=[]
    for generation in range(generations):
        fit=length(members)
        order=np.argsort(fit,kind="stable")
        members=members[order]
        history.append({"generation":generation,"best_m":float(fit[order[0]])})
        new=[x.copy() for x in members[:8]]
        while len(new)<population:
            parents=[members[min(rng.integers(0,population,3))] for _ in range(2)]
            a,b=sorted(rng.choice(n,2,replace=False))
            child=np.full(n,-1,int)
            child[a:b+1]=parents[0][a:b+1]
            used=set(child[a:b+1])
            slots=list(range(b+1,n))+list(range(a))
            values=[v for v in np.roll(parents[1],-b-1) if v not in used]
            child[slots]=values
            if rng.random()<.35:
                i,j=sorted(rng.choice(n,2,replace=False))
                child[i:j+1]=child[i:j+1][::-1]
            new.append(child)
        members=np.array(new)
        if generation%10==0:
            ranked=np.argsort(length(members))[:4]
            for index in ranked:
                members[index]=polish(members[index])
    best=members[int(np.argmin(length(members)))]
    best=polish(best)
    assert np.array_equal(np.sort(best),np.arange(n))
    result=p[best]
    assert route_length(result)<=route_length(initial)+1e-6
    return result,{"seed":seed,"population":population,"generations":generations,
                   "wall_s":time.perf_counter()-began,"initial_2opt_m":route_length(initial),
                   "best_m":route_length(result),"history":history}


def guaranteed_omni(q, poly, first_point):
    """Two sufficient certificates; never infer radius from a non-reception."""
    q,first_point=np.asarray(q),np.asarray(first_point)
    radius1000=float(np.linalg.norm(poly-q,axis=1).max())<=1000.-1e-6
    dominance=float(np.max(q@q-first_point@first_point-2*poly@(q-first_point)))<=-1e-6
    return radius1000 or dominance


def candidate_points(poly, observations, current):
    center,_=minimum_circle(poly)
    first,angle=observations[0]
    angle=math.radians(angle)
    u=np.array([math.cos(angle),math.sin(angle)])
    v=np.array([-u[1],u[0]])
    extent=float(np.linalg.norm(poly-center,axis=1).max())
    width=np.clip(extent*.3,25.,250.)
    result=[]
    for t in [.65,1.]:
        mid=np.asarray(first)+t*(center-np.asarray(first))
        for b in [-width,-width/3,0.,width/3,width]:
            result.append(mid+b*v)
    for b in [-60.,60.,-150.,150.]:
        result.append(center+b*u)
    return np.array([q for q in result if np.linalg.norm(q-current)>1. and
                     all(np.linalg.norm(q-p)>1. for p,a in observations)])


def hypotheses(poly, limit=8):
    c=poly.mean(axis=0)
    ids=np.linspace(0,len(poly)-1,min(limit,len(poly)),dtype=int)
    # Both extremes and interior hypotheses are retained, without sampling hidden truth.
    return np.vstack([poly[ids], c, (poly[ids]+c)/2])


def reception_probability(q, g, observations, mixed):
    lower=max(1000.,max(np.linalg.norm(g-p) for p,a in observations))
    dq=float(np.linalg.norm(g-q))
    prob=float(np.clip((1500.-dq)/max(1e-9,1500.-lower),0.,1.)) if dq>lower else 1.
    if not mixed:
        return prob
    angles=np.arange(48)*2*math.pi/48
    faces=np.column_stack([np.cos(angles),np.sin(angles)])
    admissible=np.ones(len(faces),bool)
    for p,a in observations:
        admissible &= (faces@(np.asarray(p)-g)>=-1e-8)
    if not admissible.any():
        return prob*.5
    return prob*float(np.mean(faces[admissible]@(q-g)>=-1e-8))


def choose_second(poly, observations, current, mixed=False, time_weight=.08, candidates=None):
    """Finite-hypothesis robust-error lookahead, with a conditional reception prior.

    This score is a heuristic, not a Bayesian posterior or a worst-case proof.
    For Q2 all candidates must pass a universal omni reception certificate.
    """
    current=np.asarray(current)
    center,r0=minimum_circle(poly)
    samples=hypotheses(poly)
    candidates=candidate_points(poly,observations,current) if candidates is None else candidates
    rows=[]
    for q in candidates:
        certificate=guaranteed_omni(q,poly,observations[0][0])
        if not mixed and not certificate:
            continue
        residuals=[]
        probabilities=[]
        for g in samples:
            prob=1. if certificate and not mixed else reception_probability(q,g,observations,mixed)
            probabilities.append(prob)
            if np.linalg.norm(g-q)<=5.:
                residuals.append((1-prob)*r0)
                continue
            theta=math.degrees(math.atan2(g[1]-q[1],g[0]-q[0]))
            worst=0.
            for error in (-1.01,0.,1.01):
                post=bearing_clip(poly,q,theta+error)
                if not len(post):
                    worst=r0
                    break
                c=post.mean(axis=0)
                worst=max(worst,float(np.linalg.norm(post-c,axis=1).max()))
            residuals.append(prob*min(worst,r0)+(1-prob)*r0)
        travel=float(np.linalg.norm(q-current))/5+5
        expected=float(np.mean(residuals))
        rows.append({"x":float(q[0]),"y":float(q[1]),"guaranteed_omni":certificate,
                     "mean_reception_prior":float(np.mean(probabilities)),"predicted_radius_m":expected,
                     "max_hypothesis_radius_m":float(max(residuals)),"move_measure_s":travel,
                     "score":expected+time_weight*travel})
    if not rows:
        return center,rows
    best=min(rows,key=lambda row:row["score"])
    return np.array([best["x"],best["y"]]),rows
