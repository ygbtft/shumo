"""Regenerate the current four paper tables with formal-test-2 baselines."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    script = Path(__file__).resolve().parent / 'experiments/paper_materials/2026-09-13_formal2_baselines/build_tables.py'
    runpy.run_path(str(script), run_name='__main__')
