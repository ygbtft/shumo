"""Use convex reception geometry to retain safe outer position regions."""
from collections import defaultdict
from itertools import combinations
import numpy as np

from coupled_dispatch_policy import CoupledCompletionPolicy, CoupledWidthPolicy
from geometry import clip, hull, polygon_area


def exclude_shadow(poly, negative, success_a, success_b):
    """Outer convex hull after excluding q+cone(q-a,q-b).

    If q is inside triangle(g,a,b), the convex receiving footprint containing
    g,a,b must also contain q. A genuine negative q excludes such g. We retain
    both boundary halfplanes with an outward margin before taking their hull.
    """
    q = np.asarray(negative)
    a, b = q-success_a, q-success_b
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if min(na, nb) < 1e-6:
        return poly
    a, b = a/na, b/nb
    cross = a[0]*b[1]-a[1]*b[0]
    if abs(cross) < 1e-4:
        return poly
    if cross < 0.:
        a,b = b,a
    n1, n2 = np.array([-a[1],a[0]]), np.array([b[1],-b[0]])
    bounds = [float(n1@q)+1e-4, float(n2@q)+1e-4]
    if np.max(poly@n1) <= bounds[0] or np.max(poly@n2) <= bounds[1]:
        return poly
    pieces = [clip(poly,n1,bounds[0]),clip(poly,n2,bounds[1])]
    nonempty = [p for p in pieces if len(p)]
    if not nonempty:
        return np.empty((0,2))
    candidate = hull(np.vstack(nonempty))
    if len(poly) < 3 or polygon_area(poly) < 1e-8:
        if np.max(np.ptp(poly,axis=0)-np.ptp(candidate,axis=0)) > 1e-5:
            return candidate
    elif polygon_area(poly)-polygon_area(candidate) > 1e-6*max(1.,polygon_area(poly)):
        return candidate
    return poly


class NegativeHullMixin:
    def __init__(self,*args,negative_hull=True,negative_history=12,success_history=3,**kwargs):
        if not 1 <= negative_history <= 32 or not 2 <= success_history <= 4:
            raise ValueError("Negative inference memory outside fixed budget")
        super().__init__(*args,**kwargs)
        self.negative_hull=negative_hull
        self.negative_history,self.success_history=negative_history,success_history
        self._negative_history=defaultdict(list)
        self.stats.update(negative_hull_updates=0,negative_shadow_cuts=0,negative_hull_inconsistent_cuts=0,
                          negative_history_limit=negative_history,success_history_limit=success_history)

    def measure(self,p,ch):
        result=super().measure(p,ch)
        if not self.negative_hull or ch in self.cleared:
            return result
        if result == "no_signal":
            memory=self._negative_history[ch]
            q=np.asarray(p).copy()
            if not any(np.linalg.norm(q-old)<1e-8 for old in memory):
                memory.append(q)
                del memory[:-self.negative_history]
        # A certified skipped query is valid negative knowledge, but this
        # ablation deliberately uses only actual RF no-signal responses.
        if result not in ("direction","no_signal") or ch not in self.regions or len(self.observations[ch]) < 2:
            return result
        poly=self.regions[ch]
        cuts=0
        successes=[position for position,_ in self.observations[ch][-self.success_history:]]
        for q in self._negative_history[ch]:
            for a,b in combinations(successes,2):
                candidate=exclude_shadow(poly,q,a,b)
                if not len(candidate):
                    self.stats["negative_hull_inconsistent_cuts"]+=1
                    # Keep the previous outer region; do not erase a source
                    # on inconsistent floating geometry or feedback.
                    continue
                if candidate is not poly:
                    poly=candidate
                    cuts+=1
        if cuts:
            self.regions[ch]=poly
            self._circles.pop(ch,None)
            self.stats["negative_hull_updates"]+=1
            self.stats["negative_shadow_cuts"]+=cuts
        return result


class NegativeWidthPolicy(NegativeHullMixin,CoupledWidthPolicy):
    pass


class NegativeCompletionPolicy(NegativeHullMixin,CoupledCompletionPolicy):
    pass
