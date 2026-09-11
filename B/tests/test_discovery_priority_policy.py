"""Regression tests for incremental RF savings; no service is contacted."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from discovery_priority_policy import (
    DiscoveryClearancePolicy,
    DiscoveryProbePolicy,
    DiscoveryPacketClearancePolicy,
    DiscoveryPacketProbePolicy,
)
from joint_task_policy import JointTaskPolicy


POLICIES = (
    (DiscoveryClearancePolicy, False),
    (DiscoveryClearancePolicy, True),
    (DiscoveryProbePolicy, True),
    (DiscoveryPacketClearancePolicy, False),
    (DiscoveryPacketClearancePolicy, True),
    (DiscoveryPacketProbePolicy, True),
)
PRECISE_RADII = (0., 10., 20. - 1e-5)
# Recorded from the unmodified policy with default clear_weight=0.
BASELINE_ORDER = [
    ("survey", 0), ("survey", 1), ("survey", 2),
    ("source", 1), ("source", 2), ("source", 3),
]


def make_policy(cls=DiscoveryClearancePolicy, mixed=False,
                radii=PRECISE_RADII, **kwargs):
    client = SimpleNamespace(position=np.array([0., 0.]), channel=1,
                             enter=Mock(), exit=Mock())
    policy = cls(client, [[10., 0.], [20., 0.], [30., 0.]],
                 mixed=mixed, **kwargs)
    for ch, radius in enumerate(radii, 1):
        center = np.array([30. + 10 * ch, 0.])
        policy.regions[ch] = np.array([center + [-radius, 0.],
                                       center + [radius, 0.]])
        # Seed exact public MEC values to exercise the skip boundary without
        # introducing geometry solver rounding into the accounting test.
        policy._circles[ch] = (center, radius)
    return policy


def task_order(policy):
    unused = list(range(len(policy.stations)))
    order = []
    while (task := policy.next_task(unused)) is not None:
        kind, key, position = task
        order.append((kind, key))
        policy.client.position = position
        if kind == "survey":
            unused.remove(key)
        else:
            policy.cleared.add(key)
    return order


class DiscoveryPriorityTests(unittest.TestCase):
    def test_default_order_matches_pre_fix_baseline(self):
        for cls, mixed in POLICIES:
            with self.subTest(policy=cls.__name__, mixed=mixed):
                policy = make_policy(cls, mixed)
                self.assertFalse(hasattr(policy, "clear_weight"))
                self.assertEqual(task_order(policy), BASELINE_ORDER)

    def test_precise_sources_get_no_duplicate_savings(self):
        for cls, mixed in POLICIES:
            for discovery_weight in (0., 900.):
                for choice_count in (4, 8):
                    with self.subTest(policy=cls.__name__, mixed=mixed,
                                      discovery=discovery_weight, choices=choice_count):
                        policy = make_policy(cls, mixed, discovery_weight=discovery_weight,
                                             choice_count=choice_count)
                        self.assertEqual(task_order(policy), BASELINE_ORDER)

    def test_removed_clear_weight_is_rejected(self):
        for cls, mixed in POLICIES:
            for weight in (0., 1., -1.):
                with self.subTest(policy=cls.__name__, mixed=mixed, weight=weight):
                    with self.assertRaisesRegex(TypeError, "clear_weight"):
                        make_policy(cls, mixed, clear_weight=weight)

    def test_zero_discovery_preserves_audit_d_route(self):
        rng = np.random.default_rng(99)
        for _ in range(8):
            points = rng.normal(size=(12, 2)) * 100
        # Audit D: promoting the shortlist changes survey 3 to survey 4 even
        # with no known source. Zero reward must bypass that promotion.
        for cls, mixed in POLICIES:
            for choice_count in (1, 4, 8):
                with self.subTest(policy=cls.__name__, mixed=mixed, choices=choice_count):
                    policy = cls(SimpleNamespace(position=np.array([0., 0.])), points,
                                 mixed=mixed, discovery_weight=0., choice_count=choice_count)
                    self.assertEqual(policy.next_task(list(range(12)))[:2], ("survey", 3))
                    self.assertEqual(policy.stats["discovery_priority_overrides"], 0)

    def test_current_experiment_candidates_build_without_retired_variants(self):
        from discovery_priority_experiments import SPECS, build
        removed = {3: {"discover300_clear7", "clear_reward7"},
                   4: {"discover900_clear22", "clear_reward22"}}
        for problem, methods in SPECS.items():
            self.assertTrue(removed[problem].isdisjoint(methods))
            self.assertEqual(len(methods), {3: 6, 4: 7}[problem])
            for name, spec in methods.items():
                with self.subTest(problem=problem, method=name):
                    self.assertNotIn("clear_weight", spec)
                    policy = build(SimpleNamespace(position=np.array([0., 0.])), spec,
                                   problem, {spec["layout"]: np.array([[0., 0.], [100., 0.]])})
                    self.assertFalse(hasattr(policy, "clear_weight"))

    def test_joint_scan_skips_exactly_the_already_precise_sources(self):
        policy = make_policy(radii=(*PRECISE_RADII, 20. - 5e-6, 20.))
        # Exercise the actual JointTaskPolicy.run scan loop, scheduling all
        # stations before completing sources so every skip is observable.
        def surveys_first(unused):
            if unused:
                return "survey", unused[0], policy.stations[unused[0]]
            pending = [ch for ch in policy.regions if ch not in policy.cleared]
            if pending:
                return "source", pending[0], policy.circle(pending[0])[0]
            return None

        policy.next_task = surveys_first
        policy.measure = Mock()
        policy.complete_source = policy.cleared.add
        result = JointTaskPolicy.run(policy)
        measured = [call.args[1] for call in policy.measure.call_args_list]
        for ch in (1, 2, 3):
            self.assertNotIn(ch, measured)
        # MEC<=20 alone is insufficient: values above 20-1e-5 still scan.
        for ch in range(4, 21):
            self.assertEqual(measured.count(ch), 3)
        self.assertEqual(result["skipped_precise_measurements"], 9)
        self.assertEqual(result["stations_visited"], 3)


if __name__ == "__main__":
    unittest.main()
