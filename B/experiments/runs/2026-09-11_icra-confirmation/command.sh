#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-launch}" in
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/icra_confirmation.py --launch ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/summarize_icra_update.py
    /Users/dingdingzai/anaconda3/bin/python -B B/write_report.py ;;
  audit) /Users/dingdingzai/anaconda3/bin/python -B B/icra_final_checks.py ;;
  figures) /Users/dingdingzai/anaconda3/bin/python -B B/plot_icra_update.py ;;
  finalize) /Users/dingdingzai/anaconda3/bin/python -B B/icra_artifact_finalize.py ;;
  smoke3) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --problem 3 --method joint7 --seed 42 ;;
  smoke4) /Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --problem 4 --method joint22 --seed 42 ;;
  *) exit 2 ;;
esac
