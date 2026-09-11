"""HTTP delivery for frozen policy factories, with an owned simulator.py mock."""
from contextlib import contextmanager, nullcontext
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import threading
import time
import traceback

import numpy as np
from client import Client, HttpTransport
from simulator import Protocol, Source, World, serialize_sources

ROOT = Path(__file__).resolve().parent


class Journal:
    def __init__(self, path):
        self.path = path
        self.count = 0

    def append(self, row):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self.count += 1


def mock_world(problem, seed):
    """Same synthetic fixture generation as run_robot; truth stays in runner/backend."""
    rng = np.random.default_rng(seed)
    sources = []
    count = int(rng.integers(10, 17))
    for ch in rng.choice(np.arange(1, 21), count, replace=False):
        radius = 1800 * np.sqrt(rng.random())
        angle = rng.uniform(0, 2 * np.pi)
        sources.append(Source(
            int(ch), float(radius * np.cos(angle)), float(radius * np.sin(angle)),
            float(rng.uniform(1000, 1500)),
            float(rng.uniform(0, 2 * np.pi)) if problem == 4 and rng.random() < .5 else None,
        ))
    return World(sources, seed)


@contextmanager
def owned_mock_http(world, journal):
    protocol = Protocol(world, robot_id="offline-robot")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            status, response = protocol.dispatch(
                self.path, raw, content_type=self.headers.get("Content-Type", ""),
                encoding=self.headers.get("Content-Encoding", "identity"),
            )
            journal.append(dict(path=self.path, request=json.loads(raw),
                                http_status=status, response=response))
            data = json.dumps(response, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    # Bind our own service before creating the client. Never probe an existing port.
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def run_http(args, factory, spec, paths, program_started):
    folder = ROOT / "robot_runs" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-bounded-" + args.mode)
    folder.mkdir(parents=True)

    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    journal = Journal(folder / "requests.jsonl")
    backend_journal = Journal(folder / "mock_http_requests.jsonl")
    world = mock_world(args.problem, args.seed) if args.mode == "mock-http" else None
    write("config.json", dict(
        **vars(args), spec=spec, python=platform.python_version(), numpy=np.__version__,
        platform=platform.platform(), threads={key: os.environ.get(key) for key in
            ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
        client_sha256=hashlib.sha256((ROOT / "client.py").read_bytes()).hexdigest(),
    ))
    if world is not None:
        write("scoring_only.json", dict(sources=serialize_sources(world.sources.values()),
              seed=args.seed, noise=world.noise, rounding=world.rounding, backend="B/simulator.py"))
    context = owned_mock_http(world, backend_journal) if world is not None else nullcontext(args.base_url or "http://127.0.0.1:2026")
    try:
        with context as base_url:
            write("endpoint.json", dict(base_url=base_url, owned_mock=world is not None))
            cli = Client(HttpTransport(base_url), robot_id="offline-robot" if world is not None else args.robot_id,
                         transcript=journal)
            began = time.perf_counter()
            policy = factory(cli, spec, args.problem, paths)
            initialization = time.perf_counter() - began
            write("policy.json", dict(class_name=type(policy).__name__, spec=spec,
                  stations=policy.stations.tolist(), station_count=len(policy.stations)))
            began, cpu = time.perf_counter(), time.process_time()
            stats = policy.run()
            wall, cpu = time.perf_counter() - began, time.process_time() - cpu
            cleared = len(policy.cleared)
            result = dict(mode=args.mode, series=args.series, problem=args.problem, method=args.method,
                          seed=args.seed if world is not None else None,
                          cleared=cleared, total_virtual_s=cli.virtual_s,
                          per_source_s=cli.virtual_s / cleared if cleared else None,
                          commands=journal.count, wall_s=wall, cpu_s=cpu,
                          initialization_s=initialization, policy=stats,
                          official_calls=0 if world is not None else journal.count)
            if world is not None:
                score = world.score()
                result.update(score)
                result.update(entered=world.entered, exited=world.exited,
                              http_requests=backend_journal.count, backend="B/simulator.py")
                if not (world.entered and world.exited and world.commands == journal.count == backend_journal.count):
                    raise RuntimeError("Mock HTTP lifecycle or command count mismatch")
                if score["cleared"] != cleared or score["total_virtual_s"] != cli.virtual_s:
                    raise RuntimeError("Mock scoring and public client state mismatch")
        # Includes imports, paths, initialization, HTTP, journals and server teardown;
        # excludes only this final summary write and printing/process teardown.
        result["program_wall_s"] = time.perf_counter() - program_started
        write("summary.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        (folder / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        print(f"Local logs: {folder}")
