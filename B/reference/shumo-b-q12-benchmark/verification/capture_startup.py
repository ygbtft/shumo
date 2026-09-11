import datetime
import json
import pathlib
import subprocess
import sys
import time

variant = sys.argv[1]
if variant not in {"full", "slim"}:
    raise SystemExit("Expected full or slim")
label = f"{variant}-visual"
directory = pathlib.Path(__file__).parent / "evidence"
prlctl = "/Applications/Parallels Desktop.app/Contents/MacOS/prlctl"
command = [prlctl, "exec", "Windows 11", "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\\Jammers\\compare_startup.ps1", "-Variant", variant, "-RunLabel", label, "-ObserveSeconds", "30"]
frames = []
started = time.monotonic()
with (directory / f"{label}-console.txt").open("w") as output:
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
    for offset in (5, 8, 13):
        time.sleep(max(0, started + offset - time.monotonic()))
        filename = directory / f"{label}-{offset}s.png"
        subprocess.run([prlctl, "capture", "Windows 11", "--file", str(filename)], check=True, capture_output=True)
        frames.append({"file": filename.name, "host_command_elapsed_s": time.monotonic() - started, "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    exit_code = process.wait(timeout=45)
    if exit_code:
        raise SystemExit(exit_code)
(directory / f"{label}-frames.json").write_text(json.dumps(frames, indent=2))
print(json.dumps(frames, indent=2))
