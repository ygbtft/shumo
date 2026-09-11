"""Launch the frozen CPU experiment in a background process, with B-only logs."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parent
peer="--peer" in sys.argv[1:]
out=root/("experiments/runs/2026-09-10_peer-benchmark" if peer else "experiments/runs/2026-09-10_independent")
env=os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE="1",MPLCONFIGDIR=str(root/".mplconfig"),OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
with (out/"log.txt").open("a") as log:
    process=subprocess.Popen([sys.executable,"-B",str(root/("peer_benchmark.py" if peer else "run_experiments.py"))],cwd=root.parent,env=env,
                             stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(out/"background.pid").write_text(str(process.pid)+"\n")
print(f"Background PID {process.pid}; log: {out/'log.txt'}")
