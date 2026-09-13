"""Compare new policies over an owned ephemeral loopback server and in-process."""
import gzip
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.request import install_opener,build_opener,ProxyHandler
from client import Client,HttpTransport
from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,ScenarioConfig,generate,Simulator,Limits,Protocol
from mission_confirmation import OUT,SPECS,all_paths
from clearance_experiments import build


def main():
    # Only this process's fresh 127.0.0.1:0 server is contacted. Explicitly avoid
    # forwarding loopback test traffic through any machine-wide HTTP proxy.
    install_opener(build_opener(ProxyHandler({})))
    paths=all_paths();results=[]
    for problem,method in ((3,"clearance7"),(3,"clearance9"),(4,"quarter22"),(4,"clearance_f015_22")):
        scenario=generate(42,ScenarioConfig(directional_fraction=.5 if problem==4 else 0.));error=ErrorConfig()
        traces=[]
        for mode in ("inprocess","owned_loopback_http"):
            sim=Simulator(scenario,ErrorField(42,error),Limits(countdown_s=0));transport=PeerTransport(Protocol(sim))
            server=None;thread=None
            if mode=="owned_loopback_http":
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_POST(self):
                        raw=self.rfile.read(int(self.headers["Content-Length"]))
                        status,response=transport(self.path,raw);body=json.dumps(response,separators=(",",":")).encode()
                        self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
                server=HTTPServer(("127.0.0.1",0),Handler)
                port=server.server_address[1];thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                client=Client(HttpTransport(f"http://127.0.0.1:{port}"),robot_id="mock-robot")
            else:client=Client(transport,robot_id="mock-robot")
            try:
                policy=build(client,SPECS[problem][method],problem,paths);began=time.perf_counter();stats=policy.run();wall=time.perf_counter()-began
                assert len(sim.cleared)==len(scenario.sources)
                rows=[dict(path=e["path"],request=e["request"]) for e in sim.trace];traces.append(rows)
                results.append(dict(problem=problem,method=method,mode=mode,all_cleared=True,cleared=len(sim.cleared),commands=len(sim.trace),total_virtual_s=sim.virtual_time_s,wall_s=wall,official_calls=0))
                with gzip.open(OUT/f"protocol_{problem}_{method}_{mode}.jsonl.gz","wt") as f:
                    for entry in sim.trace:f.write(json.dumps(entry)+"\n")
            finally:
                if server is not None:server.shutdown();server.server_close();thread.join(timeout=2)
        assert traces[0]==traces[1],(problem,method)
        assert abs(results[-1]["total_virtual_s"]-results[-2]["total_virtual_s"])<1e-6
    (OUT/"http_checks.json").write_text(json.dumps(dict(passed=4,failed=0,scored_execution_count=0,
        binding="fresh own 127.0.0.1:0; no existing service contacted",checks=results,official_calls=0),indent=2))
    print(json.dumps(results,indent=2))


if __name__=="__main__":main()
