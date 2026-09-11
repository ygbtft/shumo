#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/wide_confirmation.py --launch ;;
  protocol) /Users/dingdingzai/anaconda3/bin/python -B B/wide_protocol_checks.py >> B/experiments/runs/2026-09-11_wide-confirmation/protocol_log.txt 2>&1 ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series wide --problem 3 --method area_return1_7 --seed 42 >> B/experiments/runs/2026-09-11_wide-confirmation/smoke3_log.txt 2>&1 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series wide --problem 4 --method width_uncertainty100_22 --seed 42 >> B/experiments/runs/2026-09-11_wide-confirmation/smoke4_log.txt 2>&1 ;;
  check) /Users/dingdingzai/anaconda3/bin/python -B B/wide_final_checks.py >> B/experiments/runs/2026-09-11_wide-confirmation/final_check_log.txt 2>&1 ;;
  diagnose) /Users/dingdingzai/anaconda3/bin/python -B B/wide_trace_diagnosis.py >> B/experiments/runs/2026-09-11_wide-confirmation/diagnosis_log.txt 2>&1 ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/wide_postprocess.py >> B/experiments/runs/2026-09-11_wide-confirmation/postprocess_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/wide_final_checks.py --finalize >> B/experiments/runs/2026-09-11_wide-confirmation/finalize_log.txt 2>&1 ;;
  *) exit 2 ;;
esac
