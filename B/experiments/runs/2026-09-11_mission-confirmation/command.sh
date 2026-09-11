#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/mission_confirmation.py --launch ;;
  http) /Users/dingdingzai/anaconda3/bin/python -B B/mission_http_checks.py ;;
  audit) /Users/dingdingzai/anaconda3/bin/python -B B/mission_final_checks.py > B/experiments/runs/2026-09-11_mission-confirmation/audit_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/mission_final_checks.py --finalize ;;
  diagnose) /Users/dingdingzai/anaconda3/bin/python -B B/mission_trace_diagnosis.py > B/experiments/runs/2026-09-11_mission-confirmation/diagnosis_log.txt 2>&1 ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/mission_postprocess.py
    /Users/dingdingzai/anaconda3/bin/python -B B/write_report.py ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series mission --problem 3 --method clearance7 --seed 42 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series mission --problem 4 --method quarter22 --seed 42 ;;
  *) exit 2 ;;
esac
