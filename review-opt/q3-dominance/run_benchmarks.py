"""Run unchanged local Q1/Q2 benchmarks; redirect reports to evidence only."""
import runpy
import sys
from pathlib import Path
from unittest.mock import patch
ROOT = Path('/Users/flower/math/2026/B题')
sys.path.insert(0, str(ROOT))
original = Path.write_text
for name in ('q1_geometry', 'q1_circle_cover', 'q2_candidate', 'q2_worst_diameter'):
    def write(path, data, *args, **kwargs):
        if path.name.startswith('report') and 'benchmarks' in path.parts:
            path = ROOT/'review-opt/q3-dominance'/f'{name}.json'
        return original(path, data, *args, **kwargs)
    sys.argv = [name]
    with patch.object(Path, 'write_text', write):
        try:
            runpy.run_module(f'models.q1q2.benchmarks.{name}.run', run_name='__main__')
        except SystemExit as e:
            if e.code: raise
