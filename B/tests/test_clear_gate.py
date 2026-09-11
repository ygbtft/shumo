"""Selected configuration wiring and paired protocol regression checks."""
import unittest

from clear_gate_sweep import BASELINE, METHODS, builders, cases, execute
from client import Client
from peer_benchmark import PeerTransport
from mock.error_field import ErrorConfig, ErrorField
from mock.scenario_gen import Scenario
from mock.simulator import Limits, Simulator
from mock.protocol import Protocol


class ClearGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = builders.all_paths()

    def test_selected_factory_and_baseline_override(self):
        for problem, selected, name, stations in (
            (3, 50., "CoupledCompletionPolicy", 7),
            (4, 35., "CoupledWidthPolicy", 21),
        ):
            fixture = next(cases(problem, 1, 202630000))
            scenario = Scenario.from_dict(fixture["scenario"])
            for radius in (selected, BASELINE[problem], 0.):
                with self.subTest(problem=problem, radius=radius):
                    sim = Simulator(scenario, ErrorField(scenario.seed, ErrorConfig()), Limits(countdown_s=0))
                    spec = builders.SPECS[problem][METHODS[problem]].copy()
                    if radius != selected:
                        spec["trial_radius"] = radius
                    policy = builders.build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"),
                                            spec, problem, self.paths)
                    self.assertEqual(type(policy).__name__, name)
                    self.assertEqual(len(policy.stations), stations)
                    self.assertEqual(policy.trial_radius, radius)
                    if problem == 4:
                        self.assertEqual(policy.bracket_trial_radius, radius)

    def test_default_equals_explicit_gate_and_clears_every_source(self):
        # Independent fixtures include 10/13/16 sources and ±1° endpoint fields.
        for problem, selected in ((3, 50.), (4, 35.)):
            fixtures = list(cases(problem, 1, 202630000))
            spec = builders.SPECS[problem][METHODS[problem]]
            for index in (0, 2, 3, 49, 92, 93):
                fixture = fixtures[index]
                with self.subTest(problem=problem, index=index):
                    default = execute((problem, None, fixture, spec, self.paths))
                    explicit = execute((problem, selected, fixture, spec, self.paths))
                    self.assertTrue(default["all_cleared"])
                    self.assertFalse(default["failure"])
                    for key in ("radius", "cleared", "total_virtual_s", "clear_failure_count", "stats", "clear_events"):
                        self.assertEqual(default[key], explicit[key], key)
                    self.assertFalse(any(e["certified"] and not e["success"] for e in default["clear_events"]))


if __name__ == "__main__":
    unittest.main()
