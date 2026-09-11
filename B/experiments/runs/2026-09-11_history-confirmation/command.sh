#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/history_confirmation.py --launch ;;
  protocol) /Users/dingdingzai/anaconda3/bin/python -B B/history_protocol_checks.py >> B/experiments/runs/2026-09-11_history-confirmation/protocol_log.txt 2>&1 ;;
  audit) /Users/dingdingzai/anaconda3/bin/python -B B/history_final_checks.py >> B/experiments/runs/2026-09-11_history-confirmation/final_checks_log.txt 2>&1 ;;
  postprocess) /Users/dingdingzai/anaconda3/bin/python -B B/history_postprocess.py >> B/experiments/runs/2026-09-11_history-confirmation/postprocess_log.txt 2>&1 ;;
  diagnose) /Users/dingdingzai/anaconda3/bin/python -B B/history_trace_diagnosis.py >> B/experiments/runs/2026-09-11_history-confirmation/diagnosis_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/history_final_checks.py --finalize ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series history --problem 3 --method faithful_area7 --seed 42 > B/experiments/runs/2026-09-11_history-confirmation/smoke3_log.txt 2>&1 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series history --problem 4 --method history_first8_width015 --seed 42 > B/experiments/runs/2026-09-11_history-confirmation/smoke4_log.txt 2>&1 ;;
  report-support) /Users/dingdingzai/anaconda3/bin/python -B B/history_report_support.py > B/experiments/runs/2026-09-11_history-confirmation/report_support_log.txt 2>&1 ;;
  *) exit 2 ;;
esac
