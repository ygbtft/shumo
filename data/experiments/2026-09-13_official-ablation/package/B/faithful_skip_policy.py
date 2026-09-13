"""Delete certified stationary RF requests while preserving the baseline plan.

The logical channel is only a planning variable. Client channel, position,
clock and protocol replies always describe actual accepted requests.
"""
import numpy as np

from coupled_dispatch_policy import CoupledCompletionPolicy, CoupledWidthPolicy
from fast_dispatch_policy import FastWidthPolicy


class FaithfulSkipMixin:
    def __init__(self, *args, faithful_skip=True, range_skip=False, **kwargs):
        if range_skip:
            raise ValueError("Faithful skipping replaces the earlier range-skip rule")
        super().__init__(*args, range_skip=False, **kwargs)
        self.faithful_skip = faithful_skip
        self._planned_channel = self.client.channel
        self.stats.update(faithful_stationary_skips=0, faithful_attempt_memory_updates=0,
                          faithful_nonstationary_retained=0)

    def measure(self, p, ch):
        # Set before the actual call: nested opportunistic measurements must
        # leave their own last channel in both real and logical histories.
        self._planned_channel = ch
        if self.faithful_skip and self._surveying and ch in self.regions and ch not in self.cleared:
            center, radius = self.circle(ch)
            if np.linalg.norm(p-center) > 1500. + radius + 1e-5:
                # The protocol has no separate move command. Retain the first
                # RF at a new position, even if its outcome is predictable.
                if np.array_equal(np.asarray(p), np.asarray(self.client.position)):
                    self._attempted[ch].append(np.asarray(p).copy())
                    self.stats["faithful_attempt_memory_updates"] += 1
                    if hasattr(self, "_last_negative"):
                        self._last_negative[ch] = np.asarray(p).copy()
                        self.stats["inferred_negative_memory_updates"] += 1
                    self.stats["certified_range_scan_skips"] += 1
                    self.stats["faithful_stationary_skips"] += 1
                    return "certified_no_reception"
                self.stats["faithful_nonstationary_retained"] += 1
        return super().measure(p, ch)

    def scan_station(self, p, key):
        self._surveying = True
        try:
            channels = [ch for ch in range(1, 21) if ch not in self.cleared]
            if self._planned_channel in channels:
                channels.remove(self._planned_channel)
                channels.insert(0, self._planned_channel)
            for ch in channels:
                if ch in self.cleared:
                    continue
                if ch in self.regions and self.circle(ch)[1] <= 20. - 1e-5:
                    self.stats["skipped_precise_measurements"] += 1
                    continue
                self.measure(p, ch)
                self.surveyed[ch].add(key)
        finally:
            self._surveying = False

    def run(self):
        # This is the existing JointTaskPolicy/InterleavedMixin loop with the
        # scan channel order taken from the unabridged logical plan.
        self.client.enter()
        unused = list(range(len(self.stations)))
        while len(self.cleared) < 16:
            task = self.next_task(unused)
            if task is None:
                break
            kind, key, p = task
            if kind == "source":
                if self.mixed:
                    self.source_packet(key)
                    self._last_partial = None if key in self.cleared else key
                else:
                    self.complete_source(key)
                    if key not in self.cleared:
                        raise RuntimeError("Source completion did not terminate")
                continue
            if self.mixed:
                self._last_partial = None
            unused.remove(key)
            self.stats["stations_visited"] += 1
            self.scan_station(p, key)
        if len(self.cleared) == 16:
            self.stats["stop_reason"] = "public_upper_bound_16"
        else:
            assert not unused and all(ch in self.cleared for ch in self.regions)
            assert all(ch in self.regions or ch in self.cleared or len(self.surveyed[ch]) == len(self.stations)
                       for ch in range(1, 21))
            self.stats["stop_reason"] = "full_coverage_and_all_discovered_cleared"
        if self.mixed:
            self.stats["interrupted_channels"] = len(self._interrupted_channels)
            self.stats["maximum_source_rounds"] = max(self._rounds.values(), default=0)
            self.stats["maximum_source_primary_rf"] = max(self._primary_counts.values(), default=0)
            assert self.stats["source_interruptions"] <= self.pause_limit
            assert self.stats["maximum_source_rounds"] <= self.bracket_steps
            assert self.stats["maximum_source_primary_rf"] <= 2 * self.bracket_steps
        self.client.exit()
        return {**self.stats, "discovered_channels": len(set(self.regions) | self.cleared),
                "policy_cleared_channels": sorted(self.cleared)}


class FaithfulCompletionPolicy(FaithfulSkipMixin, CoupledCompletionPolicy):
    pass


class FaithfulWidthPolicy(FaithfulSkipMixin, CoupledWidthPolicy):
    pass


class FaithfulFastWidthPolicy(FaithfulSkipMixin, FastWidthPolicy):
    pass
