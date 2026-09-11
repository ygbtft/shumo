"""The safety score must never forgive exclusion of an exact-feasible candidate."""
import unittest

from benchmarks_q34.oracle_localization import (
    conservative_negative_pass, negative_membership,
)


class NegativeContractTests(unittest.TestCase):
    def test_outer_posterior_acceptance_truth_table(self):
        for feasible, retained, expected in (
            (True, True, True), (True, False, False),
            (False, True, True), (False, False, True),
        ):
            with self.subTest(feasible=feasible, retained=retained):
                self.assertEqual(conservative_negative_pass(feasible, retained), expected)

    def test_closed_disk_truth_remains_exact(self):
        for distance, feasible in ((999.999, False), (1000, False),
                                   (1000.001, True), (1200, True)):
            with self.subTest(distance=distance):
                self.assertEqual(negative_membership([distance, 0], [0, 0], 3), feasible)
                self.assertTrue(negative_membership([distance, 0], [0, 0], 4))
