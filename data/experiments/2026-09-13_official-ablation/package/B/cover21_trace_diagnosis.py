"""Diagnose seen best and worst cases without exposing truth to any policy."""
import gzip
import json
import math
from client import Client
from cover21_confirmation import OUT,SPECS,all_paths,build


def diagnose(method, paths, case_id):
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
    destination=OUT/"regression_public_diagnosis.json"
    if destination.exists():raise RuntimeError("Preserving diagnoses")
    paths=all_paths();rows=[json.loads(s) for s in (OUT/"trials.jsonl").read_text().splitlines()]
    selected={}
    pairs=(("range_grid21_29","range_convex22"),("count_locked_grid21_29","range_grid21_29"),
           ("predict_grid21_29","range_grid21_29"),("range_grid21_7","range_convex22"),
           ("range_closed21_3","range_convex22"))
    for candidate,baseline in pairs:
        for split in ("ordinary","stress"):
            old={r["case_id"]:r for r in rows if (r["problem"],r["method"],r["split"])==(4,baseline,split)}
            current=[r for r in rows if (r["problem"],r["method"],r["split"])==(4,candidate,split)]
            chosen=max(current,key=lambda r:r["total_virtual_s"]-old[r["case_id"]]["total_virtual_s"])
            if chosen["total_virtual_s"]-old[chosen["case_id"]]["total_virtual_s"]>1e-6:
                selected.setdefault(chosen["case_id"],[]).append((candidate,baseline,"worst_regression",split))
            if candidate=="range_grid21_29":
                chosen=min(current,key=lambda r:r["total_virtual_s"]-old[r["case_id"]]["total_virtual_s"])
                selected.setdefault(chosen["case_id"],[]).append((candidate,baseline,"largest_observed_gain",split))
    results=[]
    for case,pairs in selected.items():
        methods=list(dict.fromkeys(m for c,b,role,split in pairs for m in (b,c)))
        records={name:diagnose(name,paths,case) for name in methods};comparisons=[]
        for candidate,baseline,role,split in pairs:
            delta={kind:{key:records[candidate]["task_costs"][kind][key]-records[baseline]["task_costs"][kind][key]
                         for key in records[candidate]["task_costs"][kind]} for kind in ("survey","source")}
            comparisons.append(dict(candidate=candidate,baseline=baseline,selection=role,split=split,task_cost_delta=delta,
                                    total_delta_s=records[candidate]["total_virtual_s"]-records[baseline]["total_virtual_s"]))
        results.append(dict(case_id=case,records=records,comparisons=comparisons))
        print(json.dumps(dict(case_id=case,stations={m:len(r["station_indices"]) for m,r in records.items()},comparisons=comparisons),ensure_ascii=False),flush=True)
    result=dict(role="Post-confirmation diagnosis of selected now-seen gains/regressions; no source truth is read",scored_executions=0,
                official_calls=0,replay_count=sum(len(c["records"]) for c in results),results=results)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
