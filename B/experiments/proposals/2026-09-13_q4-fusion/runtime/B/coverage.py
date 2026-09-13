"""Square/triangle coverage layouts and open-path route optimization.

Q4 cell sufficiency requires sqrt(2)*h <= 1000 or triangle side <= 1000;
parameterized generation alone is not a coverage certificate.
"""
import math
import numpy as np
from geometry import cross


def segment_distance_origin(a, b):
    ab = b-a
    if ab@ab == 0:
        return float(np.linalg.norm(a))
    return float(np.linalg.norm(a+np.clip(-a@ab/(ab@ab), 0., 1.)*ab))


def triangle_intersects_disk(triangle, radius):
    t = np.asarray(triangle)
    signs = cross(np.roll(t,-1,axis=0)-t, -t)
    # A zero-area triangle has only edges: same-side signs do not imply interior.
    # Do not collapse thin but nonzero-area triangles with an area tolerance.
    if cross(t[1]-t[0], t[2]-t[0]) != 0 and (np.all(signs >= -1e-9) or np.all(signs <= 1e-9)):
        return True
    return min(segment_distance_origin(t[i-1],t[i]) for i in range(3)) <= radius+1e-8


def square_stations(h=650., cropped=False, radius=1800.):
    m = math.ceil(radius/h)
    if not cropped:
        return np.array([(i*h,j*h) for j in range(-m,m+1) for i in range(-m,m+1)])
    # Retain every vertex of intersecting cells, including stations outside the source disk.
    # Projecting/deleting those vertices would invalidate the cell-coverage argument.
    selected = set()
    for j in range(-m,m):
        for i in range(-m,m):
            lo, hi = np.array([i,j])*h, np.array([i+1,j+1])*h
            if np.linalg.norm(np.maximum(lo, np.minimum(0., hi))) <= radius+1e-8:
                selected.update([(i,j),(i+1,j),(i,j+1),(i+1,j+1)])
    return np.array([(i*h,j*h) for i,j in sorted(selected)])


def triangle_stations(side=990., radius=1800.):
    basis = np.array([[side,0.],[side/2,side*math.sqrt(3)/2]])
    m = math.ceil(2*radius/side)+3
    # Retain every vertex of intersecting cells, including stations outside the source disk.
    # Projecting/deleting those vertices would invalidate the cell-coverage argument.
    selected = set()
    for i in range(-m,m+1):
        for j in range(-m,m+1):
            for ids in [[(i,j),(i+1,j),(i,j+1)],[(i+1,j),(i+1,j+1),(i,j+1)]]:
                t = np.array(ids) @ basis
                if triangle_intersects_disk(t, radius):
                    selected.update(ids)
    return np.array(sorted(tuple(np.array(ij)@basis) for ij in selected))


def route_length(points, start=(0.,0.)):
    if not len(points):
        return 0.
    edges = np.diff(np.vstack([start,points]),axis=0)
    return float(np.linalg.norm(edges,axis=1).sum())


def route(points, optimized=True):
    remaining = np.asarray(points).copy()
    current = np.zeros(2)
    path = []
    while len(remaining):
        index = int(np.argmin(np.sum((remaining-current)**2,axis=1)))
        current = remaining[index]
        path.append(current)
        remaining = np.delete(remaining,index,axis=0)
    path = np.array(path)
    if not optimized:
        return path
    # Fixed origin, free terminal point; strict descent, deterministic tie handling.
    # CPU cap only; reaching 30 passes does not certify a 2-opt local optimum.
    for _ in range(30):
        changed = False
        for i in range(len(path)-1):
            a = np.zeros(2) if i==0 else path[i-1]
            for j in range(i+1,len(path)):
                old = np.linalg.norm(a-path[i])
                new = np.linalg.norm(a-path[j])
                if j+1 < len(path):
                    old += np.linalg.norm(path[j]-path[j+1])
                    new += np.linalg.norm(path[i]-path[j+1])
                if new < old-1e-7:
                    path[i:j+1] = path[i:j+1][::-1]
                    changed = True
        if not changed:
            break
    return path
