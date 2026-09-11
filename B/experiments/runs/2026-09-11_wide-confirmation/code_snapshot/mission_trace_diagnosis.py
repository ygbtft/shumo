"""Public-feedback task accounting for an explicitly reused slow case.

This is post-confirmation diagnosis, not another held-out experiment. It reads
no source truth and generates no new scene or benchmark score.
"""
import gzip
import json
import math
from pathlib import Path

from client import Client
from clearance_experiments import build
from mission_confirmation import OUT, SPECS, all_paths


def diagnose(method, paths):
    case_id = "uniform__iid__93"
    with gzip.open(OUT / "traces" / f"q4__{case_id}__{method}.jsonl.gz", "rt") as stream:
        trace = [json.loads(line) for line in stream]
    index = 0
    events = []

    def replay(endpoint, raw):
        nonlocal index
        entry = trace[index]
        assert endpoint == entry["path"] and json.loads(raw) == entry["request"], (method, index)
        index += 1
        return 200, entry["response"]

    policy = build(Client(replay, robot_id="mock-robot"), SPECS[4][method], 4, paths)
    original_next_task = policy.next_task

    def finish_previous():
        if events and "after_command" not in events[-1]:
            events[-1].update(after_command=index, finish_virtual_s=policy.client.virtual_s,
                              known_after=len(set(policy.regions) | policy.cleared),
                              cleared_after=len(policy.cleared))

    def next_task(unused):
        finish_previous()
        chosen = original_next_task(unused)
        if chosen is not None:
            kind, key, p = chosen
            events.append(dict(kind=kind, key=int(key), prediction=[float(x) for x in p],
                               before_command=index, start_virtual_s=policy.client.virtual_s,
                               known_before=len(set(policy.regions) | policy.cleared),
                               cleared_before=len(policy.cleared),
                               actual_region_radius_m=policy.circle(key)[1] if kind == "source" else None))
        return chosen

    policy.next_task = next_task
    stats = policy.run()
    finish_previous()
    assert index == len(trace)
    totals = {kind: dict(move_m=0., measure_s=0, switch_s=0, clear_s=0, commands=0, virtual_s=0.)
              for kind in ("survey", "source")}
    for event in events:
        begin, end = event["before_command"], event["after_command"]
        costs = dict(move_m=0., measure_s=0, switch_s=0, clear_s=0, commands=0)
        for i in range(begin, end):
            entry = trace[i]
            request, reply = entry["request"], entry["response"]
            if "position" not in request:
                continue
            q = [request["position"]["x"], request["position"]["y"]]
            costs["move_m"] += math.dist(q, trace[i - 1]["position"])
            if entry["path"] == "/measure":
                costs["measure_s"] += 5
                last_channel = 1
                for previous in reversed(trace[:i]):
                    if previous["path"] == "/measure":
                        last_channel = previous["request"]["channel"]
                        break
                costs["switch_s"] += int(request["channel"] != last_channel)
            else:
                costs["clear_s"] += 5 if reply["clear_result"] == "success" else 3
            costs["commands"] += 1
        costs["virtual_s"] = event["finish_virtual_s"] - event["start_virtual_s"]
        event["costs"] = costs
        for key, value in costs.items():
            totals[event["kind"]][key] += value
    assert abs(sum(t["virtual_s"] for t in totals.values()) - policy.client.virtual_s) < 1e-6
    return dict(total_virtual_s=policy.client.virtual_s, commands=len(trace),
                station_indices=[event["key"] for event in events if event["kind"] == "survey"],
                first_known_16_task=next((i for i, event in enumerate(events) if event["known_after"] == 16), None),
                task_costs=totals, stats=stats, tasks=events)


def main():
    paths = all_paths()
    methods = {method: diagnose(method, paths) for method in ("fast22", "quarter22")}
    delta = {kind: {key: methods["quarter22"]["task_costs"][kind][key] - methods["fast22"]["task_costs"][kind][key]
                    for key in methods["fast22"]["task_costs"][kind]} for kind in ("survey", "source")}
    result = dict(case_id="q4__uniform__iid__93", role="Explicitly reused confirmation case; public-feedback diagnosis only",
                  methods=methods, quarter_minus_fast=delta, scored_executions=0, official_calls=0,
                  interpretation="The probe parameter changes later public observations and task order. Extra scan visits explain much of the recorded gap; this accounting alone does not prove a parameter intervention will improve unseen scenes.")
    destination = OUT / "reused_slow_case_task_diagnosis.json"
    if destination.exists():
        raise RuntimeError("Preserving diagnosis")
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(dict(case=result["case_id"], methods={k: {n: v[n] for n in ("total_virtual_s", "station_indices", "task_costs")} for k, v in methods.items()},
                          delta=delta, scored_executions=0, official_calls=0), indent=2))


if __name__ == "__main__":
    main()
