"""Serial official-practice latency recorder; uses only the Python standard library."""

import argparse
import collections
import datetime
import http.client
import json
import math
import pathlib
import platform
import statistics
import sys
import time
import unicodedata
import uuid


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    offset = (len(ordered) - 1) * fraction
    lower = math.floor(offset)
    upper = math.ceil(offset)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (offset - lower)


def distribution(values):
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "mean_ms": statistics.fmean(values) if values else None,
        "max_ms": max(values) if values else None,
    }


class Recorder:
    def __init__(self, arguments, output):
        self.arguments = arguments
        self.output = output
        self.connection = None
        self.rows = []
        self.prefix = uuid.uuid4().hex

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def request(self, endpoint, phase, position=None, channel=None):
        payload = {
            "arena_id": "default",
            "robot_id": self.arguments.robot_id,
            "request_id": f"{self.prefix}-{len(self.rows)}",
        }
        if position is not None:
            payload.update(position={"x": position[0], "y": position[1]}, channel=channel)
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if self.connection is None:
            self.connection = http.client.HTTPConnection("127.0.0.1", self.arguments.port, timeout=self.arguments.timeout)
        row = {
            "endpoint": endpoint,
            "phase": phase,
            "request": payload,
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        started = time.perf_counter_ns()
        try:
            self.connection.request("POST", endpoint, body, {"Content-Type": "application/json"})
            response = self.connection.getresponse()
            raw = response.read()
            row["rtt_ms"] = (time.perf_counter_ns() - started) / 1_000_000
            row["http_status"] = response.status
            data = json.loads(raw.decode("utf-8"))
            row["response"] = data
            if response.status != 200 or not isinstance(data, dict) or data.get("accepted") is not True:
                raise RuntimeError(f"{endpoint}: HTTP {response.status}, request not accepted")
            virtual_time = data.get("virtual_time_s")
            if isinstance(virtual_time, bool) or not isinstance(virtual_time, (int, float)) or not math.isfinite(virtual_time):
                raise RuntimeError("Missing or invalid virtual_time_s")
            result_key = {"/measure": "measure_result", "/clear": "clear_result"}.get(endpoint)
            allowed = {"/measure": {"direction", "near", "no_signal"}, "/clear": {"success", "no_target_in_range"}}
            if result_key and data.get(result_key) not in allowed[endpoint]:
                raise RuntimeError(f"Invalid {result_key}")
            return data
        except (OSError, http.client.HTTPException, ValueError, RuntimeError) as error:
            row.setdefault("rtt_ms", (time.perf_counter_ns() - started) / 1_000_000)
            row["error"] = f"{type(error).__name__}: {error}"
            self.close()
            raise RuntimeError(row["error"]) from error
        finally:
            self.rows.append(row)
            self.output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            self.output.flush()
            if self.arguments.connection == "new":
                self.close()


def run(arguments):
    arguments.output.mkdir(parents=True, exist_ok=False)
    summary = {
        "label": arguments.label,
        "python": sys.version,
        "executable": sys.executable,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "connection": arguments.connection,
        "count_per_endpoint": arguments.count,
        "warmup_per_endpoint": arguments.warmup,
        "percentile_method": "linear interpolation at (n - 1) * quantile",
        "measurement": "HTTP send through complete response body; excludes JSON encode/decode and log writes",
        "scope": "End-to-end guest RTT; does not isolate Prism overhead from simulator, HTTP, or VM scheduling",
        "status": "incomplete",
    }
    started = time.monotonic()
    with (arguments.output / "requests.jsonl").open("w", encoding="utf-8") as output:
        recorder = Recorder(arguments, output)
        try:
            enter_started = time.monotonic()
            entered = recorder.request("/enter", "control")
            remaining = entered.get("remaining_real_duration_s")
            virtual_limit = entered.get("max_virtual_duration_s")
            if type(remaining) is not int or not 0 <= remaining <= 1200:
                raise RuntimeError("Invalid remaining_real_duration_s")
            if isinstance(virtual_limit, bool) or not isinstance(virtual_limit, (int, float)) or not math.isfinite(virtual_limit) or virtual_limit <= 0:
                raise RuntimeError("Invalid max_virtual_duration_s")
            deadline = enter_started + remaining
            summary["remaining_real_duration_s"] = remaining
            virtual_time = entered["virtual_time_s"]
            previous_position = (0.0, 0.0)
            stopped_for_budget = False
            for pair_index in range(arguments.warmup + arguments.count):
                phase = "warmup" if pair_index < arguments.warmup else "sample"
                channel = arguments.channels[pair_index % len(arguments.channels)]
                for endpoint in ("/measure", "/clear"):
                    movement = math.dist(previous_position, arguments.position) / 5
                    if time.monotonic() + arguments.timeout + arguments.reserve >= deadline or virtual_time + movement + 6 >= virtual_limit:
                        stopped_for_budget = True
                        break
                    result = recorder.request(endpoint, phase, arguments.position, channel)
                    virtual_time = result["virtual_time_s"]
                    previous_position = arguments.position
                if stopped_for_budget:
                    break
                if (pair_index + 1) % 50 == 0:
                    print(f"Completed {pair_index + 1} serial pairs", flush=True)
            summary["last_virtual_time_s"] = virtual_time
            if time.monotonic() + arguments.timeout < deadline and virtual_time < virtual_limit:
                recorder.request("/exit", "control")
                summary["status"] = "budget_stop" if stopped_for_budget else "complete"
            else:
                summary["status"] = "deadline_stop_without_exit"
        except (RuntimeError, KeyboardInterrupt) as error:
            summary["status"] = "stopped_on_error"
            summary["error"] = f"{type(error).__name__}: {error}"
            print(f"Stopped; no retries or further actions: {error}", file=sys.stderr)
        finally:
            recorder.close()
            summary["wall_elapsed_s"] = time.monotonic() - started
            groups = collections.defaultdict(list)
            outcomes = collections.Counter()
            for row in recorder.rows:
                if row["phase"] != "sample":
                    continue
                if row.get("error"):
                    outcomes[f"{row['endpoint']}:error"] += 1
                    continue
                data = row["response"]
                outcome = data.get("measure_result", data.get("clear_result", "accepted"))
                groups[row["endpoint"]].append(row["rtt_ms"])
                groups[f"{row['endpoint']}:{outcome}"].append(row["rtt_ms"])
                outcomes[f"{row['endpoint']}:{outcome}"] += 1
            summary["latency"] = {key: distribution(values) for key, values in groups.items()}
            summary["outcomes"] = dict(outcomes)
            summary["recorded_requests"] = len(recorder.rows)
            (arguments.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"complete", "budget_stop"} else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--practice", action="store_true", help="Confirm the GUI is in an official practice test; this script cannot detect test type")
    parser.add_argument("--robot-id", help="Exact logged-in team number; prompted if omitted")
    parser.add_argument("--port", type=int, default=2026)
    parser.add_argument("--count", type=int, default=200, help="Measured requests per endpoint")
    parser.add_argument("--warmup", type=int, default=10, help="Warmup requests per endpoint; still advance virtual time")
    parser.add_argument("--position", nargs=2, type=float, default=(0.0, 0.0), metavar=("X", "Y"))
    parser.add_argument("--channels", nargs="+", type=int, default=list(range(1, 21)))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--reserve", type=float, default=10.0, help="Real seconds reserved before the deadline")
    parser.add_argument("--connection", choices=("keep-alive", "new"), default="keep-alive")
    parser.add_argument("--label", default="slim-arm64-python")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("benchmark-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    arguments = parser.parse_args()
    if not arguments.practice:
        parser.error("Use --practice only after personally selecting an official practice test and waiting for the interface to become ready")
    if not 1 <= arguments.port <= 65535 or not 1 <= arguments.count <= 10000 or not 0 <= arguments.warmup <= 1000:
        parser.error("Invalid port, count (1..10000), or warmup (0..1000)")
    if any(not math.isfinite(value) or abs(value) > 2_000_000 for value in arguments.position):
        parser.error("Coordinates must be finite and within +/-2000000")
    if any(not 1 <= channel <= 20 for channel in arguments.channels):
        parser.error("Channels must be in 1..20")
    if not math.isfinite(arguments.timeout) or not 0 < arguments.timeout <= 30 or not math.isfinite(arguments.reserve) or arguments.reserve < 0:
        parser.error("Invalid timeout or reserve")
    if arguments.robot_id is None:
        arguments.robot_id = input("Logged-in team number: ")
    if not 1 <= len(arguments.robot_id.encode("utf-8")) <= 64 or any(unicodedata.category(character) in {"Cc", "Cf"} for character in arguments.robot_id):
        parser.error("Invalid robot_id")
    if arguments.output.exists():
        parser.error("Output directory already exists; choose a new directory")
    return run(arguments)


if __name__ == "__main__":
    sys.exit(main())
