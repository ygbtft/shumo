"""Independent public-feedback checks including public source-count certificates."""
import json
import math
import numpy as np
from client import Client
from faithful_skip_experiments import request_identity


def whole_polygon_distance(poly, q):
    edges = np.roll(poly,-1,axis=0)-poly
    v = q-poly
    norm2 = np.sum(edges*edges,axis=1)
    factors = np.sum(v*edges,axis=1)/np.maximum(norm2,1e-30)
    nearest = poly+np.clip(factors,0,1)[:,None]*edges
    distance = float(np.linalg.norm(nearest-q,axis=1).min())
    area2 = abs(np.sum(poly[:,0]*np.roll(poly,-1,axis=0)[:,1]-poly[:,1]*np.roll(poly,-1,axis=0)[:,0]))
    if area2 > 1e-8 and np.min(edges[:,0]*v[:,1]-edges[:,1]*v[:,0]) >= 0:
        return 0.
    return distance


def independent_pair(poly, q, a, b):
    for g in poly:
        assert max(np.linalg.norm(g-a),np.linalg.norm(g-b)) <= np.linalg.norm(g-q)+1e-7
        u,v = np.linalg.solve(np.column_stack((g-q,-(b-a))),a-q)
        assert -1e-7 <= u <= 1.+1e-7 and -1e-7 <= v <= 1.+1e-7


def physical_path(trace):
    points = [(0.,0.)]
    for entry in trace:
        p = entry["request"].get("position")
        if p is not None:
            q = p["x"],p["y"]
            if q != points[-1]:
                points.append(q)
    return points


def expanded_plan(trace, spec, problem, paths, build):
    index = 0
    skipped = []
    known_negatives = set()
    known_positive = set()
    actual = []
    range_count = pair_count = empty_count = nonstationary = 0

    def position(entry):
        p = entry["request"]["position"]
        return p["x"],p["y"]

    def note(entry):
        if entry["path"] == "/measure" and entry["response"]["measure_result"] in ("direction","near"):
            known_positive.add(entry["request"]["channel"])
        if entry["path"] == "/measure" and entry["response"]["measure_result"] == "no_signal":
            known_negatives.add((entry["request"]["channel"],position(entry)))

    def transport(endpoint, raw):
        nonlocal index
        req = json.loads(raw)
        entry = trace[index]
        assert (endpoint,req.get("position"),req.get("channel")) == request_identity(entry), index
        note(entry)
        actual.append(entry)
        index += 1
        return 200,entry["response"]

    client = Client(transport,robot_id="mock-robot")
    policy = build(client,spec,problem,paths)
    original = policy.measure

    def measure(q,ch):
        nonlocal index,range_count,pair_count,empty_count,nonstationary
        before = client.position,client.channel,client.virtual_s,client.sequence
        poly = policy.regions[ch].copy() if ch in policy.regions else None
        was_surveying = policy._surveying
        result = original(q,ch)
        if result == "certified_no_reception":
            entry = trace[index]
            assert entry["path"] == "/measure" and entry["request"]["channel"] == ch
            assert np.array_equal(q,position(entry)) and entry["response"]["measure_result"] == "no_signal"
            assert before == (client.position,client.channel,client.virtual_s,client.sequence)
            assert was_surveying and ch not in policy.cleared
            assert np.array_equal(policy._attempted[ch][-1],q) and policy._planned_channel == ch
            if hasattr(policy,"_last_negative"):
                assert np.array_equal(policy._last_negative[ch],q)
            certificate = policy._last_skip_certificate
            if certificate["kind"] == "public_16_bound":
                assert poly is None and ch not in known_positive and len(known_positive)==16
                assert set(certificate["discovered_channels"])==known_positive
                assert np.array_equal(q,before[0])
                empty_count += 1
            elif certificate["kind"] == "range":
                assert poly is not None
                assert whole_polygon_distance(poly,np.asarray(q)) > 1500.-1e-5
                range_count += 1
            else:
                assert poly is not None
                a,b = certificate["a"],certificate["b"]
                assert (ch,tuple(a)) in known_negatives and (ch,tuple(b)) in known_negatives
                independent_pair(poly,np.asarray(q),a,b)
                pair_count += 1
            nonstationary += int(not np.array_equal(q,before[0]))
            note(entry)
            skipped.append(index)
            index += 1
        return result

    policy.measure = measure
    stats = policy.run()
    assert index == len(trace) and stats["certified_scan_skips"] == len(skipped)
    assert range_count == stats["certified_range_scan_skips"] and pair_count == stats["predicted_pair_skips"]
    assert nonstationary == stats["deferred_nonstationary_skips"]
    assert stats["minimum_unknown_actions_per_station"] >= 4
    assert empty_count == stats["public_empty_scan_skips"]
    assert physical_path(trace) == physical_path(actual)
    return dict(logical_commands=len(trace),actual_commands=client.sequence,skipped=len(skipped),
                range_skips=range_count,pair_skips=pair_count,public_empty_skips=empty_count,nonstationary_skips=nonstationary,
                skipped_indices=skipped,physical_movement_path_equal=True,
                minimum_actual_unknown=stats["minimum_actual_unknown_per_station"],
                minimum_unknown_actions=stats["minimum_unknown_actions_per_station"])


def verify_actual_cost(reference, actual, detail, virtual_before, virtual_after):
    omitted = set(detail["skipped_indices"])
    reduced = [entry for i,entry in enumerate(reference) if i not in omitted]
    assert [request_identity(e) for e in reduced] == [request_identity(e) for e in actual]
    assert physical_path(reference) == physical_path(actual)
    def switches(trace):
        channels = [1]+[e["request"]["channel"] for e in trace if e["path"] == "/measure"]
        return sum(a != b for a,b in zip(channels,channels[1:]))
    switch_saved = switches(reference)-switches(actual)
    assert switch_saved >= 0
    k = detail["skipped"]
    assert len(reference)-len(actual) == k
    assert abs(virtual_before-virtual_after-(5*k+switch_saved)) < 1e-6
    return dict(skipped=k,switch_saved=switch_saved,virtual_saved_s=virtual_before-virtual_after)
