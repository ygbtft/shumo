#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
 launch) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_confirmation.py --launch ;;
 postprocess) exec /Users/dingdingzai/anaconda3/bin/python -B B/scan_pair_analysis.py >> B/experiments/runs/2026-09-11_cover21-confirmation/postprocess_log.txt 2>&1 ;;
 protocol) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_protocol_checks.py >> B/experiments/runs/2026-09-11_cover21-confirmation/protocol_log.txt 2>&1 ;;
 audit) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_final_checks.py >> B/experiments/runs/2026-09-11_cover21-confirmation/final_checks_log.txt 2>&1 ;;
 diagnose) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_trace_diagnosis.py >> B/experiments/runs/2026-09-11_cover21-confirmation/diagnosis_log.txt 2>&1 ;;
 report-support) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_report_support.py > B/experiments/runs/2026-09-11_cover21-confirmation/report_support_log.txt 2>&1 ;;
 figure) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_figures.py > B/experiments/runs/2026-09-11_cover21-confirmation/figure_log.txt 2>&1 ;;
 finalize) exec /Users/dingdingzai/anaconda3/bin/python -B B/cover21_final_checks.py --finalize ;;
 smoke3) exec /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series cover21 --problem 3 --method lean_deferred_area7 --seed 42 > B/experiments/runs/2026-09-11_cover21-confirmation/smoke3_log.txt 2>&1 ;;
 smoke4) exec /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --seed 42 > B/experiments/runs/2026-09-11_cover21-confirmation/smoke4_log.txt 2>&1 ;;
 *) exit 2 ;;
esac
