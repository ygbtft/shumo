#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
# Earlier attempted OCR command (failed, exit 133, Apple Vision nilError):
# /usr/bin/swift -module-cache-path "$PWD/B/.swift-module-cache" B/paper_review_ocr.swift 'B/别人的结果/同学一' B/experiments/runs/2026-09-11_peer-paper-review/ocr
# All 35 original pages were instead read directly at original resolution.
case "${1:-check}" in
  check) /Users/dingdingzai/anaconda3/bin/python -B B/peer_paper_checks.py ;;
  launch) /Users/dingdingzai/anaconda3/bin/python -B B/ring_experiments.py --launch ;;
  summarize) /Users/dingdingzai/anaconda3/bin/python -B B/summarize_ring_review.py ;;
  smoke-ring9) /Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q3_active --method peer_ring9_r1300 --seed 42 ;;
  smoke-ring7) /Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q3_active --method ring7_r1140 --seed 42 ;;
  report) /Users/dingdingzai/anaconda3/bin/python -B B/write_report.py ;;
  final-check) /Users/dingdingzai/anaconda3/bin/python -B B/peer_review_final_checks.py ;;
  *) exit 2 ;;
esac
