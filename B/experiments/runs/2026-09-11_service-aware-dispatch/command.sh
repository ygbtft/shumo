#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
 check) exec /Users/dingdingzai/anaconda3/bin/python -B B/service_aware_experiments.py --check >> B/experiments/runs/2026-09-11_service-aware-dispatch/check_log.txt 2>&1 ;;
 launch) exec /Users/dingdingzai/anaconda3/bin/python -B B/service_aware_experiments.py --launch ;;
 analyze) exec /Users/dingdingzai/anaconda3/bin/python -B B/service_aware_analysis.py ;;
 audit) exec /Users/dingdingzai/anaconda3/bin/python -B B/service_aware_audit.py >> B/experiments/runs/2026-09-11_service-aware-dispatch/audit_log.txt 2>&1 ;;
 *) exit 2 ;;
esac
