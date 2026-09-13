"""The two production strategies used in each problem's second formal test."""
import json
from pathlib import Path

import numpy as np
from coupled_dispatch_policy import CoupledWidthPolicy
from omni_negative_policy import OmniNegativeCompletionPolicy
from ring_coverage import stations

ROOT = Path(__file__).resolve().parent

# Historical experiments reproduce from their frozen packages, not this registry.
METHODS = {3: "range_area7", 4: "range_grid21_29"}
FORMAL_PARAMETERS = {
    3: dict(task_order="nearest", trial_radius=65., max_active=2,
            share_limit=6, localization_weight=.08, remainder_weight=1.5),
    4: dict(dispatch="nearest", trial_radius=35., share_limit=6,
            share_cooldown=150., transverse_m=40., fraction=.15, steps=10, pause_limit=16),
}
SPECS = {
    3: {"range_area7": dict(kind="coupled_completion", layout="ring7",
                           dispatch_model="base", range_skip=True,
                           area_prior=True, **FORMAL_PARAMETERS[3])},
    4: {"range_grid21_29": dict(kind="coupled_width", layout="grid21_29",
                               dispatch_model="base", range_skip=True,
                               **FORMAL_PARAMETERS[4])},
}


def actual_parameters(policy, problem):
    names = {"localization_weight": "time_weight", "steps": "bracket_steps"}
    return {key: getattr(policy, names.get(key, key)) for key in FORMAL_PARAMETERS[problem]}


def construct(problem, client):
    policy = build(client, SPECS[problem][METHODS[problem]], problem, load_paths(problem))
    if actual_parameters(policy, problem) != FORMAL_PARAMETERS[problem]:
        raise ValueError("Runtime parameters differ from formal test #2")
    return policy


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
        max_active = parameters.pop("max_active", None)
        if max_active is not None and (type(max_active) is not int or not 1 <= max_active <= 5):
            raise ValueError("Q3 primary localization budget must be an integer from 1 to 5")
        policy = OmniNegativeCompletionPolicy(client, points, mixed=False, **parameters)
        if max_active is not None:
            policy.max_active = max_active
        return policy
    if problem == 4:
        return CoupledWidthPolicy(client, points, mixed=True, **parameters)
    raise ValueError("Only problems 3 and 4 are registered")
