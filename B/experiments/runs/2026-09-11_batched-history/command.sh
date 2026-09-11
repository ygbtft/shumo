#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  check) /Users/dingdingzai/anaconda3/bin/python -B B/batched_history_experiments.py --check >> B/experiments/runs/2026-09-11_batched-history/check_log.txt 2>&1 ;;
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/batched_history_experiments.py --launch ;;
  *) exit 2 ;;
esac
