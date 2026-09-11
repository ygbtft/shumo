#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  check) /Users/dingdingzai/anaconda3/bin/python -B B/completion_width_experiments.py --check >> B/experiments/runs/2026-09-11_completion-width/check_log.txt 2>&1 ;;
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/completion_width_experiments.py --launch ;;
  *) exit 2 ;;
esac
