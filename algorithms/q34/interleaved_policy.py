"""Interleave bounded localization packets with scan and clearance tasks.

Every source retains its lifetime RF budget. A pair of Q4 probes is atomic;
only a completed pair or successful bearing can yield to another task.
"""
from collections import defaultdict
import math
import numpy as np

from adaptive_routes import remaining_route
from clearance_policy import ClearanceMixin
from efficient_joint_policy import EfficientJointPolicy, ProbeJointPolicy
from geometry import clip
from joint_policy import choose_covariance
from policies import Policy


class InterleavedMixin:
    def __init__(self, *args, pause_limit=16, prediction="center", dispatch="two_opt", **kwargs):
        if not 0 <= pause_limit <= 24:
            raise ValueError("Interruption budget must be between 0 and 24")
        if prediction not in ("center", "action") or dispatch not in ("two_opt", "nearest"):
            raise ValueError("Unknown task prediction or dispatcher")
        super().__init__(*args, **kwargs)
        self.pause_limit, self.prediction, self.dispatch = pause_limit, prediction, dispatch
        # Lifetime counts per channel survive task switches; primary counts exclude sharing RF.
        self._rounds = defaultdict(int)
        self._primary_counts = defaultdict(int)
        self._last_partial = None
        self._fallback_done = set()
        self.stats.update(source_packets=0, source_interruptions=0, interrupted_channels=0,
                          maximum_source_rounds=0, maximum_source_primary_rf=0,
                          packet_fallbacks=0, forced_continuations=0)
        self._interrupted_channels = set()

    def predicted_action(self, ch):
        center, radius = self.circle(ch)
        if self.prediction == "center":
            return center
        if self.mixed:
            if (radius <= 20. - 1e-5 or self._rounds[ch] >= self.bracket_steps
                    or (radius <= self.bracket_trial_radius and ch not in self.bracket_tried)):
                return center
            return self.probes(ch, self._rounds[ch])[3][0]
        if (radius <= 20. - 1e-5 or self._rounds[ch] >= self.max_active
                or (radius <= self.trial_radius and ch not in self._trial_done)):
            return center
        return choose_covariance(self.regions[ch], self.observations[ch], self.client.position,
                                 self.sensing == "cov_robust", self.time_weight)

    def next_task(self, unused):
        if len(set(self.regions) | self.cleared) == 16:
            self.stats["known_upper_bound_skips"] += len(unused)
            unused.clear()
        # source_interruptions is a global budget, not a fresh allowance for each source.
        previous = self._last_partial
        if previous is not None and previous not in self.cleared and self.stats["source_interruptions"] >= self.pause_limit:
            self.stats["forced_continuations"] += 1
            return "source", previous, self.circle(previous)[0]
        tasks = [("survey", i, self.stations[i]) for i in unused]
        tasks.extend(("source", ch, self.predicted_action(ch)) for ch in self.regions if ch not in self.cleared)
        if not tasks:
            return None
        points = np.array([task[2] for task in tasks])
        if self.dispatch == "nearest":
            chosen = int(np.linalg.norm(points - self.client.position, axis=1).argmin())
        else:
            self.stats["joint_route_solves"] += 1
            chosen = int(remaining_route(points, self.client.position, True)[0])
        task = tasks[chosen]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task

    def fallback(self, ch):
        if ch in self.cleared:
            return
        assert ch not in self._fallback_done
        self._fallback_done.add(ch)
        self.stats["packet_fallbacks"] += 1
        old_active = self.active
        self.active = False
        try:
            Policy.complete_source(self, ch)
        finally:
            self.active = old_active
        assert ch in self.cleared

    def primary_measure(self, q, ch):
        self._primary_counts[ch] += 1
        self.stats["active_measurements"] += 1
        if self.mixed:
            self.stats["bracket_measurements"] += 1
        result = self.measure(q, ch)
        self.stats["active_no_signal"] += int(result == "no_signal")
        return result

    def source_packet(self, ch):
        if ch in self.cleared:
            return
        self.stats["source_packets"] += 1
        maximum = self.bracket_steps if self.mixed else self.max_active
        if self._rounds[ch] >= maximum:
            self.fallback(ch)
            return
        center, radius = self.circle(ch)
        if radius <= 20. - 1e-5:
            if not self.clear(center, ch, True):
                raise RuntimeError("Certified packet clearance failed")
            return
        if self.mixed:
            if radius <= self.bracket_trial_radius and ch not in self.bracket_tried:
                self.bracket_tried.add(ch)
                self.stats["bracket_optical_trials"] += 1
                if self.clear(center, ch):
                    self.stats["bracket_optical_success"] += 1
                    return
            anchor, u, length, probes = self.probes(ch, self._rounds[ch])
            if length <= 1e-3:
                self.fallback(ch)
                return
            self._rounds[ch] += 1
            both_negative = True
            for q in probes:
                result = self.primary_measure(q, ch)
                if ch in self.cleared:
                    return
                if result != "no_signal":
                    both_negative = False
                    break
            if both_negative:
                # Only the completed negative pair licenses this cut. u follows an observed
                # bearing; anchor projection + length is the cutoff, expanded by 1e-6 m.
                restricted = clip(self.regions[ch], u, float(u @ anchor) + length + 1e-6)
                if not len(restricted):
                    self.stats["bracket_cut_inconsistencies"] += 1
                    self.fallback(ch)
                    return
                self.regions[ch] = restricted
                # Region changed: its cached enclosing circle is now stale.
                self._circles.pop(ch, None)
                self.stats["bracket_pair_cuts"] += 1
        else:
            if radius <= self.trial_radius and ch not in self._trial_done:
                self._trial_done.add(ch)
                self.stats["early_optical_trials"] += 1
                if self.clear(center, ch):
                    self.stats["early_optical_success"] += 1
                    return
                q = center
            else:
                q = choose_covariance(self.regions[ch], self.observations[ch], self.client.position,
                                      self.sensing == "cov_robust", self.time_weight)
            self._rounds[ch] += 1
            result = self.primary_measure(q, ch)
            if ch in self.cleared:
                return
            if result == "no_signal":
                self.fallback(ch)
                return
        # Match the existing atomic policy when a source consumes its final
        # RF round: it immediately enters finite optical completion.
        if self._rounds[ch] >= maximum and ch not in self.cleared:
            self.fallback(ch)

    def run(self):
        self.client.enter()
        unused = list(range(len(self.stations)))
        # 16 is only the public upper bound; fewer sources require complete station coverage.
        while len(self.cleared) < 16:
            task = self.next_task(unused)
            if task is None:
                break
            kind, key, p = task
            if kind == "source":
                self.source_packet(key)
                self._last_partial = None if key in self.cleared else key
                continue
            self._last_partial = None
            unused.remove(key)
            self.stats["stations_visited"] += 1
            self._surveying = True
            try:
                channels = [ch for ch in range(1, 21) if ch not in self.cleared]
                if self.client.channel in channels:
                    channels.remove(self.client.channel)
                    channels.insert(0, self.client.channel)
                for ch in channels:
                    if ch in self.cleared:
                        continue
                    if ch in self.regions and self.circle(ch)[1] <= 20. - 1e-5:
                        self.stats["skipped_precise_measurements"] += 1
                        continue
                    self.measure(p, ch)
                    # Processed includes certified skip; unknown channels must still receive real RF.
                    self.surveyed[ch].add(key)
            finally:
                self._surveying = False
        if len(self.cleared) == 16:
            self.stats["stop_reason"] = "public_upper_bound_16"
        else:
            assert not unused and all(ch in self.cleared for ch in self.regions)
            assert all(ch in self.regions or ch in self.cleared or len(self.surveyed[ch]) == len(self.stations)
                       for ch in range(1, 21))
            self.stats["stop_reason"] = "full_coverage_and_all_discovered_cleared"
        self.stats["interrupted_channels"] = len(self._interrupted_channels)
        self.stats["maximum_source_rounds"] = max(self._rounds.values(), default=0)
        self.stats["maximum_source_primary_rf"] = max(self._primary_counts.values(), default=0)
        assert self.stats["source_interruptions"] <= self.pause_limit
        assert self.stats["maximum_source_rounds"] <= (self.bracket_steps if self.mixed else self.max_active)
        assert self.stats["maximum_source_primary_rf"] <= (2 * self.bracket_steps if self.mixed else self.max_active)
        self.client.exit()
        return {**self.stats, "discovered_channels": len(set(self.regions) | self.cleared),
                "policy_cleared_channels": sorted(self.cleared)}


class InterleavedJointPolicy(InterleavedMixin, EfficientJointPolicy):
    pass


class InterleavedProbePolicy(InterleavedMixin, ProbeJointPolicy):
    pass


class InterleavedClearancePolicy(ClearanceMixin, InterleavedJointPolicy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_clearance()
