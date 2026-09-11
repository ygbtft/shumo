"""Preserve the full scan plan while deferring movement to retained requests."""
from collections import defaultdict
from itertools import combinations
import numpy as np

from faithful_skip_policy import FaithfulSkipMixin, FaithfulCompletionPolicy, FaithfulWidthPolicy, FaithfulFastWidthPolicy
from historical_pair_policy import exclusion_planes


def pair_nonreception_certificate(poly, query, a, b):
    """All feasible sources contradict reception at query, given two negatives.

    Strict inward margin on normalized exclusion halfplanes is conservative.
    """
    planes = exclusion_planes(query, a, b)
    if planes is None:
        return None
    normals, bounds = planes
    if not np.all(normals @ poly[0] - bounds < -1e-4):
        return None
    if np.all(poly @ normals.T - bounds < -1e-4):
        return planes
    return None


class DeferredScanMixin:
    def __init__(self, *args, defer_scan=True, predict_negatives=False, prediction_history=4, **kwargs):
        if not 2 <= prediction_history <= 8:
            raise ValueError("Prediction memory outside 2..8")
        super().__init__(*args, **kwargs)
        self.defer_scan, self.predict_negatives = defer_scan, predict_negatives
        self.prediction_history = prediction_history
        self._logical_negatives = defaultdict(list)
        self._last_skip_certificate = None
        self._scan_actual_unknown = 0
        self.stats.update(certified_scan_skips=0, deferred_nonstationary_skips=0,
                          predicted_pair_skips=0, pair_prediction_checks=0,
                          minimum_actual_unknown_per_station=20,
                          logical_negative_memory_limit=prediction_history)

    def remember_negative(self, p, ch):
        if not self.predict_negatives:
            return
        memory = self._logical_negatives[ch]
        q = np.asarray(p).copy()
        if not any(np.array_equal(q, old) for old in memory):
            memory.append(q)
            del memory[:-self.prediction_history]

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
                        planes = pair_nonreception_certificate(self.regions[ch], np.asarray(p), a, b)
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

    def scan_station(self, p, key):
        unknown = [ch for ch in range(1,21) if ch not in self.regions and ch not in self.cleared]
        assert len(unknown) >= 4, "Public bound of 16 valid channels was violated"
        self._scan_actual_unknown = 0
        super().scan_station(p, key)
        # These retained requests ensure that any deferred travel to p occurs
        # before the scan finishes. No hidden source count is read.
        assert self._scan_actual_unknown >= len(unknown) >= 4
        self.stats["minimum_actual_unknown_per_station"] = min(
            self.stats["minimum_actual_unknown_per_station"], self._scan_actual_unknown)


class DeferredCompletionPolicy(DeferredScanMixin, FaithfulCompletionPolicy):
    pass


class DeferredWidthPolicy(DeferredScanMixin, FaithfulWidthPolicy):
    pass


class DeferredFastWidthPolicy(DeferredScanMixin, FaithfulFastWidthPolicy):
    pass
