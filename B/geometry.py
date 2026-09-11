"""Bounded-bearing geometry. No scenario truth and no network dependencies."""
import itertools
import math
import numpy as np

ANGLE_BOUND_DEG = 1.01  # also encloses truncation; nearest rounding only needs 1.005.
TOL = 1e-8


def cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def hull(points):
    pts = sorted(set(map(tuple, np.asarray(points, float).reshape(-1, 2))))
    if len(pts) < 3:
        return np.array(pts, float).reshape(-1, 2)
    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and cross(np.subtract(out[-1], out[-2]), np.subtract(p, out[-1])) <= 0:
                out.pop()
            out.append(p)
        return out
    return np.asarray(half(pts)[:-1] + half(pts[::-1])[:-1])


def clip(poly, normal, bound):
    """Closed halfplane clipping, retaining point/segment degeneracies."""
    poly = np.asarray(poly, float).reshape(-1, 2)
    if not len(poly):
        return poly
    n = np.asarray(normal, float)
    values = poly @ n - bound
    # Shift outward by a small distance, never discard a feasible boundary point.
    values -= TOL * max(1., float(np.linalg.norm(n)))
    out = []
    for i in range(len(poly)):
        a, b = poly[i-1], poly[i]
        fa, fb = values[i-1], values[i]
        if (fa <= 0) != (fb <= 0):
            out.append(a + (b-a) * (fa/(fa-fb)))
        if fb <= 0:
            out.append(b)
    return np.asarray(out, float).reshape(-1, 2)


def bearing_planes(position, angle_deg, error_deg=ANGLE_BOUND_DEG):
    if not 0 <= error_deg < 90:
        raise ValueError("This implementation requires 0 <= angular error < 90 degrees")
    p = np.asarray(position, float)
    t, e = math.radians(angle_deg % 360), math.radians(error_deg)
    normals = np.array([[math.sin(t-e), -math.cos(t-e)],
                        [-math.sin(t+e), math.cos(t+e)],
                        [-math.cos(t), -math.sin(t)]])
    return normals, normals @ p


def bearing_clip(poly, position, angle_deg, error_deg=ANGLE_BOUND_DEG):
    normals, bounds = bearing_planes(position, angle_deg, error_deg)
    for n, b in zip(normals[:2 if error_deg else 3], bounds):
        poly = clip(poly, n, b)
    return poly


def disk_outer(center, radius, sides=64):
    theta = (np.arange(sides)+.5) * 2*math.pi/sides
    return np.asarray(center) + radius/math.cos(math.pi/sides)*np.column_stack([np.cos(theta), np.sin(theta)])


NORMALS = np.column_stack([np.cos(np.arange(64)*2*math.pi/64), np.sin(np.arange(64)*2*math.pi/64)])


def update_region(poly, position, angle_deg, error_deg=ANGLE_BOUND_DEG):
    if poly is None:
        poly = disk_outer([0., 0.], 1800.)
    poly = bearing_clip(poly, position, angle_deg, error_deg)
    for n in NORMALS:
        poly = clip(poly, n, float(n @ position) + 1500.)
        if not len(poly):
            raise ValueError("Inconsistent bearings: retain earlier conservative region; investigate feedback")
    return poly


def polygon_area(poly):
    if len(poly) < 3:
        return 0.
    return .5 * abs(float(np.sum(cross(poly, np.roll(poly, -1, axis=0)))))


def diameter(poly):
    """Exact vertex-pair diameter, O(v^2), also valid for a segment/point."""
    p = np.asarray(poly)
    if not len(p):
        return None, None
    d2 = np.sum((p[:, None] - p[None, :])**2, axis=2)
    i, j = np.unravel_index(np.argmax(d2), d2.shape)
    return math.sqrt(float(d2[i, j])), (p[i].copy(), p[j].copy())


def circumcircle(a, b, c):
    ab, ac = b-a, c-a
    det = 2*float(cross(ab, ac))
    if abs(det) < 1e-13 * max(1., np.linalg.norm(ab)*np.linalg.norm(ac)):
        pts = np.array([a, b, c])
        _, (u, v) = diameter(pts)
        o = (u+v)/2
        return o, float(np.linalg.norm(pts-o, axis=1).max())
    v = np.array([ac[1]*(ab@ab)-ab[1]*(ac@ac), ab[0]*(ac@ac)-ac[0]*(ab@ab)])/det
    return a+v, float(np.linalg.norm(v))


def minimum_circle(poly):
    """Randomized incremental MEC (fixed seed); final radius is an upper bound."""
    pts = np.asarray(poly, float).reshape(-1, 2)
    if not len(pts):
        return None, None
    pts = pts[np.random.default_rng(42).permutation(len(pts))]
    o, r = pts[0].copy(), 0.
    for i, p in enumerate(pts):
        if np.linalg.norm(p-o) <= r+1e-9:
            continue
        o, r = p.copy(), 0.
        for j, q in enumerate(pts[:i]):
            if np.linalg.norm(q-o) <= r+1e-9:
                continue
            o, r = (p+q)/2, float(np.linalg.norm(p-q)/2)
            for s in pts[:j]:
                if np.linalg.norm(s-o) > r+1e-9:
                    o, r = circumcircle(p, q, s)
    r = max(r, float(np.linalg.norm(pts-o, axis=1).max()))
    return o, r


def minimum_circle_enumerated(poly):
    """Independent support enumeration, reserved for verification."""
    p = np.asarray(poly, float)
    choices = [(a.copy(), 0.) for a in p]
    choices += [((a+b)/2, float(np.linalg.norm(a-b)/2)) for a, b in itertools.combinations(p, 2)]
    choices += [circumcircle(a, b, c) for a, b, c in itertools.combinations(p, 3)]
    enclosing = []
    for center, radius in choices:
        # Rank actual enclosing radii, not radii accepted with an inward slack.
        # Every support center is usable after expansion; the MEC center is among them.
        radius = max(radius, float(np.linalg.norm(p-center, axis=1).max()))
        if radius > 0:
            radius = math.nextafter(radius, math.inf)
        enclosing.append((center, radius))
    return min(enclosing, key=lambda c:c[1])


def halfplane_region(normals, bounds):
    """Q1: feasibility + four unboundedness LPs; no fabricated bounding box."""
    from scipy.optimize import linprog  # Q3/Q4 runtime only needs NumPy.
    a, b = np.asarray(normals, float).reshape(-1, 2), np.asarray(bounds, float)
    norm = np.linalg.norm(a, axis=1)
    if np.any((norm == 0) & (b < 0)):
        return {"status": "empty", "vertices": [], "diameter": None, "radius": None}
    b, a = b[norm > 0]/norm[norm > 0], a[norm > 0]/norm[norm > 0, None]
    def lp(c):
        return linprog(c, A_ub=a if len(a) else None, b_ub=b if len(a) else None,
                       bounds=[(None, None), (None, None)], method="highs")
    feasible = lp([0., 0.])
    if feasible.status == 2:
        return {"status": "empty", "vertices": [], "diameter": None, "radius": None}
    if feasible.status != 0:
        return {"status": "numerically_unresolved", "message": feasible.message}
    extrema = [lp(c) for c in [[1,0],[-1,0],[0,1],[0,-1]]]
    if any(r.status == 3 for r in extrema):
        return {"status": "unbounded", "vertices": [], "diameter": math.inf, "radius": math.inf}
    if any(r.status != 0 for r in extrema):
        return {"status": "numerically_unresolved"}
    vertices = [r.x for r in extrema]
    for i, j in itertools.combinations(range(len(a)), 2):
        det = float(cross(a[i], a[j]))
        if abs(det) < 1e-15:
            continue
        x = np.array([b[i]*a[j,1]-a[i,1]*b[j], a[i,0]*b[j]-b[i]*a[j,0]])/det
        if np.all(a@x-b <= 1e-7 + 1e-11*np.linalg.norm(x)):
            vertices.append(x)
    vertices = hull(vertices)
    d, pair = diameter(vertices)
    center, radius = minimum_circle(vertices)
    # A thin polygon is still two-dimensional; do not classify by relative area.
    dim = 0 if len(vertices)==1 else (1 if len(vertices)==2 else 2)
    return {"status": ["point", "segment", "bounded"][dim], "vertices": vertices.tolist(),
            "diameter": d, "diameter_endpoints": [x.tolist() for x in pair],
            "center": center.tolist(), "radius": radius}


def solve_bearings(observations, error_deg=1.):
    ab = [bearing_planes(p, angle, error_deg) for p, angle in observations]
    if not ab:
        return halfplane_region([], [])
    return halfplane_region(np.concatenate([a for a,b in ab]), np.concatenate([b for a,b in ab]))


def optical_cover(poly, first_angle, step=28.):
    """Cell centers cover a conservative oriented rectangle by radius <20 disks."""
    t = math.radians(first_angle)
    u = np.array([math.cos(t), math.sin(t)])
    v = np.array([-u[1], u[0]])
    basis = np.column_stack([u, v])
    coords = poly @ basis
    low, high = coords.min(axis=0)-1e-6, coords.max(axis=0)+1e-6
    counts = np.maximum(1, np.ceil((high-low)/step).astype(int))
    axes = [low[k]+(np.arange(counts[k])+.5)*(high[k]-low[k])/counts[k] for k in (0,1)]
    local = [(x,y) for j,y in enumerate(axes[1]) for x in (axes[0] if j%2==0 else axes[0][::-1])]
    points = np.asarray(local) @ basis.T
    cover_radius = float(np.linalg.norm((high-low)/counts)/2)
    return points, cover_radius
