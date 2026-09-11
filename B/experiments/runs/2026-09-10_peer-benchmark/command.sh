#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export PYTHONPATH=/Users/dingdingzai/Desktop/数学建模/B/reference/shumo-b
/Users/dingdingzai/anaconda3/bin/python -B B/peer_audit.py
/Users/dingdingzai/anaconda3/bin/python -B -m pytest -q -p no:cacheprovider --import-mode=importlib B/reference/shumo-b/mock/tests/test_rules.py
/Users/dingdingzai/anaconda3/bin/python -B B/peer_benchmark.py
