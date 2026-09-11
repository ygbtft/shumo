#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
case "${1:-fetch}" in
  fetch) curl --fail --location --max-time 45 --output B/reference/tokekar2013asensor.pdf https://tokekar.com/pubs/tokekar2013asensor.pdf ;;
  *) exit 2 ;;
esac
