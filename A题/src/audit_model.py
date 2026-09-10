import ast
from dataclasses import replace
from pathlib import Path

import numpy as np

from data_io import CACHE, PROJECT, RESULTS, inputs, save_json
from model import Configuration, DryingModel


def main():
    checks = []
    for path in [*sorted((PROJECT / "src").glob("*.py")), PROJECT / "paper/build_paper.py"]:
        ast.parse(path.read_text(encoding="utf-8"))
    generator = np.random.default_rng(2026)
    for case, axial in ((1, 0), (3, 0), (4, 0), (3, 6), (4, 6)):
        model = DryingModel(Configuration(case=case, intervals=8, axial_intervals=axial))
        equilibrium = np.r_[np.full(model.count, 50.0), np.full(model.count, 0.05), 0.0]
        equilibrium_error = float(np.max(np.abs(model.derivative(20000, equilibrium))))
        assert equilibrium_error < 1e-12
        radial = np.repeat(model.radial[:, None], model.shape[1], axis=1).ravel()
        state = np.r_[40 + 6 * radial, 0.4 - 0.1 * radial, 0.0]
        direction = generator.normal(size=state.size)
        direction[-1] = 0
        displacement = 1e-5
        centered = (model.derivative(12345, state + displacement * direction) - model.derivative(12345, state - displacement * direction)) / (2 * displacement)
        colored = model.jacobian(12345, state) @ direction
        jacobian_error = float(np.max(np.abs(centered - colored)) / max(np.max(np.abs(centered)), 1e-12))
        assert jacobian_error < 2e-5
        derivative = model.derivative(12345, state)
        balance_residual = abs(float(model.weights @ derivative[model.count:2 * model.count] + derivative[-1]))
        assert balance_residual < 1e-12
        checks.append({"case": case, "axial_intervals": axial, "equilibrium_residual": equilibrium_error,
                       "jacobian_relative_error": jacobian_error, "instantaneous_balance_residual": balance_residual})
    air, radius = inputs()
    assert np.all(radius[:, 1] > 0)
    assert np.all(np.diff(radius[:, 1]) <= 0)
    field_checks = []
    for name in ("result1", "result2", "result2_full", "result3", "result4"):
        path = CACHE / f"{name}.npz"
        if not path.exists():
            continue
        with np.load(path) as data:
            temperature, moisture = data["temperature"], data["moisture"]
            assert np.nanmin(temperature) >= min(28, air[:, 1].min()) - 1e-5
            assert np.nanmax(temperature) <= max(50, air[:, 1].max()) + 1e-5
            assert np.nanmin(moisture) > 0 and np.nanmax(moisture) <= 2.55000001
            if name == "result4":
                outside = data["distances"][None, :] > data["surfaces"][:, :1] + 1e-9
                assert np.array_equal(outside, np.isnan(moisture))
            if name in ("result3", "result4"):
                assert np.nanmax(moisture[-1]) < 0.14995
            field_checks.append({"cache": name, "time_rows": len(data["times"]), "first_time_s": float(data["times"][0]),
                                 "last_time_s": float(data["times"][-1]), "temperature_min": float(np.nanmin(temperature)),
                                 "temperature_max": float(np.nanmax(temperature)), "moisture_min": float(np.nanmin(moisture)),
                                 "moisture_max": float(np.nanmax(moisture))})
    with np.load(CACHE / "result2.npz") as short, np.load(CACHE / "result2_full.npz") as full:
        overlap = {field: float(np.max(np.abs(short[field] - full[field][:len(short[field])]))) for field in ("temperature", "moisture", "times")}
        assert max(overlap.values()) < 1e-12
    save_json(RESULTS / "model_audit.json", {"seed": 2026, "structural_checks": checks, "output_range_checks": field_checks,
                                            "question2_full_short_maximum_difference": overlap})
    print("模型结构、Jacobian、全程输出范围和前三小时一致性核验完成", flush=True)


if __name__ == "__main__":
    main()
