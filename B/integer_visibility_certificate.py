"""Exact integer predicates for closed-hull coverage of integer stations."""
from itertools import combinations
import math
import numpy as np


def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def convex_vertices(points):
    ordered=sorted(set(tuple(map(int,p)) for p in points))
    if len(ordered)<3:
        return None
    lower=[]
    upper=[]
    for point in ordered:
        while len(lower)>=2 and cross(lower[-2],lower[-1],point)<=0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper)>=2 and cross(upper[-2],upper[-1],point)<=0:
            upper.pop()
        upper.append(point)
    hull=lower[:-1]+upper[:-1]
    return np.array(hull,dtype=np.int64) if len(hull)>=3 else None


def _integer_points(points):
    raw = np.asarray(points, dtype=float)
    if (raw.ndim != 2 or raw.shape[1] != 2 or not len(raw)
            or not np.isfinite(raw).all() or not np.array_equal(raw, np.round(raw))
            or np.max(np.abs(raw)) > 1950):
        raise ValueError("stations must be a nonempty finite integer Nx2 array with |coordinate|<=1950")
    return raw


def certify_integer_stations(points,arena_radius=1800,receive_radius=1000,max_depth=16,max_cells=150000):
    raw=_integer_points(points)
    if (isinstance(max_depth, (bool, np.bool_)) or not isinstance(max_depth, (int, np.integer))
            or not 0 <= max_depth <= 16):
        raise ValueError("max_depth must be an integer in [0,16]")
    if arena_radius != 1800 or receive_radius != 1000:
        raise ValueError("coverage requires arena_radius=1800 and receive_radius=1000")
    # 2**depth makes every root subdivision integral, including the last level.
    # |station|<=1950, |corner|<=1800, scale<=65536 bound the squared-distance
    # sum by 2*(3750*65536)**2 < 1.21e17. Hull support intermediates are bounded
    # by 2*3900*(3750+1800)*65536**2 < 1.86e17, safely below int64's 2**63-1.
    scale=2**int(max_depth)
    p=np.asarray(raw,dtype=np.int64)*scale
    arena=1800*scale
    arena2=arena*arena
    # Rational 10^-5 m inward distance margin; no floating-point norm decides eligibility.
    safe_radius_numerator=1000*100000-1
    # Floor the squared limit: integer comparison cannot admit an out-of-range station.
    limit=(safe_radius_numerator**2*scale**2)//100000**2
    stack=[(0,0,arena,0)]
    cache={}
    cells=[]
    visited=0
    while stack:
        x,y,h,depth=stack.pop()
        visited+=1
        nearx=max(abs(x)-h,0)
        neary=max(abs(y)-h,0)
        if nearx*nearx+neary*neary>arena2:
            continue
        center=np.array([x,y],dtype=np.int64)
        far=np.abs(p-center)+h
        ids=tuple(np.flatnonzero(np.sum(far*far,axis=1)<=limit).tolist())
        if ids not in cache:
            cache[ids]=convex_vertices(p[list(ids)]) if len(ids)>=3 else None
        hull=cache[ids]
        accepted=False
        if hull is not None:
            edges=np.roll(hull,-1,axis=0)-hull
            relative=center-hull
            # CCW edges put the interior on the left; subtract the square support.
            # Equality is allowed: the receiving face and convex hull are closed.
            lower=edges[:,0]*relative[:,1]-edges[:,1]*relative[:,0]-h*(abs(edges[:,0])+abs(edges[:,1]))
            accepted=bool(np.all(lower>=0))
        if accepted:
            cells.append([x/scale,y/scale,h/scale,list(ids)])
        elif depth>=max_depth or visited>=max_cells:
            return dict(covered=False,reason="unresolved_exact_cell",cell=[x/scale,y/scale,h/scale,depth],visited=visited)
        else:
            if h%2 != 0:
                raise ValueError("nonintegral quadtree subdivision")
            half=h//2
            stack.extend((x+dx*half,y+dy*half,half,depth+1) for dx in (-1,1) for dy in (-1,1))
    return dict(covered=True,arena_radius=arena_radius,receive_radius=receive_radius,scale=scale,
                leaf_count=len(cells),visited=visited,cells=cells,exact_integer_predicates=True,
                receiving_inward_margin_m=1e-5,closed_convex_hull=True,
                arithmetic_bound="All int64 products and sums are below 2e17 with |station|<=1950, A=1800, scale<=65536")


def verify_integer_certificate(points,certificate):
    """Independent corner-triangle containment, pair distances, and integer partition."""
    scale=certificate["scale"]
    if (isinstance(scale, (bool, np.bool_)) or not isinstance(scale, (int, np.integer))
            or not 1 <= scale <= 65536 or int(scale) & (int(scale)-1)):
        raise ValueError("scale must be a power of two in [1,65536]")
    scale = int(scale)
    if certificate.get("covered") is not True:
        raise ValueError("certificate is not marked covered")
    if certificate.get("arena_radius") != 1800 or certificate.get("receive_radius") != 1000:
        raise ValueError("coverage requires arena_radius=1800 and receive_radius=1000")
    raw = _integer_points(points)
    # Independent predicates use Python int (unbounded), not the generator's int64.
    p=[tuple(int(v)*scale for v in point) for point in raw]
    arena=1800*scale
    radius=1000*scale
    cells = certificate.get("cells")
    if cells is None or not len(cells):
        raise ValueError("missing nonempty leaf partition")
    # [-1800,1800]^2 is the fixed quadtree root; as in the floating verifier,
    # cells wholly outside the source disk may be omitted. No full-square claim.
    leaves=set()
    boundary_corners=0
    def det(a,b,c):
        ax,ay=a
        bx,by=b
        cx,cy=c
        return (bx-ax)*(cy-ay)-(by-ay)*(cx-ax)
    def triangle_contains(q,a,b,c):
        direction=det(a,b,c)
        if not direction:
            return False
        signs=(det(a,b,q),det(b,c,q),det(c,a,q))
        return min(signs)>=0 if direction>0 else max(signs)<=0
    for cell in cells:
        if len(cell) != 4:
            raise ValueError("malformed leaf: expected x, y, half-width, station ids")
        x,y,h,ids = cell
        if (not np.isfinite([x,y,h]).all() or h <= 0
                or abs(x)+h > 1800 or abs(y)+h > 1800):
            raise ValueError("leaf must be finite, positive and within the root square")
        # IDs are zero-based rows of the supplied points, never Python negative indices.
        if (not isinstance(ids, (list, tuple)) or len(ids) < 3
                or any(isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer))
                       or i < 0 or i >= len(p) for i in ids)):
            raise ValueError("leaf requires at least three valid station indices")
        values=[x*scale,y*scale,h*scale]
        if not all(v==int(v) for v in values):
            raise ValueError("leaf coordinates must be integral at certificate scale")
        xi,yi,hi=map(int,values)
        key=(xi,yi,hi)
        if key in leaves:
            raise ValueError("duplicate partition leaves")
        leaves.add(key)
        selected=[p[i] for i in ids]
        triples=list(combinations(selected,3))
        for q in ((xi-hi,yi-hi),(xi+hi,yi-hi),(xi+hi,yi+hi),(xi-hi,yi+hi)):
            # Recheck strict <1000 m, not the generator's rational 1e-5 m margin.
            if not all((q[0]-a[0])**2+(q[1]-a[1])**2<radius**2 for a in selected):
                raise ValueError("corner receiving distance must be strictly below 1000 m")
            if not any(triangle_contains(q,*triangle) for triangle in triples):
                raise ValueError("corner is outside the closed station hull")
            boundary_corners+=int(abs(q[0])==arena or abs(q[1])==arena)
    stack=[(0,0,arena)]
    seen=set()
    visited=0
    minimum=min(c[2] for c in leaves)
    while stack:
        x,y,h=stack.pop()
        visited+=1
        key=(x,y,h)
        if key in leaves:
            seen.add(key)
            continue
        dx=max(abs(x)-h,0)
        dy=max(abs(y)-h,0)
        if dx*dx+dy*dy>arena*arena:
            continue
        if h < minimum or h%2 != 0:
            raise ValueError(f"uncovered integer partition: {key}")
        half=h//2
        stack.extend((x+a*half,y+b*half,half) for a in (-1,1) for b in (-1,1))
    if seen != leaves:
        raise ValueError("partition contains overlapping or non-quadtree leaves")
    return dict(verified_leaves=len(leaves),partition_nodes=visited,boundary_corners=boundary_corners,
                independent_exact_corner_triangles=True,integer_partition=True)


def certify_integer_omni_stations(points, max_depth=16, max_cells=200000):
    """Q3 disk coverage; explicit full-root partition, including outside leaves.

    Q4 entry points above retain their convex-hull requirements unchanged.
    Every receiving leaf fits one 1000-1e-5 m disk. An outside leaf is omitted
    from the source domain only by an exact strictly-outside-disk predicate.
    """
    raw = _integer_points(points)
    if type(max_depth) is not int or not 0 <= max_depth <= 16:
        raise ValueError('max_depth must be an integer in [0,16]')
    scale = 2**max_depth
    p = raw.astype(np.int64)*scale
    arena = 1800*scale
    limit = ((1000*100000-1)**2*scale**2)//100000**2
    stack = [(0, 0, arena, 0)]
    cells = []
    visited = 0
    while stack:
        x, y, h, depth = stack.pop()
        visited += 1
        nx, ny = max(abs(x)-h, 0), max(abs(y)-h, 0)
        outside = nx*nx+ny*ny > arena*arena
        far = np.abs(p-[x,y])+h
        d2 = np.sum(far*far, axis=1)
        i = int(d2.argmin())
        if outside or d2[i] <= limit:
            cells.append([x/scale,y/scale,h/scale,[] if outside else [i]])
        elif depth >= max_depth or visited >= max_cells:
            return dict(covered=False, reason='unresolved_exact_omni_cell',
                        cell=[x/scale,y/scale,h/scale,depth],visited=visited)
        else:
            half = h//2
            stack.extend((x+a*half,y+b*half,half,depth+1)
                         for a in (-1,1) for b in (-1,1))
    return dict(covered=True, problem=3, arena_radius=1800, receive_radius=1000,
                scale=scale, cells=cells, leaf_count=len(cells), visited=visited,
                source_domain='disk', partition_domain='[-1800,1800]^2',
                receiving_inward_margin_m=1e-5, exact_integer_predicates=True)


def verify_integer_omni_certificate(points, certificate, *, route):
    """Independent Python-int corners and complete exact quadtree traversal."""
    raw = _integer_points(points)
    path = _integer_points(route)
    if set(map(tuple,raw)) != set(map(tuple,path)):
        raise ValueError('route differs from certified coordinate set')
    if (certificate.get('covered') is not True or certificate.get('problem') != 3
            or certificate.get('arena_radius') != 1800
            or certificate.get('receive_radius') != 1000
            or certificate.get('source_domain') != 'disk'
            or certificate.get('partition_domain') != '[-1800,1800]^2'):
        raise ValueError('invalid Q3 certificate context')
    scale = certificate.get('scale')
    if type(scale) is not int or not 1 <= scale <= 65536 or scale & (scale-1):
        raise ValueError('invalid integer scale')
    points_i = [(int(x)*scale,int(y)*scale) for x,y in raw]
    leaves = {}; ancestors = set(); outside_count = 0
    for cell in certificate.get('cells',[]):
        if len(cell) != 4:
            raise ValueError('malformed leaf')
        x,y,h,ids = cell
        if not np.isfinite([x,y,h]).all() or h <= 0:
            raise ValueError('invalid leaf coordinates')
        values = [v*scale for v in (x,y,h)]
        if any(v != int(v) for v in values):
            raise ValueError('nonintegral leaf')
        xi,yi,hi = map(int,values); key=(xi,yi,hi)
        if key in leaves:
            raise ValueError('duplicate leaf')
        if not isinstance(ids,list) or len(ids)>1:
            raise ValueError('invalid receiving station ids')
        if not ids:
            nx,ny = max(abs(xi)-hi,0),max(abs(yi)-hi,0)
            if nx*nx+ny*ny <= (1800*scale)**2:
                raise ValueError('outside leaf intersects source disk')
            outside_count += 1
        else:
            i=ids[0]
            if type(i) is not int or not 0 <= i < len(points_i):
                raise ValueError('invalid station index')
            px,py=points_i[i]
            for qx,qy in ((xi-hi,yi-hi),(xi+hi,yi-hi),(xi+hi,yi+hi),(xi-hi,yi+hi)):
                d2=(qx-px)**2+(qy-py)**2
                if d2*100000**2 > (1000*100000-1)**2*scale**2:
                    raise ValueError('corner violates original receiving inward margin')
        cx,cy,ch=0,0,1800*scale
        for _ in range(17):
            if (cx,cy,ch)==key:break
            if ch<=hi or ch%2:
                raise ValueError('off-tree leaf')
            ancestors.add((cx,cy,ch));ch//=2
            cx+=ch if xi>cx else -ch;cy+=ch if yi>cy else -ch
        else:raise ValueError('leaf exceeds depth 16')
        leaves[key]=ids
    stack=[(0,0,1800*scale)];seen=set();visited=0
    while stack:
        key=stack.pop();visited+=1
        if key in leaves:
            seen.add(key);continue
        if key not in ancestors:raise ValueError('incomplete root-square partition')
        x,y,h=key;half=h//2
        stack.extend((x+a*half,y+b*half,half) for a in (-1,1) for b in (-1,1))
    if seen!=set(leaves):raise ValueError('overlapping partition')
    return dict(verified_leaves=len(seen),outside_leaves=outside_count,
                partition_nodes=visited,full_root_partition=True,
                independent_python_integer_predicates=True,problem=3)
