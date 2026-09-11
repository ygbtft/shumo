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
                        witness=directional_witness(p,c,receive_radius) if np.linalg.norm(c)<=arena_radius else None)
        half=h/2
        stack.extend((x+dx*half,y+dy*half,half,depth+1) for dx in (-1,1) for dy in (-1,1))
    return dict(covered=True,arena_radius=arena_radius,receive_radius=receive_radius,
                leaf_count=len(cells),visited=visited,deepest=deepest,
                min_receiving_margin_m=min_range,min_convex_hull_margin_m=min_hull,
                cells=cells if save_cells else None,
                proof="source disk covered by disjoint certified squares; each square inside convex hull of uniformly receivable stations")


def _point_array(points, label):
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 2 or not len(p) or not np.isfinite(p).all():
        raise ValueError(f"{label}: expected a nonempty finite Nx2 coordinate array")
    return p


def verify_cells(points, certificate):
    """Verify source-disk partition and strict leaf geometry, not a layout claim.

    Legacy certificates omit squares wholly outside the source disk. The shared
    quadtree check validates those omissions as well as disjointness. This alone
    does NOT certify a route/problem or coverage of the entire root square;
    use certify_layout_coverage for that stronger, context-bound guarantee.
    Invalid geometry/partitions raise ValueError, including under python -O.
    """
    # Import lazily: icra_final_checks itself imports this module.
    from icra_final_checks import partition_check

    p = _point_array(points, "points")
    if certificate.get("covered") is not True:
        raise ValueError("certificate is not marked covered")
    if certificate.get("arena_radius") != 1800. or certificate.get("receive_radius") != 1000.:
        raise ValueError("coverage requires arena_radius=1800 and receive_radius=1000")
    cells = certificate.get("cells")
    if cells is None or not len(cells):
        raise ValueError("missing nonempty leaf partition")
    for cell in cells:
        if len(cell) != 4:
            raise ValueError("malformed leaf: expected x, y, half-width, station ids")
        x, y, h, ids = cell
        if not np.isfinite([x, y, h]).all() or h <= 0:
            raise ValueError("leaf coordinates must be finite with positive half-width")
        if (not isinstance(ids, (list, tuple)) or len(ids) < 3
                or any(isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer))
                       or i < 0 or i >= len(p) for i in ids)):
            raise ValueError("leaf requires at least three valid station indices")
    partition_check(certificate)
    area = 0.
    for index, (x, y, h, ids) in enumerate(cells):
        corners = np.array([[x-h, y-h], [x+h, y-h], [x+h, y+h], [x-h, y+h]])
        # A tuple denotes row IDs, not NumPy multi-axis indexing.
        stations = p[list(ids)]
        distances = np.linalg.norm(stations[:, None, :]-corners[None, :, :], axis=2)
        if not distances.max() <= 1000.-1e-5:
            raise ValueError(f"leaf {index}: receiving distance violates 1e-5 m inward margin")
        try:
            hull = ConvexHull(stations)
        except QhullError as exc:
            raise ValueError(f"leaf {index}: stations have no two-dimensional convex hull") from exc
        values = corners@hull.equations[:, :2].T+hull.equations[:, -1]
        if not values.max() < -1e-5:
            raise ValueError(f"leaf {index}: square is not strictly inside hull by 1e-5 m")
        area += 4*h*h
    return dict(verified_leaves=len(cells), certified_area_m2=area,
                coverage_guarantee=False,
                missing_requirements=["explicit layout coordinates, route and problem type",
                                      "full root-square partition (source-disk partition only checked)"])


def certify_layout_coverage(points, certificate, *, layout_points=None, route=None,
                            problem=None, layout_problem=None):
    """Certify the entire [-1800,1800]^2 for an explicitly bound Q4 layout.

    points retains certificate index order; layout_points and route may permute
    it. Exact coordinate-set equality follows cover21_geometry_audit's existing
    route check (no rounding/allclose). The Q4 restriction follows the directional
    certificate's scope. Missing context fails closed; historical disk-only
    certificates must not be advertised as full-square certificates.
    """
    missing = [name for name, value in (("layout_points", layout_points),
               ("route", route), ("problem", problem), ("layout_problem", layout_problem))
               if value is None]
    if missing:
        raise ValueError("missing coverage prerequisites: " + ", ".join(missing))
    if problem != 4 or layout_problem != problem:
        raise ValueError("problem type must match the Q4 layout")
    p = _point_array(points, "points")
    layout = _point_array(layout_points, "layout_points")
    path = _point_array(route, "route")
    if set(map(tuple, p)) != set(map(tuple, layout)):
        raise ValueError("layout coordinate set differs from verified points")
    if set(map(tuple, p)) != set(map(tuple, path)):
        raise ValueError("route coordinate set differs from verified points")
    result = verify_cells(p, certificate)
    # Shared quadtree verification already proves these are disjoint dyadic
    # root descendants. Their exact binary-rational areas must fill the root;
    # Fraction avoids a summation tolerance hiding a small missing square.
    from fractions import Fraction
    area = sum((4*Fraction(float(c[2]))**2 for c in certificate["cells"]), Fraction())
    if area != 3600**2:
        raise ValueError("incomplete root-square partition: disk-only coverage is insufficient")
    return {**result, "coverage_guarantee": True, "missing_requirements": [],
            "problem": problem, "domain": "[-1800,1800]^2"}
