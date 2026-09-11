"""Frozen pre-refactor seed42 results, plus experiment-tree isolation."""
import gzip
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import bounded_candidates as candidates

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / "tests/fixtures/bounded_entry_seed42.json").read_text())


class BoundedEntryTests(unittest.TestCase):
    def test_cli_guards_before_layout_loading(self):
        import run_bounded_robot
        from verify_bounded_http import verify_guards
        self.assertEqual(verify_guards()["network_calls"], 0)
        for extra in (("--problem", "3", "--method", "range_grid21_29"),
                      ("--problem", "4", "--method", "range_area7"),
                      ("--problem", "3", "--method", "range_area7", "--series", "icra")):
            with patch.object(sys, "argv", ["run_bounded_robot.py", *extra]), \
                 patch.object(run_bounded_robot, "load_paths", side_effect=AssertionError("No layout reads")), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    run_bounded_robot.main()
                self.assertEqual(error.exception.code, 2)

    def test_only_frozen_candidates_and_exact_layouts(self):
        self.assertEqual({q: list(s) for q, s in candidates.SPECS.items()},
                         {3: ["range_area7"], 4: ["range_grid21_29"]})
        for problem in (3, 4):
            expected = BASELINE["candidates"][str(problem)]
            spec = next(iter(candidates.SPECS[problem].values()))
            self.assertEqual(spec, expected["spec"])
            paths = candidates.load_paths(problem)
            self.assertEqual(list(paths), [spec["layout"]])
            np.testing.assert_array_equal(paths[spec["layout"]], expected["stations"])

    def test_ring7_needs_no_files_and_layout_loading_never_writes(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError), \
             patch.object(Path, "write_text", side_effect=AssertionError("No writes")):
            self.assertEqual(len(candidates.load_paths(3)["ring7"]), 7)
        with patch.object(Path, "write_text", side_effect=AssertionError("No writes")):
            self.assertEqual(len(candidates.load_paths(4)["grid21_29"]), 21)

    def test_cli_matches_pre_refactor_in_both_backends_without_experiments(self):
        # A fresh interpreter prevents another test's cached imports from hiding
        # a dependency. Deny the entire historical tree, not just missing polar.
        script = '''
import importlib.abc
from pathlib import Path
import sys
class NoExperiments(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(word in fullname for word in ("experiments", "confirmation", "final_checks")):
            raise AssertionError("Historical import: " + fullname)
sys.meta_path.insert(0, NoExperiments())
original_read = Path.read_text
def read(self, *args, **kwargs):
    if "experiments" in self.parts:
        raise FileNotFoundError(self)
    return original_read(self, *args, **kwargs)
Path.read_text = read
import run_bounded_robot as runner
import bounded_http
destination = Path(sys.argv[1])
(destination / "client.py").write_bytes((runner.ROOT / "client.py").read_bytes())
runner.ROOT = bounded_http.ROOT = destination
sys.argv = ["run_bounded_robot.py"] + sys.argv[2:]
runner.main()
'''
        for problem, method in ((3, "range_area7"), (4, "range_grid21_29")):
            for mode in ("mock-http", "offline"):
                with self.subTest(problem=problem, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    subprocess.run([sys.executable, "-B", "-c", script, tmp,
                                    "--problem", str(problem), "--method", method,
                                    "--mode", mode, "--seed", "42"], cwd=ROOT,
                                   check=True, capture_output=True, text=True, timeout=60)
                    folder = next((Path(tmp) / "robot_runs").iterdir())
                    summary = json.loads((folder / "summary.json").read_text())
                    # Wall/CPU timings and real timestamps naturally vary;
                    # every scoring field and policy statistic must be exact.
                    for key in ("wall_s", "cpu_s", "initialization_s", "program_wall_s"):
                        summary.pop(key, None)
                    expected = BASELINE[f"q{problem}-{mode}"]
                    self.assertEqual(summary, expected["summary"])
                    self.assertTrue(summary["all_cleared"])
                    if mode == "offline":
                        stream = gzip.open(folder / "trace.jsonl.gz", "rt")
                    else:
                        stream = (folder / "requests.jsonl").open()
                    with stream:
                        rows = [json.loads(line) for line in stream]
                    for row in rows:
                        # UUID request prefixes identify executions, not actions.
                        row["request"].pop("request_id")
                        row["response"].pop("real_timestamp_ms")
                    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
                    self.assertEqual(digest, expected["trace_sha256"])


if __name__ == "__main__":
    unittest.main()
