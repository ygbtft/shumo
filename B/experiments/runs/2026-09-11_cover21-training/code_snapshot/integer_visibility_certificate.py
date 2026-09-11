"""Exact integer predicates for closed-hull coverage of integer stations."""
from itertools import combinations
import math
import numpy as np


def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def convex_vertices(points):
    ordered=sorted(set(tuple(map(int,p)) for p in points))
    if len(ordered)<3:return None
    lower=[];upper=[]
    for point in ordered:
        while len(lower)>=2 and cross(lower[-2],lower[-1],point)<=0:lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper)>=2 and cross(upper[-2],upper[-1],point)<=0:upper.pop()
        upper.append(point)
    hull=lower[:-1]+upper[:-1]
    return np.array(hull,dtype=np.int64) if len(hull)>=3 else None


def certify_integer_stations(points,arena_radius=1800,receive_radius=1000,max_depth=16,max_cells=150000):
    raw=np.asarray(points)
    assert np.array_equal(raw,np.round(raw))
    assert max_depth<=16 and np.max(abs(raw))<=1950 and arena_radius==1800 and receive_radius==1000
    scale=2**max_depth;p=np.asarray(raw,dtype=np.int64)*scale
    arena=arena_radius*scale;arena2=arena*arena
    # Rational 10^-5 m inward distance margin; no floating-point norm decides eligibility.
    safe_radius_numerator=receive_radius*100000-1
    limit=(safe_radius_numerator**2*scale**2)//100000**2
    stack=[(0,0,arena,0)];cache={};cells=[];visited=0
    while stack:
        x,y,h,depth=stack.pop();visited+=1
        nearx=max(abs(x)-h,0);neary=max(abs(y)-h,0)
        if nearx*nearx+neary*neary>arena2:continue
        center=np.array([x,y],dtype=np.int64)
        far=np.abs(p-center)+h
        ids=tuple(np.flatnonzero(np.sum(far*far,axis=1)<=limit).tolist())
        if ids not in cache:cache[ids]=convex_vertices(p[list(ids)]) if len(ids)>=3 else None
        hull=cache[ids]
        accepted=False
        if hull is not None:
            edges=np.roll(hull,-1,axis=0)-hull
            relative=center-hull
            lower=edges[:,0]*relative[:,1]-edges[:,1]*relative[:,0]-h*(abs(edges[:,0])+abs(edges[:,1]))
            accepted=bool(np.all(lower>=0))
        if accepted:
            cells.append([x/scale,y/scale,h/scale,list(ids)])
        elif depth>=max_depth or visited>=max_cells:
            return dict(covered=False,reason="unresolved_exact_cell",cell=[x/scale,y/scale,h/scale,depth],visited=visited)
        else:
            assert h%2==0
            half=h//2
            stack.extend((x+dx*half,y+dy*half,half,depth+1) for dx in (-1,1) for dy in (-1,1))
    return dict(covered=True,arena_radius=arena_radius,receive_radius=receive_radius,scale=scale,
                leaf_count=len(cells),visited=visited,cells=cells,exact_integer_predicates=True,
                receiving_inward_margin_m=1e-5,closed_convex_hull=True,
                arithmetic_bound="All int64 products and sums are below 2e17 with |station|<=1950, A=1800, scale<=65536")


def verify_integer_certificate(points,certificate):
    """Independent corner-triangle containment, pair distances, and integer partition."""
    scale=certificate["scale"]
    assert scale<=65536 and certificate["covered"]
    p=[tuple(int(v)*scale for v in point) for point in points]
    assert all(tuple(v/scale for v in q)==tuple(map(float,raw)) for q,raw in zip(p,points))
    arena=certificate["arena_radius"]*scale;radius=certificate["receive_radius"]*scale
    leaves={};boundary_corners=0
    def det(a,b,c):
        ax,ay=a;bx,by=b;cx,cy=c
        return (bx-ax)*(cy-ay)-(by-ay)*(cx-ax)
    def triangle_contains(q,a,b,c):
        direction=det(a,b,c)
        if not direction:return False
        signs=(det(a,b,q),det(b,c,q),det(c,a,q))
        return min(signs)>=0 if direction>0 else max(signs)<=0
    for x,y,h,ids in certificate["cells"]:
        values=[x*scale,y*scale,h*scale]
        assert all(v==int(v) for v in values)
        xi,yi,hi=map(int,values);key=(xi,yi,hi)
        assert key not in leaves;leaves[key]=True
        selected=[p[i] for i in ids]
        triples=list(combinations(selected,3))
        for q in ((xi-hi,yi-hi),(xi+hi,yi-hi),(xi+hi,yi+hi),(xi-hi,yi+hi)):
            assert all((q[0]-a[0])**2+(q[1]-a[1])**2<radius**2 for a in selected)
            assert any(triangle_contains(q,*triangle) for triangle in triples)
            boundary_corners+=int(abs(q[0])==arena or abs(q[1])==arena)
    stack=[(0,0,arena)];seen=set();visited=0;minimum=min(c[2] for c in leaves)
    while stack:
        x,y,h=stack.pop();visited+=1;key=(x,y,h)
        if key in leaves:seen.add(key);continue
        dx=max(abs(x)-h,0);dy=max(abs(y)-h,0)
        if dx*dx+dy*dy>arena*arena:continue
        assert h>=minimum and h%2==0,(key,"uncovered integer partition")
        half=h//2
        stack.extend((x+a*half,y+b*half,half) for a in (-1,1) for b in (-1,1))
    assert seen==set(leaves)
    return dict(verified_leaves=len(leaves),partition_nodes=visited,boundary_corners=boundary_corners,
                independent_exact_corner_triangles=True,integer_partition=True)
