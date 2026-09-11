#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
case "${1:-search}" in
  search) /Users/dingdingzai/anaconda3/bin/python -B B/visibility_layout_search.py ;;
  check) /Users/dingdingzai/anaconda3/bin/python -B B/replacement_experiments.py --check ;;
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/replacement_experiments.py --launch ;;
  *) exit 2 ;;
esac
