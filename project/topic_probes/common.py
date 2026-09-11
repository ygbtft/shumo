"""Local, exploratory topic probes. Never writes into the original problem bundle."""
from pathlib import Path
import hashlib
import json
import platform
import time

import numpy as np
import pandas as pd
import scipy

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "CUMCM2026Problems"
OUT = ROOT / "experiments/runs/2026-09-10_topic-probes"
SEED = 42


def log(topic, message):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{topic}] {message}"
    print(line, flush=True)
    with (OUT / "log.txt").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def save_json(name, value):
    def convert(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, Path):
            return str(item)
        raise TypeError(type(item).__name__)
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=convert), encoding="utf-8"
    )


def record_environment(topic, files):
    save_json(f"{topic}_run_config.json", {
        "seed": SEED,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "input_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "purpose": "topic-selection exploratory experiment, not a competition submission",
    })
