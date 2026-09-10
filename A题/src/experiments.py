import argparse
from dataclasses import replace
import json
import platform
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import brentq
from scipy.special import j0, j1

from data_io import CACHE, PROJECT, RESULTS, inputs, save_json, sha256
from model import Configuration, DryingModel


def evaluate(config, end_time=None):
    result = DryingModel(config).run(end_time)
    summary = result.summary()
    assert summary["moisture_min"] > 0
    assert summary["moisture_max"] <= 2.55000001
    assert summary["balance_error"] < 1e-8
    print(config.case, config.intervals, config.axial_intervals, config.flux,
          summary["critical_time_h"], round(summary["elapsed_seconds"], 2), flush=True)
    return result, summary


def required_times(result):
    if result.model.config.case == 1:
        return np.array([100, 300, 600, 900, 1200, 1500, 1800], dtype=float)
    return np.unique(np.r_[np.arange(21600, result.stop_time, 21600), result.stop_time])


def table_records(result, times, distances):
    temperature, moisture, surface = result.profiles(times, distances)
    return {"time_s": times.tolist(), "distances_cm": list(distances),
            "temperature": [[None if np.isnan(value) else float(value) for value in row] for row in temperature],
            "moisture": [[None if np.isnan(value) else float(value) for value in row] for row in moisture],
            "surface": surface.tolist()}


def export_matrix(name, times, matrix, headings):
    path = CACHE / (name + ".json")
    values = np.c_[times, matrix]
    with path.open("w", encoding="utf-8") as stream:
        stream.write("[")
        stream.write(json.dumps(headings, ensure_ascii=False))
        for row in values:
            stream.write(",\n")
            stream.write(json.dumps([None if np.isnan(value) else float(round(value, 4)) for value in row], ensure_ascii=False, allow_nan=False))
        stream.write("]")
    return {"data": str(path.relative_to(PROJECT)).replace("\\", "/"), "rows": len(times) + 1, "columns": len(headings)}


def export_result(result, name, spacing, full=False):
    times = np.arange(spacing, result.stop_time + 0.01, spacing)
    if not full and name == "result2":
        times = np.arange(1, 10801)
    distances = np.arange(21) / 10
    temperature, moisture, surfaces = result.profiles(times, distances)
    np.savez_compressed(CACHE / (name + ".npz"), times=times, distances=distances,
                        temperature=temperature, moisture=moisture, surfaces=surfaces)
    header = ["时间/s 距中心/cm", *distances.tolist()]
    if name == "result4":
        moisture = np.c_[moisture[:, :-1], surfaces[:, 2]]
        header = ["时间/s 距中心/cm", *distances[:-1].tolist(), "药材表面"]
    sheets = []
    if name in ("result1", "result2", "result2_full"):
        sheets.append({"name": "温度", **export_matrix(name + "_temperature", times, temperature, header)})
        sheets.append({"name": "水分浓度", **export_matrix(name + "_moisture", times, moisture, header)})
    else:
        sheets.append({"name": "Sheet1", **export_matrix(name + "_moisture", times, moisture, header)})
    if name == "result4":
        sheets.append({"name": "半径", **export_matrix(name + "_radius", times, surfaces[:, :1], ["时间/s", "半径/cm"])})
    filename = {"result2": "result2_3h.xlsx", "result2_full": "result2.xlsx"}.get(name, name + ".xlsx")
    return {"filename": filename, "sheets": sheets}


def heat_benchmark(config):
    result, summary = evaluate(replace(config, case=1, constant_air=True), end_time=1800)
    biot = 25 * 0.02 / 0.36
    grid = np.linspace(0.001, 320, 30000)
    characteristic = grid * j1(grid) - biot * j0(grid)
    indices = np.flatnonzero(characteristic[:-1] * characteristic[1:] < 0)
    roots = np.array([brentq(lambda value: value * j1(value) - biot * j0(value), grid[index], grid[index + 1]) for index in indices])
    coefficients = 2 * j1(roots) / (roots * (j0(roots)**2 + j1(roots)**2))
    times = np.array([1, 5, 10, 30, 100, 300, 600, 1800], dtype=float)
    distances = np.arange(21) / 10
    analytical = 50 - 22 * (np.exp(-np.outer(times, roots**2) * (0.36 / (820 * 2600)) / 0.02**2) * coefficients) @ j0(np.outer(roots, distances / 2))
    computed = result.profiles(times, distances)[0]
    return {"intervals": config.intervals, "maximum_absolute_error_C": float(np.max(np.abs(computed - analytical))),
            "errors_by_time_C": np.max(np.abs(computed - analytical), axis=1).tolist(), "times_s": times.tolist(), "series_terms": len(roots)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["production", "validation", "sensitivity", "axial", "all"], default="all")
    parser.add_argument("--intervals", type=int, default=1024)
    parser.add_argument("--full-second-output", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    base = Configuration(intervals=args.intervals)
    if args.stage in ("production", "all"):
        summaries, tables, exports = {}, {}, []
        for case, name in ((1, "result1"), (3, "result3"), (4, "result4")):
            result, summary = evaluate(replace(base, case=case))
            summaries[name] = summary
            tables[name] = table_records(result, required_times(result), [0, 0.5, 1, 1.5, 2])
            exports.append(export_result(result, name, 1 if case == 1 else 60))
            if case == 3:
                tables["result2"] = table_records(result, np.arange(1800, 10801, 1800), [0, 0.5, 1, 1.5, 2])
                exports.append(export_result(result, "result2", 1))
                if args.full_second_output:
                    exports.append(export_result(result, "result2_full", 1, full=True))
        save_json(RESULTS / "production.json", {"summaries": summaries, "tables": tables})
        save_json(CACHE / "export_manifest.json", exports)
    if args.stage in ("validation", "all"):
        comparisons, benchmark = [], []
        for case in (1, 3, 4):
            previous = None
            for intervals in (256, 512, 1024, 2048):
                result, summary = evaluate(replace(base, case=case, intervals=intervals))
                times = np.arange(1, 1801) if case == 1 else np.unique(np.r_[np.arange(1, 10801), np.arange(10860, result.stop_time + 0.01, 60)])
                temperature, moisture, surface = result.profiles(times, np.arange(21) / 10)
                values = (np.c_[temperature, surface[:, 1]], np.c_[moisture, surface[:, 2]])
                comparison = {"case": case, "intervals": intervals, "summary": summary,
                              "sampled_times": len(times), "last_sample_s": float(times[-1]),
                              "includes_moving_surface": True}
                if previous is not None:
                    common, current_indices, previous_indices = np.intersect1d(times, previous[2], return_indices=True)
                    comparison["temperature_difference_C"] = float(np.nanmax(np.abs(values[0][current_indices] - previous[1][0][previous_indices])))
                    comparison["moisture_difference"] = float(np.nanmax(np.abs(values[1][current_indices] - previous[1][1][previous_indices])))
                    comparison["comparison_last_sample_s"] = float(common[-1])
                    if case != 1:
                        comparison["critical_time_difference_s"] = abs(summary["critical_time_s"] - previous[0]["critical_time_s"])
                comparisons.append(comparison)
                previous = summary, values, times
                save_json(RESULTS / "convergence.json", comparisons)
        for intervals in (256, 512, 1024):
            benchmark.append(heat_benchmark(replace(base, intervals=intervals)))
        save_json(RESULTS / "heat_benchmark.json", benchmark)
        contrast = []
        for flux in ("harmonic", "kirchhoff"):
            for intervals in (80, 160):
                result, summary = evaluate(replace(base, case=3, intervals=intervals, grid="uniform", flux=flux, rtol=1e-8))
                contrast.append(summary)
        for case in (3, 4):
            for method in ("BDF", "Radau"):
                result, summary = evaluate(replace(base, case=case, intervals=128, method=method, rtol=1e-8))
                contrast.append(summary)
        save_json(RESULTS / "method_comparison.json", contrast)
    if args.stage in ("sensitivity", "all"):
        experiments = []
        for case in (3, 4):
            specifications = [("baseline", {}), ("air_T_minus1", {"temperature_shift": -1}),
                              ("air_T_plus1", {"temperature_shift": 1}),
                              ("air_C_minus_001", {"moisture_shift": -0.001}),
                              ("air_C_plus_001", {"moisture_shift": 0.001}),
                              ("mass_transfer_minus10pct", {"mass_transfer_scale": 0.9}),
                              ("mass_transfer_plus10pct", {"mass_transfer_scale": 1.1}),
                              ("diffusivity_minus10pct", {"diffusivity_scale": 0.9}),
                              ("diffusivity_plus10pct", {"diffusivity_scale": 1.1}),
                              ("last_observation_plateau", {"plateau": "last"}),
                              ("tail_mean_plateau", {"plateau": "tail_mean"}),
                              ("joint_adverse", {"temperature_shift": -1, "moisture_shift": 0.001,
                                                  "mass_transfer_scale": 0.9, "diffusivity_scale": 0.9})]
            if case == 4:
                specifications += [("no_shrinkage", {"radius_mode": "fixed"}), ("linear_radius", {"radius_mode": "linear"})]
            for name, changes in specifications:
                result, summary = evaluate(replace(base, case=case, intervals=256, rtol=1e-8, **changes))
                experiments.append({"name": name, **summary})
                save_json(RESULTS / "sensitivity.json", experiments)
    if args.stage in ("axial", "all"):
        comparisons = []
        for intervals, axial_intervals in ((32, 24), (64, 40)):
            for case in (3, 4):
                result, summary = evaluate(replace(base, case=case, intervals=intervals, axial_intervals=axial_intervals, rtol=2e-7))
                reference, reference_summary = evaluate(replace(base, case=case, intervals=intervals, rtol=2e-7))
                snapshot = result.states([result.critical_time])[:, 0]
                comparison = {"summary": summary, "matched_1d_summary": reference_summary,
                              "relative_time_change": summary["critical_time_s"] / reference_summary["critical_time_s"] - 1,
                              "table": table_records(result, required_times(result), [0, 0.5, 1, 1.5, 2]),
                              "radial_cm": (result.model.radial * result.model.radius(result.critical_time) * 100).tolist(),
                              "axial_cm": (result.model.axial * 12.5).tolist(),
                              "moisture_at_critical": snapshot[result.model.count:2 * result.model.count].reshape(result.model.shape).tolist()}
                comparisons.append(comparison)
                save_json(RESULTS / "axial_comparison.json", comparisons)
    air, radius = inputs()
    save_json(RESULTS / "provenance.json", {
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "air_observations": len(air), "radius_observations": len(radius),
        "input_sha256": {str(path.relative_to(PROJECT)).replace("\\", "/"): sha256(path) for path in (PROJECT / "附件/附件1.xlsx", PROJECT / "附件/附件2.xlsx", PROJECT / "A题.pdf")},
        "scope": "题设有效输运模型；不是实验标定后的真实药材预测；没有使用GPU。",
    })


if __name__ == "__main__":
    main()
