"""Cheap necessary point checks before the unchanged full-region certificate."""
import numpy as np
from itertools import combinations
from faithful_skip_policy import FaithfulSkipMixin
from deferred_skip_policy import (DeferredWidthPolicy, DeferredFastWidthPolicy, pair_nonreception_certificate)


def cheap_pair_nonreception_certificate(poly, query, a, b):
    # A full-region certificate necessarily contains this actual polygon
    # vertex. Reject only clear violations; the original strict normalized
    # halfplanes still make every acceptance decision.
    qx,qy = float(query[0]),float(query[1])
    gx,gy = float(poly[0,0])-qx,float(poly[0,1])-qy
    ax,ay = float(a[0])-qx,float(a[1])-qy
    bx,by = float(b[0])-qx,float(b[1])-qy
    if 2*(ax*gx+ay*gy)-(ax*ax+ay*ay) < -1e-5:
        return None
    if 2*(bx*gx+by*gy)-(bx*bx+by*by) < -1e-5:
        return None
    ex,ey = bx-ax,by-ay
    denominator = gx*ey-gy*ex
    if abs(denominator)>1e-3:
        u=(ax*ey-ay*ex)/denominator
        v=(ax*gy-ay*gx)/denominator
        if not (-1e-4<=u<=1.+1e-4 and -1e-4<=v<=1.+1e-4):
            return None
    return pair_nonreception_certificate(poly,query,a,b)


class CheapPairMixin:
    def measure(self, p, ch):
        self._planned_channel = ch
        certificate = None
        stationary = np.array_equal(np.asarray(p), np.asarray(self.client.position))
        if self.faithful_skip and self._surveying and ch in self.regions and ch not in self.cleared:
            center, radius = self.circle(ch)
            if self.defer_scan or stationary:
                if np.linalg.norm(p-center) > 1500. + radius + 1e-5:
                    certificate = dict(kind="range", center=center.copy(), radius=radius)
                elif self.predict_negatives:
                    for a,b in combinations(reversed(self._logical_negatives[ch]), 2):
                        self.stats["pair_prediction_checks"] += 1
                        planes = cheap_pair_nonreception_certificate(self.regions[ch], np.asarray(p), a, b)
                        if planes is not None:
                            certificate = dict(kind="two_negatives", a=a.copy(), b=b.copy())
                            break
            elif np.linalg.norm(p-center) > 1500. + radius + 1e-5:
                self.stats["faithful_nonstationary_retained"] += 1
        if certificate is not None:
            self._attempted[ch].append(np.asarray(p).copy())
            self.stats["faithful_attempt_memory_updates"] += 1
            if hasattr(self, "_last_negative"):
                self._last_negative[ch] = np.asarray(p).copy()
                self.stats["inferred_negative_memory_updates"] += 1
            self.stats["certified_scan_skips"] += 1
            self.stats["faithful_stationary_skips"] += int(stationary)
            self.stats["deferred_nonstationary_skips"] += int(not stationary)
            self.stats["certified_range_scan_skips"] += int(certificate["kind"] == "range")
            self.stats["predicted_pair_skips"] += int(certificate["kind"] == "two_negatives")
            self._last_skip_certificate = certificate
            self.remember_negative(p, ch)
            return "certified_no_reception"
        if self._surveying and ch not in self.regions and ch not in self.cleared:
            self._scan_actual_unknown += 1
        # Reuse the established policy below FaithfulSkipMixin; this method
        # already maintains the logical state and applies its replacement rule.
        result = super(FaithfulSkipMixin, self).measure(p, ch)
        if result == "no_signal" and ch not in self.cleared:
            self.remember_negative(p, ch)
        return result


class CheapPredictionWidthPolicy(CheapPairMixin,DeferredWidthPolicy):
    pass


class CheapPredictionFastWidthPolicy(CheapPairMixin,DeferredFastWidthPolicy):
    pass
