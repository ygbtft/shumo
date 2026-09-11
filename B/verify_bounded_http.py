"""Read-only verification of saved mock HTTP runs and CLI no-network guards."""
import contextlib
import io
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch


def verify(folder):
    def read(name):
        return json.loads((folder / name).read_text())

    rows = [json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()]
    backend = [json.loads(line) for line in (folder / "mock_http_requests.jsonl").read_text().splitlines()]
    summary, policy, endpoint = read("summary.json"), read("policy.json"), read("endpoint.json")
    assert rows == backend
    assert endpoint["owned_mock"] and endpoint["base_url"].startswith("http://127.0.0.1:")
    assert endpoint["base_url"] != "http://127.0.0.1:2026"
    assert rows[0]["path"] == "/enter" and rows[-1]["path"] == "/exit"
    assert rows[-1]["response"]["exit_reason"] == "user_exit"
    assert sum(row["path"] == "/enter" for row in rows) == 1
    assert sum(row["path"] == "/exit" for row in rows) == 1
    assert len({row["request"]["request_id"] for row in rows}) == len(rows)
    position, channel, time_us, cleared = (0., 0.), 1, 0, set()
    for row in rows:
        request, response, path = row["request"], row["response"], row["path"]
        assert row["http_status"] == 200 and response["accepted"] is True
        if path in ("/measure", "/clear"):
            q = request["position"]["x"], request["position"]["y"]
            time_us += round(math.dist(position, q) / 5 * 1e6)
            position = q
            if path == "/measure":
                time_us += (5 + int(request["channel"] != channel)) * 1_000_000
                channel = request["channel"]
            else:
                success = response["clear_result"] == "success"
                time_us += (5 if success else 3) * 1_000_000
                if success:
                    assert request["channel"] not in cleared
                    cleared.add(request["channel"])
        assert response["virtual_time_s"] == time_us / 1e6
    assert cleared == {source["channel"] for source in read("scoring_only.json")["sources"]}
    assert summary["all_cleared"] and summary["clear_fraction"] == 1
    assert summary["cleared"] == len(cleared) and summary["total_virtual_s"] == time_us / 1e6
    assert summary["per_source_s"] == time_us / 1e6 / len(cleared)
    assert summary["commands"] == summary["http_requests"] == len(rows)
    assert summary["official_calls"] == 0
    expected = {3: ("range_area7", "CoupledCompletionPolicy", 7),
                4: ("range_grid21_29", "CoupledWidthPolicy", 21)}[summary["problem"]]
    assert (summary["method"], policy["class_name"], policy["station_count"]) == expected
    return dict(folder=str(folder), passed=True, commands=len(rows), total_virtual_s=time_us / 1e6)


def verify_guards():
    import run_bounded_robot
    base = ["run_bounded_robot.py", "--series", "cover21", "--problem", "3", "--method", "range_area7"]
    cases = [
        ["--mode", "practice"],
        ["--mode", "practice", "--robot-id", "guard-only"],
        ["--mode", "practice", "--confirm-practice"],
        ["--base-url", "http://127.0.0.1:2026"],
        ["--mode", "offline", "--confirm-practice"],
    ]
    with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")) as connect, \
         patch("socket.socket.bind", side_effect=AssertionError("Server startup forbidden")) as bind:
        for args in cases:
            with patch.object(sys, "argv", base + args), contextlib.redirect_stderr(io.StringIO()):
                try:
                    run_bounded_robot.main()
                except SystemExit as exc:
                    assert exc.code == 2
                else:
                    raise AssertionError("Invalid CLI was accepted")
        assert connect.call_count == bind.call_count == 0
    return dict(passed=len(cases), network_calls=0)


if __name__ == "__main__":
    folders = [Path(arg) for arg in sys.argv[1:]]
    if not folders:
        raise SystemExit("Usage: python -B verify_bounded_http.py RUN_FOLDER [RUN_FOLDER ...]")
    print(json.dumps(dict(runs=[verify(folder) for folder in folders], guards=verify_guards()), indent=2))
