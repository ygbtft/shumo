"""Rank scan tasks using public negative history and a documented search prior.

Finite position/orientation hypotheses affect task priority only. The original
continuous layout certificate and every remaining scan are retained.
"""
import math
import numpy as np

from adaptive_routes import remaining_route
from clearance_policy import ClearanceJointPolicy
from efficient_joint_policy import ProbeJointPolicy
from interleaved_policy import InterleavedClearancePolicy, InterleavedProbePolicy


class DiscoveryPriorityMixin:
    def __init__(self, *args, discovery_weight=900., choice_count=4, **kwargs):
        super().__init__(*args, **kwargs)
        if discovery_weight < 0 or not 1 <= choice_count <= 8:
            raise ValueError("Invalid nonnegative priority weight or shortlist")
        self.discovery_weight = discovery_weight
        self.choice_count = choice_count
        rng = np.random.default_rng(42)
        theta = rng.uniform(0., 2 * math.pi, 384)
        radial = 1800. * np.sqrt(rng.uniform(0., 1., 384))
        interior = radial[:, None] * np.column_stack((np.cos(theta), np.sin(theta)))
        boundary_angle = np.arange(128) * 2 * math.pi / 128 + rng.uniform(0., 2 * math.pi)
        boundary = 1800. * np.column_stack((np.cos(boundary_angle), np.sin(boundary_angle)))
        # 384 area samples + 128 boundary samples give the boundary an artificial 1/4
        # weight. The 12 orientations are equally weighted; gains are ranking scores,
        # not true discovery probabilities. 1000 m is the minimum receiving radius.
        locations = np.vstack((interior, boundary))
        delta = self.stations[:, None, :] - locations[None, :, :]
        in_range = np.sum(delta ** 2, axis=2) < 1000. ** 2 - 1e-6
        if self.mixed:
            # The 12 faces include the outward normal at each hypothetical
            # position. This is a conservative search prior, not hidden truth
            # or a claim about the official directional-source distribution.
            yaw = np.arctan2(locations[:, 1], locations[:, 0])[:, None] + np.arange(12) * 2 * math.pi / 12
            normals = np.stack((np.cos(yaw), np.sin(yaw)), axis=-1)
            facing = np.einsum("spd,pad->spa", delta, normals) >= 0.
            self._visible_worlds = (in_range[:, :, None] & facing).reshape(len(self.stations), -1)
        else:
            self._visible_worlds = in_range
        self.stats.update(discovery_priority_overrides=0, discovery_prior_worlds=int(self._visible_worlds.shape[1]),
                          last_sampled_unknown_worlds=int(self._visible_worlds.shape[1]))

    def next_task(self, unused):
        if len(set(self.regions) | self.cleared) == 16:
            self.stats["known_upper_bound_skips"] += len(unused)
            unused.clear()
        previous = getattr(self, "_last_partial", None)
        if previous is not None and previous not in self.cleared and self.stats["source_interruptions"] >= self.pause_limit:
            self.stats["forced_continuations"] += 1
            return "source", previous, self.circle(previous)[0]
        pending = [ch for ch in self.regions if ch not in self.cleared]
        predict = self.predicted_action if hasattr(self, "predicted_action") else lambda ch: self.circle(ch)[0]
        tasks = [("survey", i, self.stations[i]) for i in unused]
        tasks.extend(("source", ch, predict(ch)) for ch in pending)
        if not tasks:
            return None
        points = np.array([task[2] for task in tasks])
        self.stats["joint_route_solves"] += 1
        route = remaining_route(points, self.client.position, True)
        chosen = int(route[0])
        # Zero discovery reward must retain the base route, without shortlist
        # promotion becoming an independent route optimization switch.
        if self.discovery_weight:
            unvisited_mask = np.zeros(len(self.stations), dtype=bool)
            unvisited_mask[unused] = True
            seen = ~unvisited_mask
            # Seen stations were processed for every unknown channel; this is search
            # history, not an individual known source's RF posterior.
            if seen.any():
                remaining_worlds = ~self._visible_worlds[seen].any(axis=0)
            else:
                remaining_worlds = np.ones(self._visible_worlds.shape[1], dtype=bool)
            total = int(remaining_worlds.sum())
            self.stats["last_sampled_unknown_worlds"] = total
            gains = np.sum(self._visible_worlds[:, remaining_worlds], axis=1) / max(1, total)
            scores = []
            for j in range(min(self.choice_count, len(route))):
                candidate = int(route[j])
                promoted_order = np.concatenate((route[j:j + 1], route[:j], route[j + 1:]))
                sequence = points[promoted_order]
                length = np.linalg.norm(sequence[0] - self.client.position)
                if len(sequence) > 1:
                    length += np.linalg.norm(np.diff(sequence, axis=0), axis=1).sum()
                kind, key, _ = tasks[candidate]
                reward = self.discovery_weight * gains[key] if kind == "survey" else 0.
                # JointTaskPolicy.run already skips survey RF for known
                # sources with MEC <= 20 - 1e-5. Clearing them adds zero
                # future RF savings, so source tasks receive no extra reward.
                scores.append((float(length / 5. - reward), j, candidate))
            chosen = min(scores)[2]
            self.stats["discovery_priority_overrides"] += int(chosen != route[0])
        task = tasks[chosen]
        if previous is not None and previous not in self.cleared and task[:2] != ("source", previous):
            self.stats["source_interruptions"] += 1
            self._interrupted_channels.add(previous)
        return task


class DiscoveryClearancePolicy(DiscoveryPriorityMixin, ClearanceJointPolicy):
    pass


class DiscoveryProbePolicy(DiscoveryPriorityMixin, ProbeJointPolicy):
    pass


class DiscoveryPacketClearancePolicy(DiscoveryPriorityMixin, InterleavedClearancePolicy):
    pass


class DiscoveryPacketProbePolicy(DiscoveryPriorityMixin, InterleavedProbePolicy):
    pass
