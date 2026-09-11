#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
export TMPDIR="$PWD/B/experiments/runs/2026-09-11_q12-peer-benchmark/tmp"
exec /Users/dingdingzai/anaconda3/bin/python -B B/q12_benchmark_diagnostics.py
