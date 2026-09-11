#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_confirmation.py --launch ;;
  protocol) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_protocol_checks.py >> B/experiments/runs/2026-09-11_coupled-confirmation/protocol_log.txt 2>&1 ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series coupled --problem 3 --method range_area7 --seed 42 >> B/experiments/runs/2026-09-11_coupled-confirmation/smoke3_log.txt 2>&1 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series coupled --problem 4 --method fast_arc05_width015 --seed 42 >> B/experiments/runs/2026-09-11_coupled-confirmation/smoke4_log.txt 2>&1 ;;
  check) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_final_checks.py >> B/experiments/runs/2026-09-11_coupled-confirmation/final_check_log.txt 2>&1 ;;
  diagnose) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_trace_diagnosis.py >> B/experiments/runs/2026-09-11_coupled-confirmation/diagnosis_log.txt 2>&1 ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_postprocess.py >> B/experiments/runs/2026-09-11_coupled-confirmation/postprocess_log.txt 2>&1 ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/coupled_final_checks.py --finalize ;;
  *) exit 2 ;;
esac
