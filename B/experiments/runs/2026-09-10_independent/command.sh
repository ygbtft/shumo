#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export MPLCONFIGDIR=/Users/dingdingzai/Desktop/数学建模/B/.mplconfig
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
/Users/dingdingzai/anaconda3/bin/python -B B/extract_sources.py
/Users/dingdingzai/anaconda3/bin/python -B B/checks.py
/Users/dingdingzai/anaconda3/bin/python -B B/run_experiments.py
/Users/dingdingzai/anaconda3/bin/python -B B/analysis_experiments.py
/Users/dingdingzai/anaconda3/bin/python -B B/summarize.py
