"""Exact fixed-source-pair outer exclusion, opt-q12 §A.

Optional dependency layer: numpy proposes evidence; Fraction proves whole-box
inequalities; mpmath.iv proves source membership and the fixed-q upper bound.
The driver deliberately supports ONLY the standard symmetric continuous model.
Binary64 source coordinates denote exact rationals. No production predicate or
objective is replaced. Artifacts contain a closed partition, including unresolved
leaves on budget exit. See benchmarks/q2_outer/EXCLUSION.md for the proof scope.
"""
from dataclasses import asdict
from fractions import Fraction as F
from functools import lru_cache
import math
import time

import numpy as np
from mpmath.ctx_iv import MPIntervalContext

from .certified import certify

ROOT = (F(0), F(1005), F(0), F(1000))
INCUMBENT = (843.035666, 545.527004)
MODEL = 'standard-S0-theta0-eps1-rho1000-1500-near5-arena1800-v1'


def quadratic_min(coefficients, box):
    """Exact minimum of k*(qx²+qy²)+bx*qx+by*qy+c on a closed box."""
    k, bx, by, c = map(F, coefficients)
    lo, hi, bottom, top = map(F, box)
    if k <= 0 or lo > hi or bottom > top:
        raise ValueError('positive curvature and ordered box required')
    x = min(hi, max(lo, -bx/(2*k)))
    y = min(top, max(bottom, -by/(2*k)))
    return k*(x*x+y*y)+bx*x+by*y+c


def pair_coefficients(x, y, k):
    x, y, k = tuple(map(F, x)), tuple(map(F, y)), F(k)
    sx, sy = x[0]+y[0], x[1]+y[1]
    dot = x[0]*y[0]+x[1]*y[1]
    det = x[0]*y[1]-x[1]*y[0]
    return [(F(1), -sx, -sy, dot)] + [
        (k, -k*sx+s*(x[1]-y[1]), -k*sy+s*(y[0]-x[0]), k*dot+s*det)
        for s in (-1, 1)]


def pair_proves(x, y, box, target, k):
    """Exact box test; caller MUST separately prove both actual sources in F."""
    x, y = tuple(map(F, x)), tuple(map(F, y))
    if sum((a-b)**2 for a, b in zip(x, y)) < F(target)**2:
        return False
    if any(quadratic_min(c, box) < 0 for c in pair_coefficients(x, y, k)):
        return False
    return all(quadratic_min((1, -2*p[0], -2*p[1], sum(v*v for v in p)), box) > 25
               for p in (x, y))


def bisect(box):
    axis = 0 if box[1]-box[0] >= box[3]-box[2] else 2
    mid = (box[axis]+box[axis+1])/2
    left, right = list(box), list(box)
    left[axis+1], right[axis] = mid, mid
    return tuple(left), tuple(right)


def standard_source_set():
    from ..geometry import BearingMeasurement, NumericPolicy
    from ..feasible import PhysicsConfig, build_source_set
    return build_source_set(
        BearingMeasurement((0., 0.), 0., half_width_deg=1.),
        PhysicsConfig(rho_lo=1000., rho_hi=1500., near_radius=5.,
                      arena_radius=1800., arena_center=(0., 0.),
                      action_bounds=(-2000000., 2000000., -2000000., 2000000.)),
        NumericPolicy())


class Evidence:
    """Standard-model interval checks, with a private (not global) iv context."""
    def __init__(self, dps=60):
        self.iv = iv = MPIntervalContext()
        iv.dps = dps
        self.sn, self.cs = iv.sin(iv.pi/180), iv.cos(iv.pi/180)
        tangent = iv.tan(iv.pi/90)
        self.k = F(math.nextafter(float(tangent.a), -math.inf))
        if not 0 < iv.mpf(float(self.k)) < tangent.a:
            raise ValueError('could not enclose tan(2 degrees) from below')
        # Outward binary endpoint conversion; exact rectangle-distance proof
        # remains valid for every irrational center in these rectangles.
        self.centers = []
        for r in (5, 1000):
            for sign in (-1, 1):
                self.centers.append(tuple(
                    (F(math.nextafter(float(v.a), -math.inf)),
                     F(math.nextafter(float(v.b), math.inf)))
                    for v in (r*self.cs, sign*r*self.sn)))

    @lru_cache(maxsize=32768)
    def legal(self, point):
        x, y = map(self.iv.mpf, point)
        rr = x*x+y*y
        return bool(rr.a > 25 and rr.b <= 1500**2 and x.a > 0
                    and (self.sn*x-self.cs*y).a >= 0
                    and (self.sn*x+self.cs*y).a >= 0)

    def outside(self, box):
        for index, center in enumerate(self.centers):
            d2 = sum(max(F(0), box[2*i]-hi, lo-box[2*i+1])**2
                     for i, (lo, hi) in enumerate(center))
            if d2 > 1000**2:
                return index
        return None

    def incumbent_legal(self, q):
        x, y = map(self.iv.mpf, q)
        return all(((x-r*self.cs)**2+(y-sign*r*self.sn)**2).b < 1000**2
                   for r in (5, 1000) for sign in (-1, 1))


class Proposals:
    """Floating operations only select witnesses; none is a pruning authority."""
    def __init__(self, evidence, upper):
        self.evidence = evidence
        points = [(r*math.cos(math.radians(a)), r*math.sin(math.radians(a)))
                  for a in (-.999, 0., .999)
                  for r in [5.001, *range(25, 1500, 25), 1499.999]]
        points = [p for p in points if evidence.legal(p)]
        a = np.array(points)
        ii, jj = np.triu_indices(len(a), 1)
        x, y = a[ii], a[jj]
        d2 = ((x-y)**2).sum(1)
        keep = d2 > upper**2
        x, y, d2 = x[keep], y[keep], d2[keep]
        order = np.argsort(-d2, kind='stable')
        self.x, self.y = x[order], y[order]
        x, y = self.x, self.y
        sx, sy = x[:, 0]+y[:, 0], x[:, 1]+y[:, 1]
        dot, det = (x*y).sum(1), x[:, 0]*y[:, 1]-x[:, 1]*y[:, 0]
        k = float(evidence.k)
        self.coeffs = [(1., -sx, -sy, dot)] + [
            (k, -k*sx+s*(x[:, 1]-y[:, 1]), -k*sy+s*(y[:, 0]-x[:, 0]), k*dot+s*det)
            for s in (-1, 1)]

    def static(self, box):
        lo, hi, bottom, top = map(float, box)
        mask = np.ones(len(self.x), dtype=bool)
        for k, bx, by, c in self.coeffs:
            x, y = np.clip(-bx/(2*k), lo, hi), np.clip(-by/(2*k), bottom, top)
            mask &= k*(x*x+y*y)+bx*x+by*y+c >= -1e-7
        for p in (self.x, self.y):
            mask &= (np.maximum(np.maximum(lo-p[:, 0], p[:, 0]-hi), 0)**2
                     + np.maximum(np.maximum(bottom-p[:, 1], p[:, 1]-top), 0)**2) > 25
        indices = np.flatnonzero(mask)
        return [(tuple(self.x[i]), tuple(self.y[i])) for i in indices[:1]]

    def dynamic(self, box, target):
        q = np.array((float((box[0]+box[1])/2), float((box[2]+box[3])/2)))
        result = []
        for sign in (-1, 1):
            angle = sign*math.radians(.999999999)
            x = 1499.999999*np.array((math.cos(angle), math.sin(angle)))
            for delta in (-math.radians(1.999999999), math.radians(1.999999999)):
                a = x-q
                v = np.array((math.cos(delta)*a[0]-math.sin(delta)*a[1],
                              math.sin(delta)*a[0]+math.cos(delta)*a[1]))
                u = np.array((math.cos(angle), -math.sin(angle)))
                det = u[0]*v[1]-u[1]*v[0]
                if det == 0:
                    continue
                r = (q[0]*v[1]-q[1]*v[0])/det
                y = r*u
                d = math.dist(x, y)
                if not (5 < r < 1500 and d > target):
                    continue
                y = x+(y-x)*((target+d)/2/d)
                pair = tuple(map(float, x)), tuple(map(float, y))
                if all(self.evidence.legal(p) for p in pair):
                    result.append(pair)
        return result


def certify_outer(*, tau='0.01', max_nodes=10000, time_limit_s=120.,
                  dps=60, q=INCUMBENT, fixed_max_nodes=200000,
                  fixed_time_limit_s=60.):
    """Return a JSON-ready proof. Budgets apply to splitting after initialization.

    Pending leaves have the universal lower bound zero, so partial results never
    claim the requested gap. The target is exact U-tau, not float subtraction.
    A fixed-q budget exit still supplies a valid U (convergence is not presumed).
    No scene/root overrides: symmetry must not leak into nonstandard models.
    """
    tau = F(tau)
    if (tau <= 0 or isinstance(max_nodes, bool) or not isinstance(max_nodes, int)
            or max_nodes < 0 or not math.isfinite(time_limit_s) or time_limit_s < 0
            or not isinstance(dps, int) or dps < 30):
        raise ValueError('positive tau, nonnegative budgets and dps >= 30 required')
    q = tuple(map(float, q))
    if len(q) != 2 or not all(map(math.isfinite, q)):
        raise ValueError('finite 2D incumbent required')
    started = time.monotonic()
    evidence = Evidence(dps)
    if not evidence.incumbent_legal(q):
        raise ValueError('incumbent not strictly certified in all four disks')
    fixed = certify(standard_source_set(), q, tol=.001, max_nodes=fixed_max_nodes,
                    time_limit_s=fixed_time_limit_s, dps=30)
    upper = F(fixed.upper_m)
    target = max(F(0), upper-tau)
    proposals = Proposals(evidence, float(upper))
    stack, leaves, nodes = [(ROOT, ())], [], 0
    search_start = time.monotonic()
    reason = 'complete'
    while stack:
        if nodes >= max_nodes or time.monotonic()-search_start >= time_limit_s:
            reason = 'node_budget' if nodes >= max_nodes else 'time_budget'
            break
        box, parents = stack.pop()
        nodes += 1
        record = dict(box=list(map(str, box)))
        disk = evidence.outside(box)
        if disk is not None:
            leaves.append(dict(record, kind='disk', disk=disk))
            continue
        bank = list(parents)+proposals.dynamic(box, float(target))
        if max(box[1]-box[0], box[3]-box[2]) >= 25:
            bank += proposals.static(box)
        pair = next(((x, y) for x, y in bank
                     if evidence.legal(x) and evidence.legal(y)
                     and pair_proves(x, y, box, target, evidence.k)), None)
        if pair is not None:
            leaves.append(dict(record, kind='pair', x=pair[0], y=pair[1], lower=str(target)))
            continue
        left, right = bisect(box)
        keep = tuple(bank[-8:])
        stack.extend(((left, keep), (right, keep)))
    for box, _ in stack:
        leaves.append(dict(box=list(map(str, box)), kind='pending', lower='0'))
    complete = not stack
    lower = target if complete else F(0)
    gap = upper-lower
    return dict(schema='q2-outer-exclusion-v1', model=MODEL, root=list(map(str, ROOT)),
                reflected_y=True, q=q, tau=str(tau), k=str(evidence.k), target=str(target),
                lower=str(lower), upper=str(upper), gap=str(gap), converged=complete,
                status='CERTIFIED_OUTER_TAU' if complete else 'CERTIFIED_OUTER_BOUNDS',
                stop_reason=reason, nodes=nodes, pending=len(stack), leaves=leaves,
                fixed_certificate=asdict(fixed), source_dps=dps,
                search_seconds=time.monotonic()-search_start,
                elapsed_seconds=time.monotonic()-started,
                options=dict(max_nodes=max_nodes, time_limit_s=time_limit_s,
                             fixed_max_nodes=fixed_max_nodes,
                             fixed_time_limit_s=fixed_time_limit_s))
