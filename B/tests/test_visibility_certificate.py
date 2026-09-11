"""Coverage prerequisites, strict geometry, and frozen main-path regressions."""
import copy
import json
from pathlib import Path
import unittest

from visibility_certificate import certify_layout_coverage, verify_cells
from icra_final_checks import partition_check


class CoverageCertificateTests(unittest.TestCase):
    def setUp(self):
        self.points = []
        cells = []
        # Full depth-three root partition, with four strictly enclosing sites
        # per square. Adjacent leaves share edges, not interiors.
        for x in range(-1575, 1800, 450):
            for y in range(-1575, 1800, 450):
                ids = list(range(len(self.points), len(self.points)+4))
                self.points.extend([[x+dx*245, y+dy*245]
                                    for dx, dy in ((-1,-1),(1,-1),(1,1),(-1,1))])
                cells.append([x, y, 225., ids])
        self.cert = dict(covered=True, arena_radius=1800., receive_radius=1000., cells=cells)

    def certify(self, cert=None, **overrides):
        context = dict(layout_points=self.points, route=self.points[::-1], problem=4, layout_problem=4)
        context.update(overrides)
        return certify_layout_coverage(self.points, self.cert if cert is None else cert, **context)

    def test_complete_partition_and_qualified_leaves(self):
        result = self.certify()
        self.assertTrue(result['coverage_guarantee'])
        self.assertEqual(result['verified_leaves'], 64)
        self.assertEqual(result['certified_area_m2'], 3600**2)

    def test_legacy_entry_explicitly_withholds_layout_guarantee(self):
        result = verify_cells(self.points, self.cert)
        self.assertFalse(result['coverage_guarantee'])
        self.assertTrue(result['missing_requirements'])

    def test_partial_partition_is_rejected_by_both_entries(self):
        self.cert['cells'] = [self.cert['cells'][27]]
        for check in (lambda: verify_cells(self.points, self.cert), self.certify):
            with self.assertRaisesRegex(ValueError, 'incomplete partition'):
                check()

    def test_distance_at_or_above_1000_and_inward_margin(self):
        for distance in (1000., 1001., 1000.-5e-6):
            with self.subTest(distance=distance):
                # Against the opposite corner (x+225,y+225).
                self.points[0] = [-1575+225-distance, -1575+225]
                with self.assertRaisesRegex(ValueError, 'receiving distance'):
                    self.certify()

    def test_hull_exclusion_and_inward_margin(self):
        for half in (100., 225., 225.+5e-6):
            with self.subTest(half=half):
                for i, (dx,dy) in enumerate(((-1,-1),(1,-1),(1,1),(-1,1))):
                    self.points[i] = [-1575+dx*half, -1575+dy*half]
                with self.assertRaisesRegex(ValueError, 'inside hull'):
                    self.certify()

    def test_missing_context(self):
        for field in ('layout_points', 'route', 'problem', 'layout_problem'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                self.certify(**{field: None})

    def test_problem_and_coordinate_mismatches(self):
        for context in ({'problem': 3}, {'layout_problem': 3},
                        {'layout_points': self.points[:-1]}, {'route': self.points[:-1]}):
            with self.subTest(context=list(context)), self.assertRaises(ValueError):
                self.certify(**context)

    def test_duplicate_overlapping_and_off_tree_leaves(self):
        for extra in (self.cert['cells'][0], [0.,0.,1800.,[0,1,2,3]],
                      [1.,1.,225.,[0,1,2,3]]):
            cert = copy.deepcopy(self.cert)
            cert['cells'].append(extra)
            with self.subTest(extra=extra[:3]), self.assertRaisesRegex(ValueError, 'partition'):
                self.certify(cert)

    def test_invalid_geometry_metadata(self):
        for field, value in (('cells', []), ('cells', None), ('covered', False),
                             ('arena_radius', 1799.), ('receive_radius', 1001.)):
            cert = {**self.cert, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.certify(cert)
        for half in (0., -1., float('nan'), float('inf')):
            cert = copy.deepcopy(self.cert)
            cert['cells'][0][2] = half
            with self.subTest(half=half), self.assertRaises(ValueError):
                self.certify(cert)

    def test_frozen_icra_partition_and_leaf_checks_still_pass(self):
        root = Path(__file__).resolve().parents[1]
        layouts = json.loads((root/'experiments/runs/2026-09-11_convex-visibility/certified_layouts.json').read_text())
        self.assertEqual(len(layouts), 11)
        for name, item in layouts.items():
            with self.subTest(layout=name):
                verified = verify_cells(item['points'], item['certificate'])
                partition = partition_check(item['certificate'])
                self.assertEqual(verified['verified_leaves'], partition['cells'])
                # Existing disk certificates cannot claim full-square coverage.
                with self.assertRaisesRegex(ValueError, 'root-square partition'):
                    certify_layout_coverage(item['points'], item['certificate'],
                        layout_points=item['points'], route=item['route'], problem=4, layout_problem=4)


if __name__ == '__main__':
    unittest.main()
