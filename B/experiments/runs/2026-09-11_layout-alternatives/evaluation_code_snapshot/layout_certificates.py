"""Continuous coverage certificates for arbitrary Q3 layouts and Q4 meshes."""
import math
import numpy as np
from geometry import clip, disk_outer
from coverage import triangle_intersects_disk


def omni_certificate(points,arena_radius=1800.,receive_radius=1000.,sides=256):
    """Conservative finite certificate over an OUTER polygon of the source disk.

    Intersect each nearest-site Voronoi cell with the outer source polygon.
    Euclidean distance to that cell's site reaches its maximum at a vertex.
    Thus every point in the source disk is within the reported upper bound
    of a station. Numerical clipping expands cells by a tiny distance margin.
    """
    points=np.asarray(points,float);bound=0.;witness=None;cells=[]
    for i,p in enumerate(points):
        poly=disk_outer([0.,0.],arena_radius,sides)
        for j,q in enumerate(points):
            if j==i:continue
            poly=clip(poly,2*(q-p),float(q@q-p@p))
            if not len(poly):break
        if len(poly):
            d=np.linalg.norm(poly-p,axis=1);k=int(np.argmax(d))
            if d[k]>bound:bound=float(d[k]);witness={"site":i,"point":poly[k].tolist()}
        cells.append(len(poly))
    return {"problem":3,"covered":bound+1e-6<receive_radius,"radius_upper_m":bound+1e-6,
            "margin_lower_m":receive_radius-bound-1e-6,"outer_source_polygon_sides":sides,"witness":witness,"cell_vertices":cells}


def directional_mesh_certificate(points,arena_radius=1800.,receive_radius=1000.):
    """Sufficient Q4 certificate, not a necessary test of arbitrary station sets.

    A triangular mesh covers the source disk. Every vertex of each intersecting
    triangle is within receive_radius of every point in that triangle if its
    longest edge is <= receive_radius. At least one vertex lies in any closed
    halfplane through that point because the point is in their convex hull.
    """
    from scipy.spatial import Delaunay,ConvexHull
    points=np.asarray(points,float);hull=ConvexHull(points)
    inward_distances=-hull.equations[:,-1]/np.linalg.norm(hull.equations[:,:2],axis=1)
    inradius=float(inward_distances.min());triangulation=Delaunay(points)
    longest=0.;active=[]
    for ids in triangulation.simplices:
        triangle=points[ids]
        if not triangle_intersects_disk(triangle,arena_radius):continue
        length=float(np.linalg.norm(triangle[:,None,:]-triangle[None,:,:],axis=2).max())
        longest=max(longest,length);active.append(ids.tolist())
    return {"problem":4,"covered":inradius>arena_radius+1e-6 and longest<receive_radius-1e-6,
            "hull_inradius_m":inradius,"hull_margin_m":inradius-arena_radius,"maximum_relevant_edge_m":longest,
            "receiving_margin_m":receive_radius-longest,"triangles_intersecting_arena":active,
            "criterion":"sufficient triangle mesh certificate, not a necessary coverage condition"}


def polar_layers(layers,phase_deg=0.,include_origin=True):
    parts=[np.zeros((1,2))] if include_origin else []
    for n,radius in layers:
        angle=np.arange(n)*2*math.pi/n+math.radians(phase_deg)
        parts.append(radius*np.column_stack((np.cos(angle),np.sin(angle))))
    return np.vstack(parts)


def square9(spacing):
    return np.array([(i*spacing,j*spacing) for j in (-1,0,1) for i in (-1,0,1)],float)


def alternating9(cardinal_radius=1450.,diagonal_radius=850.):
    a=np.arange(8)*math.pi/4;r=np.where(np.arange(8)%2==0,cardinal_radius,diagonal_radius)
    return np.vstack((np.zeros(2),r[:,None]*np.column_stack((np.cos(a),np.sin(a)))))
