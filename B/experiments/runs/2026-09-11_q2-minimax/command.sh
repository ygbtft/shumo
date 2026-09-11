#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
case "${1:-run}" in
  run) /Users/dingdingzai/anaconda3/bin/python -B B/q2_minimax_experiments.py ;;
  *) exit 2 ;;
esac
