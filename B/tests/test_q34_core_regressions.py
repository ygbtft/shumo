"""Audited P2 geometry, GA and local mock regressions."""
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from coverage import segment_distance_origin, triangle_intersects_disk, route_length
from geometry import minimum_circle_enumerated
from intelligent import genetic_route
from simulator import Protocol, Source, World


class GeometryTests(unittest.TestCase):
    def test_enumerated_circle_encloses_all_points(self):
        for points, expected in (
            ([[0., 0.], [1e-8, 0.]], 5e-9),
            ([[0., 0.], [0., 0.]], 0.),
            ([[-1., 0.], [0., 0.], [1., 0.]], 1.),
            ([[0., 0.], [2., 0.], [1., np.sqrt(3)]], 2 / np.sqrt(3)),
        ):
            with self.subTest(points=points):
                center, radius = minimum_circle_enumerated(points)
                # No positive tolerance here: the returned circle must contain inputs.
                self.assertTrue(np.all(np.linalg.norm(np.asarray(points)-center, axis=1) <= radius))
                if expected:
                    self.assertAlmostEqual(radius / expected, 1., places=12)
                else:
                    self.assertEqual(radius, 0.)

    def test_zero_length_segment(self):
        with np.errstate(all='raise'):
            for point, expected in (([10., 0.], 10.), ([0., 0.], 0.)):
                self.assertEqual(segment_distance_origin(np.array(point), np.array(point)), expected)

    def test_degenerate_and_regular_triangles(self):
        cases = (
            ([[10., 0.], [11., 0.], [12., 0.]], False),
            ([[10., 0.]] * 3, False),
            ([[0., 0.]] * 3, True),
            ([[-2., 0.], [2., 0.], [2., 0.]], True),
            ([[-2., 1.], [2., 1.], [0., 1.]], True),
            ([[-2., 1.01], [2., 1.01], [0., 1.01]], False),
            ([[-2., -2.], [2., -2.], [0., 2.]], True),
            ([[10., 0.], [11., 0.], [10., 1.]], False),
        )
        for triangle, expected in cases:
            for vertices in (triangle, triangle[::-1]):
                with self.subTest(vertices=vertices):
                    self.assertEqual(triangle_intersects_disk(vertices, 1.), expected)


class GeneticRouteTests(unittest.TestCase):
    def test_empty_singleton_and_duplicate_stations(self):
        for points in ([], [[3., 4.]], [[3., 4.]] * 3,
                       [[0., 0.], [0., 0.], [1., 0.]],
                       [[3., 4.], [1., 2.], [3., 4.], [-1., 0.], [1., 2.]]):
            with self.subTest(points=points):
                result, info = genetic_route(points, population=16, generations=3)
                self.assertEqual(result.shape, (len(set(map(tuple, points))), 2))
                self.assertEqual(set(map(tuple, result)), set(map(tuple, points)))
                self.assertEqual(info['best_m'], route_length(result))
                self.assertLessEqual(info['best_m'], info['initial_2opt_m'] + 1e-6)


class MockIdempotencyTests(unittest.TestCase):
    def test_retry_waiting_before_lock_replays_first_response(self):
        for conflict in (False, True):
            with self.subTest(conflict=conflict):
                world = World([Source(1, 100., 0.)])
                protocol = Protocol(world)
                base = dict(arena_id='default', robot_id='offline-robot')
                protocol.dispatch('/enter', json.dumps(dict(base, request_id='enter')).encode())
                payload = dict(base, request_id='same', position=dict(x=0., y=0.), channel=1)
                raw = json.dumps(payload).encode()
                waiting, done = threading.Event(), threading.Event()
                lock = threading.Lock()

                class ScheduledLock:
                    def acquire(self, blocking=False):
                        if threading.current_thread().name.startswith('delayed'):
                            waiting.set()
                            if not done.wait(5):
                                raise RuntimeError('schedule timeout')
                        return lock.acquire(blocking=blocking)

                    def release(self):
                        lock.release()

                protocol.lock = ScheduledLock()
                # Force A to reach acquisition first, but B to execute and cache first.
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix='delayed') as pool:
                    pending = pool.submit(protocol.dispatch, '/measure', raw)
                    try:
                        self.assertTrue(waiting.wait(5))
                        if conflict:
                            payload['channel'] = 2
                        first = protocol.dispatch('/measure', json.dumps(payload).encode())
                    finally:
                        done.set()
                    second = pending.result(timeout=5)
                self.assertEqual(first[0], 200)
                if conflict:
                    self.assertEqual(second[0], 409)
                else:
                    self.assertEqual(second, first)
                    self.assertEqual(protocol.dispatch('/measure', raw), first)
                self.assertEqual(world.measures, 1)
                self.assertEqual(world.commands, 2)
                self.assertEqual(world.time_us, 6_000000 if conflict else 5_000000)


if __name__ == '__main__':
    unittest.main()
