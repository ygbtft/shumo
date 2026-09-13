"""Q3-only distance dominance from actual negative replies and successful anchors."""
import numpy as np

from geometry import clip
from coupled_dispatch_policy import CoupledCompletionPolicy


def dominance_clip(poly, negative, anchor):
    """Retain |g-q| >= |g-a|, with outward slack; never infer an unknown radius.

    Success at a implies rho >= |g-a|; actual Q3 no_signal at q implies
    |g-q| > rho. Thus (q-a).g < (q-a).(q+a)/2. Keep the closed
    halfplane. Normalize before clipping so its tolerance is in metres.
    The extra 1e-4 squared-metre slack matches the reviewed prototype.
    Coincident/near-coincident anchors carry no numerically useful constraint.
    This implication is invalid for directional Q4 reception.
    """
    q, a = np.asarray(negative, float), np.asarray(anchor, float)
    delta = q-a
    distance = float(np.linalg.norm(delta))
    if not np.isfinite(distance) or distance <= 1e-7:
        return poly
    normal = delta/distance
    bound = float(normal @ (a+delta/2)) + 1e-4/(2*distance)
    return clip(poly, normal, bound)


class OmniNegativeCompletionPolicy(CoupledCompletionPolicy):
    """Enabled only by the range_area7 factory; historical candidates stay frozen."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.mixed:
            raise ValueError("Distance dominance requires Q3 omnidirectional reception")
        self._real_negatives = {}
        self._success_anchors = {}
        self.stats.update(omni_negative_cuts=0, omni_negative_inconsistencies=0)

    def record_feedback(self, p, ch, reply):
        super().record_feedback(p, ch, reply)
        # Do not record inferred certified_no_reception, failed transports or
        # rejected requests. Client validates acceptance before this hook runs.
        if reply.get("accepted") is not True or ch in self.cleared:
            return
        result = reply["measure_result"]
        point = tuple(map(float, p))
        negatives = self._real_negatives.setdefault(ch, set())
        anchors = self._success_anchors.setdefault(ch, set())
        if result == "no_signal" and point not in negatives:
            negatives.add(point)
            pairs = [(point, a) for a in sorted(anchors)]
        elif result == "direction" and point not in anchors:
            anchors.add(point)
            pairs = [(q, point) for q in sorted(negatives)]
        else:
            return
        # Each distinct pair is applied once. Later bearing updates intersect
        # the retained region, so earlier constraints need not be reapplied.
        if ch not in self.regions:
            return
        for q, a in pairs:
            old = self.regions[ch]
            candidate = dominance_clip(old, q, a)
            if not len(candidate) or not np.isfinite(candidate).all():
                self.stats["omni_negative_inconsistencies"] += 1
                continue  # Preserve the last containing region on inconsistent feedback.
            if not np.array_equal(candidate, old):
                self.regions[ch] = candidate
                self._circles.pop(ch, None)
                self.stats["omni_negative_cuts"] += 1
