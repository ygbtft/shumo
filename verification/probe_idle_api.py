import datetime
import http.client
import json
import pathlib
import platform
import sys
import time
import uuid

payload = {
    "arena_id": "default",
    "robot_id": "local-availability-probe",
    "request_id": "idle-probe-" + uuid.uuid4().hex,
}
result = {
    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "python": sys.executable,
    "architecture": platform.machine(),
    "observed_gui_state": "not_logged_in",
    "endpoint": "http://127.0.0.1:2026/enter",
    "request": payload,
}
connection = http.client.HTTPConnection("127.0.0.1", 2026, timeout=5)
started = time.perf_counter()
try:
    connection.request("POST", "/enter", json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
    response = connection.getresponse()
    result["http_status"] = response.status
    result["response_body"] = response.read().decode("utf-8", errors="replace")
    result["outcome"] = "received_http_response"
except (OSError, http.client.HTTPException) as error:
    result["outcome"] = "connection_failed_or_closed"
    result["exception"] = type(error).__name__
    result["message"] = str(error)
finally:
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000
    connection.close()
    destination = pathlib.Path("C:/JammersEvidence/idle-api-probe.json")
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
