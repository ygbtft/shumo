"""Only the two frozen Q3/Q4 candidates used by the delivery entry point."""
import json
from pathlib import Path

import numpy as np
from coupled_dispatch_policy import CoupledCompletionPolicy, CoupledWidthPolicy
from omni_negative_policy import OmniNegativeCompletionPolicy
from ring_coverage import stations

ROOT = Path(__file__).resolve().parent

# Copy the effective parameters, including the selected clear gates; historical
# experiment defaults (80/40 m) must not silently replace the current 50/35 m.
SPECS = {
    3: {"range_area7": dict(kind="coupled_completion", layout="ring7",
                           dispatch_model="base", range_skip=True,
                           trial_radius=50., area_prior=True, remainder_weight=1.5)},
    4: {"range_grid21_29": dict(kind="coupled_width", layout="grid21_29",
                               dispatch_model="base", range_skip=True,
                               fraction=.15, share_cooldown=150.,
                               transverse_m=40., trial_radius=35.)},
}


def load_paths(problem):
    # Load only the chosen layout. No certificate generation or experimental
    # JSON reads are needed at runtime. Preserve route order and float values.
    if problem == 3:
        return {"ring7": stations(6, 1140.)}
    if problem == 4:
        data = json.loads((ROOT / "layouts/grid21_29.json").read_text())
        return {"grid21_29": np.asarray(data["route"])}
    raise ValueError("Only problems 3 and 4 are registered")


def build(client, spec, problem, paths):
    # This single adapter retains bounded_http.run_http's factory contract.
    # There is deliberately no forwarding to historical experiment factories.
    parameters = spec.copy()
    parameters.pop("kind")
    points = paths[parameters.pop("layout")]
    if problem == 3:
        return OmniNegativeCompletionPolicy(client, points, mixed=False, **parameters)
    if problem == 4:
        return CoupledWidthPolicy(client, points, mixed=True, **parameters)
    raise ValueError("Only problems 3 and 4 are registered")
