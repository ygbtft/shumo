"""Reorder unvisited coverage stations using accepted public position only."""
import time
import numpy as np
from policies import Policy


def remaining_route(points, current, polish=False):
    points = np.asarray(points)
    n = len(points)
    distances = np.linalg.norm(points[:, None]-points[None, :], axis=2)
    start = np.linalg.norm(points-np.asarray(current), axis=1)
    unused = list(range(n))
    path = []
    while unused:
        costs = start[unused] if not path else distances[path[-1], unused]
        path.append(unused.pop(int(np.argmin(costs))))
    path = np.array(path, dtype=int)
    if polish:
        for _ in range(3):
            changed = False
            for i in range(n-1):
                for j in range(i+1, n):
                    # Open route from the accepted current position, with a free end.
                    # Symmetric internal edges cancel; suffix reversal has no return edge.
                    if i == 0:
                        delta = start[path[j]]-start[path[i]]
                    else:
                        delta = distances[path[i-1], path[j]]-distances[path[i-1], path[i]]
                    if j+1 < n:
                        delta += distances[path[i], path[j+1]]-distances[path[j], path[j+1]]
                    if delta < -1e-7:
                        path[i:j+1] = path[i:j+1][::-1]
                        changed = True
            if not changed:
                break
    return path


class AdaptiveOrder:
    def __init__(self, client, points, polish):
        self.client, self.points, self.polish = client, np.asarray(points).copy(), polish
        self.compute_s, self.replans = 0., 0
        self.visited_original_indices = []

    def __len__(self):
        return len(self.points)

    def __iter__(self):
        unused = list(range(len(self.points)))
        while unused:
            start = time.perf_counter()
            # Last accepted position incorporates localisation/clearing detours.
            path = remaining_route(self.points[unused], self.client.position, self.polish)
            index = unused.pop(int(path[0]))
            self.compute_s += time.perf_counter()-start
            self.replans += 1
            self.visited_original_indices.append(index)
            yield self.points[index]


class AdaptivePolicy(Policy):
    def __init__(self, client, stations, polish=False, **kwargs):
        super().__init__(client, stations, **kwargs)
        self.stations = AdaptiveOrder(client, stations, polish)

    def run(self):
        stats = super().run()
        visited = self.stations.visited_original_indices
        assert len(set(visited)) == len(visited)
        stats.update(route_compute_s=self.stations.compute_s, route_replans=self.stations.replans,
                     visited_original_indices=visited)
        return stats
