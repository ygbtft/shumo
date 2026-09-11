"""Read-only audit of the supplied b-branch recording; never sends its identity anywhere."""
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PEER=ROOT/"reference/shumo-b"
OUT=ROOT/"experiments/runs/2026-09-10_peer-benchmark"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=PEER/"practice-logs/session-20260910/requests.jsonl"
    raw=path.read_bytes()
    rows=[json.loads(line) for line in raw.splitlines()]
    position=(0.,0.); channel=1; last_us=0; mismatches=[]; residuals=[]; seen={}; repetitions=0
    outcomes=Counter(); failures=[]; clears=set(); discovered=set(); per_step=[]
    for i,row in enumerate(rows):
        response=row["response"]
        assert row["http_status"]==200 and response["accepted"] is True
        assert row["sequence"]==i and response==json.loads(row["response_raw_utf8"])
        assert row["request_id"]==row["request"]["request_id"]
        assert row["session_mode"]=="practice"
        if i:
            assert rows[i-1]["local_end_timestamp_ms"]<=row["local_start_timestamp_ms"]
        action=row["action"]
        current_us=int(Decimal(str(response["virtual_time_s"]))*1000000)
        expected_us=0; floating_s=0.
        if action in ("/measure","/clear"):
            q=(row["request"]["position"]["x"],row["request"]["position"]["y"])
            ch=row["request"]["channel"]
            move=math.dist(position,q)/5
            if action=="/measure":
                result=response["measure_result"]
                fee=5+int(ch!=channel); channel=ch
                assert ("svd_deg" in response)==(result=="direction")
                if result in ("near","direction"):
                    discovered.add(ch)
                if result=="direction":
                    key=(q,ch)
                    if key in seen:
                        repetitions+=1
                        if seen[key]!=response["svd_deg"]:
                            failures.append({"sequence":i,"rule":"fixed_error"})
                    seen[key]=response["svd_deg"]
            else:
                result=response["clear_result"]
                fee=5 if result=="success" else 3
                if result=="success":
                    clears.add(ch)
            outcomes[result]+=1
            floating_s=move+fee
            expected_us=math.floor(move*1000000+.5)+fee*1000000
            position=q
        observed_us=current_us-last_us
        if expected_us!=observed_us:
            mismatches.append({"sequence":i,"expected_us":expected_us,"observed_us":observed_us})
        residuals.append(observed_us/1000000-floating_s)
        per_step.append({"sequence":i,"action":action,"expected_delta_us":expected_us,
                         "observed_delta_us":observed_us,"difference_us":observed_us-expected_us})
        last_us=current_us
    assert len({r["request_id"] for r in rows})==len(rows)
    assert rows[0]["action"]=="/enter" and rows[-1]["action"]=="/exit"
    assert rows[-1]["response"]["exit_reason"]=="user_exit"
    summary={"commit":"c477d3660368f27c7131a0591426b4c4f107ea5d",
             "recording_sha256":hashlib.sha256(raw).hexdigest(),"requests":len(rows),
             "accepted_requests":len(rows),"outcomes":dict(outcomes),
             "discovered_channels":len(discovered),"cleared_channels":len(clears),
             "final_virtual_s":last_us/1000000,"exact_microsecond_mismatches":len(mismatches),
             "max_float_formula_residual_s":max(map(abs,residuals)),
             "same_point_direction_repetitions":repetitions,"fixed_error_violations":len(failures),
             "total_sources_reported_by_peer":15,"count_evidence":"peer REPORT only; referenced GUI screenshots absent from this commit",
             "official_authenticity":"Provided recording labelled practice, consistent hash; no independent cryptographic official-origin verification",
             "official_connections_made_by_this_audit":0,
             "limits":["No hidden exact source coordinates/radii/orientations", "One practice session only",
                       "No dedicated half-microsecond tie or exact physical boundary calibration",
                       "No logged reject/idempotent retry/deadline cases in the provided session"]}
    (OUT/"recording_audit.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (OUT/"recording_time_differences.json").write_text(json.dumps(mismatches,indent=2))
    import csv
    with (OUT/"recording_timing.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(per_step[0])); w.writeheader(); w.writerows(per_step)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
