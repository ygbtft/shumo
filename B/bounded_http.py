"""HTTP delivery for frozen policy factories, with an owned simulator.py mock."""
from contextlib import contextmanager, nullcontext
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import socket
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
        self.failures = 0
        self.request_ids = set()

    def append(self, row):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self.count += 1
        self.failures += row.get("event") == "transport_failure"
        self.request_ids.add(row["request"]["request_id"])


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
def owned_mock_http(world, journal, *, read_timeout_s=5.):
    protocol = Protocol(world, robot_id="offline-robot")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            if len(raw) != length or self.server.closing or time.monotonic() >= self.server.read_deadline:
                # A disconnected sender did not deliver a complete action.
                self.close_connection = True
                return
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

    class Server(HTTPServer):
        def __init__(self, *args):
            self.connection_lock = threading.Lock()
            self.current_connection = None
            self.closing = False
            super().__init__(*args)

        def close_current(self):
            with self.connection_lock:
                if self.current_connection is not None:
                    try:
                        self.current_connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.current_connection.close()

        def get_request(self):
            connection, address = super().get_request()
            with self.connection_lock:
                if self.closing:
                    connection.close()
                    raise OSError("Mock is closing")
                self.current_connection = connection
                self.read_deadline = time.monotonic() + read_timeout_s
            return connection, address

        def finish_request(self, request, address):
            # A socket timeout alone is renewed by trickled bytes. This timer
            # bounds the whole header + body read on the single accepted socket.
            request.settimeout(read_timeout_s)
            timer = threading.Timer(max(0., self.read_deadline - time.monotonic()), self.close_current)
            timer.start()
            try:
                super().finish_request(request, address)
            finally:
                timer.cancel()
                timer.join()
                with self.connection_lock:
                    self.current_connection = None

    # Bind our own service before creating the client. Never probe an existing port.
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        # Prevent a concurrent accept from escaping teardown, then unblock the
        # handler before shutdown waits for the single service thread.
        with server.connection_lock:
            server.closing = True
        server.close_current()
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
    cli = None
    policy = None
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
                          commands=journal.count-journal.failures, transport_failures=journal.failures,
                          wall_s=wall, cpu_s=cpu,
                          initialization_s=initialization, policy=stats,
                          official_calls=0 if world is not None else journal.count)
            if world is not None:
                score = world.score()
                result.update(score)
                result.update(entered=world.entered, exited=world.exited,
                              http_requests=backend_journal.count, backend="B/simulator.py")
                if not (world.entered and world.exited and
                        world.commands == result["commands"] == len(backend_journal.request_ids)):
                    raise RuntimeError("Mock HTTP lifecycle or command count mismatch")
                if score["cleared"] != cleared or score["total_virtual_s"] != cli.virtual_s:
                    raise RuntimeError("Mock scoring and public client state mismatch")
        # Includes imports, paths, initialization, HTTP, journals and server teardown;
        # excludes only this final summary write and printing/process teardown.
        result["program_wall_s"] = time.perf_counter() - program_started
        write("summary.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        (folder / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        # Preserve confirmed public state even when a pending action's outcome
        # is unknown. Do not issue a new action/exit to probe that outcome.
        write("summary.json", dict(
            status="failed", error=repr(exc), mode=args.mode, series=args.series,
            problem=args.problem, method=args.method,
            total_virtual_s=cli.virtual_s if cli is not None else None,
            cleared=len(getattr(policy, "cleared", ())) if policy is not None else None,
            commands=journal.count-journal.failures, transport_failures=journal.failures,
            execution_state="unknown" if journal.failures else "confirmed_only",
            http_requests=backend_journal.count if world is not None else None,
            official_calls=0 if world is not None else journal.count,
            program_wall_s=time.perf_counter()-program_started,
        ))
        raise
    finally:
        print(f"Local logs: {folder}")
