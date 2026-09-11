"""Continuous all-direction coverage by certified adaptive rectangle cells."""
import math
import numpy as np
from scipy.spatial import ConvexHull,QhullError


def directional_witness(points,g,receive_radius=1000.):
    """Return a real uncovered face at g, or None; NOT a full-domain test."""
    delta=np.asarray(points)-g;distance=np.linalg.norm(delta,axis=1)
    if np.any(distance<=1e-8):return None
    delta=delta[distance<=receive_radius+1e-7]
    if not len(delta):return {"position":np.asarray(g).tolist(),"direction_deg":0.,"reason":"no_station_in_range"}
    angles=np.sort(np.mod(np.arctan2(delta[:,1],delta[:,0]),2*math.pi))
    gaps=np.diff(np.r_[angles,angles[0]+2*math.pi]);i=int(gaps.argmax())
    if gaps[i]>math.pi+1e-7:
        return {"position":np.asarray(g).tolist(),"direction_deg":math.degrees((angles[i]+gaps[i]/2)%(2*math.pi)),"empty_angle_deg":math.degrees(gaps[i])}
    return None


def sample_reject(points,arena_radius=1800.):
    angles=np.arange(144)*2*math.pi/144
    for radius in np.linspace(0,arena_radius,37):
        for a in angles:
            witness=directional_witness(points,radius*np.array([math.cos(a),math.sin(a)]))
            if witness:return witness
    return None


def rectangle_certificate(points,arena_radius=1800.,receive_radius=1000.,max_depth=13,save_cells=True,max_cells=200000):
    """Finite continuous certificate. Numerical margins shrink allowable sets.

    Each leaf is a square [center-half,center+half]. Eligible stations have
    distance <= receive_radius from all four corners. If the whole square
    lies strictly inside their convex hull, every source in that square sees
    at least one of these eligible stations in every closed 180-degree face.
    Leaves whose minimum norm exceeds arena_radius do not meet the source disk.
    """
    p=np.asarray(points,float);stack=[(0.,0.,float(arena_radius),0)]
    cache={};cells=[];visited=0;deepest=0;min_range=math.inf;min_hull=math.inf
    while stack:
        x,y,h,depth=stack.pop();visited+=1;deepest=max(deepest,depth)
        c=np.array([x,y]);nearest=np.maximum(np.abs(c)-h,0.)
        if float(nearest@nearest)>arena_radius**2+1e-6:continue
        farthest=np.linalg.norm(np.abs(p-c)+h,axis=1)
        ids=tuple(np.flatnonzero(farthest<=receive_radius-1e-5).tolist())
        if ids not in cache:
            try:cache[ids]=ConvexHull(p[list(ids)]).equations if len(ids)>=3 else None
            except QhullError:cache[ids]=None
        equations=cache[ids]
        if equations is not None:
            margins=-(equations[:,:2]@c+equations[:,2]+h*np.abs(equations[:,:2]).sum(axis=1))
            if margins.min()>1e-5:
                min_hull=min(min_hull,float(margins.min()))
                min_range=min(min_range,float(receive_radius-farthest[list(ids)].max()))
                cells.append([x,y,h,list(ids)]);continue
        if depth>=max_depth or visited>=max_cells:
            return dict(covered=False,reason="unresolved_cell",cell=[x,y,h,depth],visited=visited,
                        witness=directional_witness(p,c) if np.linalg.norm(c)<=arena_radius else None)
        half=h/2
        stack.extend((x+dx*half,y+dy*half,half,depth+1) for dx in (-1,1) for dy in (-1,1))
    return dict(covered=True,arena_radius=arena_radius,receive_radius=receive_radius,
                leaf_count=len(cells),visited=visited,deepest=deepest,
                min_receiving_margin_m=min_range,min_convex_hull_margin_m=min_hull,
                cells=cells if save_cells else None,
                proof="source disk covered by disjoint certified squares; each square inside convex hull of uniformly receivable stations")


def verify_cells(points,certificate):
    """Independent vertex check for each exported square and its selected sites."""
    p=np.asarray(points,float);area=0.
    for x,y,h,ids in certificate["cells"]:
        corners=np.array([[x-h,y-h],[x+h,y-h],[x+h,y+h],[x-h,y+h]])
        stations=p[ids];assert np.linalg.norm(stations[:,None,:]-corners[None,:,:],axis=2).max()<certificate["receive_radius"]
        hull=ConvexHull(stations);values=corners@hull.equations[:,:2].T+hull.equations[:,-1]
        assert values.max()<1e-7
        area+=4*h*h
    return dict(verified_leaves=len(certificate["cells"]),certified_area_m2=area)
