#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  check) /Users/dingdingzai/anaconda3/bin/python -B B/task_collector_checks.py > B/experiments/runs/2026-09-11_task-confirmation-v2/check_log.txt 2>&1 ;;
  http) /Users/dingdingzai/anaconda3/bin/python -B B/task_protocol_checks.py > B/experiments/runs/2026-09-11_task-confirmation-v2/http_log.txt 2>&1 ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series task --problem 3 --method packet_center7 --seed 42 > B/experiments/runs/2026-09-11_task-confirmation-v2/smoke3_log.txt 2>&1 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series task --problem 4 --method packet_center22 --seed 42 > B/experiments/runs/2026-09-11_task-confirmation-v2/smoke4_log.txt 2>&1 ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/task_postprocess.py
    /Users/dingdingzai/anaconda3/bin/python -B B/write_report.py ;;
  audit) /Users/dingdingzai/anaconda3/bin/python -B B/task_final_checks.py > B/experiments/runs/2026-09-11_task-confirmation-v2/audit_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/task_final_checks.py --finalize ;;
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/task_confirmation_v2.py --launch ;;
  *) exit 2 ;;
esac
