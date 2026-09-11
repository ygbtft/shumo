#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
/Users/dingdingzai/anaconda3/bin/python -B B/multicore_cover_search.py --launch

# 独立见证审计（首次ImportError及修正后的输出均保留）
# OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/dingdingzai/anaconda3/bin/python -B B/multicore_cover_audit.py >> B/experiments/runs/2026-09-11_multicore-cover-search/audit_log.txt 2>&1
