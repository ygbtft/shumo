"""New task policies over an owned ephemeral loopback HTTP service."""
import gzip
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import time
from urllib.request import install_opener, build_opener, ProxyHandler

from client import Client, HttpTransport
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, Simulator, Limits, Protocol
from task_confirmation_v2 import OUT, SPECS, all_paths, build


def main():
    if (OUT / "http_checks.json").exists():
        raise RuntimeError("Preserving HTTP checks")
    install_opener(build_opener(ProxyHandler({})))
    paths = all_paths()
    checks = []
    for problem, method in ((3, "packet_center7"), (4, "packet_center22"), (4, "packet_action24_22"), (4, "packet_discover300_22")):
        scenario = generate(42, ScenarioConfig(directional_fraction=.5 if problem == 4 else 0.))
        error = ErrorConfig()
        records = []
        for mode in ("inprocess", "owned_loopback_http"):
            sim = Simulator(scenario, ErrorField(42, error), Limits(countdown_s=0))
            transport = PeerTransport(Protocol(sim))
            server = None
            if mode == "owned_loopback_http":
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass
                    def do_POST(self):
                        raw = self.rfile.read(int(self.headers["Content-Length"]))
                        status, response = transport(self.path, raw)
                        body = json.dumps(response, separators=(",", ":")).encode()
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                server = HTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                client = Client(HttpTransport(f"http://127.0.0.1:{server.server_address[1]}"), robot_id="mock-robot")
            else:
                client = Client(transport, robot_id="mock-robot")
            try:
                policy = build(client, SPECS[problem][method], problem, paths)
                began = time.perf_counter()
                policy.run()
                elapsed = time.perf_counter() - began
                assert len(sim.cleared) == len(scenario.sources)
                records.append([(e["path"], e["request"], e["response"]["virtual_time_s"]) for e in sim.trace])
                checks.append(dict(problem=problem, method=method, mode=mode, all_cleared=True,
                                   cleared=len(sim.cleared), commands=len(sim.trace),
                                   total_virtual_s=sim.virtual_time_s, wall_s=elapsed, official_calls=0))
                with gzip.open(OUT / f"protocol_{problem}_{method}_{mode}.jsonl.gz", "wt") as stream:
                    for entry in sim.trace:
                        stream.write(json.dumps(entry) + "\n")
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
        assert records[0] == records[1]
    result = dict(passed=4, failed=0, checks=checks, scored_execution_count=0, official_calls=0,
                  binding="Only this process's freshly created 127.0.0.1:0 server; no existing service contacted")
    (OUT / "http_checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
