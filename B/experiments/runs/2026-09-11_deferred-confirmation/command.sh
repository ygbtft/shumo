#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_confirmation.py --launch ;;
  protocol) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_protocol_checks.py >> B/experiments/runs/2026-09-11_deferred-confirmation/protocol_log.txt 2>&1 ;;
  audit) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_final_checks.py >> B/experiments/runs/2026-09-11_deferred-confirmation/final_checks_log.txt 2>&1 ;;
  postprocess) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_postprocess.py >> B/experiments/runs/2026-09-11_deferred-confirmation/postprocess_log.txt 2>&1 ;;
  diagnose) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_trace_diagnosis.py >> B/experiments/runs/2026-09-11_deferred-confirmation/diagnosis_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_final_checks.py --finalize ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series deferred --problem 3 --method deferred_area7 --seed 42 > B/experiments/runs/2026-09-11_deferred-confirmation/smoke3_log.txt 2>&1 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series deferred --problem 4 --method cheap_predict8_width015 --seed 42 > B/experiments/runs/2026-09-11_deferred-confirmation/smoke4_log.txt 2>&1 ;;
  report-support) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_report_support.py > B/experiments/runs/2026-09-11_deferred-confirmation/report_support_log.txt 2>&1 ;;
  figure) /Users/dingdingzai/anaconda3/bin/python -B B/deferred_tradeoff_figure.py > B/experiments/runs/2026-09-11_deferred-confirmation/figure_log.txt 2>&1 ;;
  *) exit 2 ;;
esac
