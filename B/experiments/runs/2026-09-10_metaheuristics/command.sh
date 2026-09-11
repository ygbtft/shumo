#!/bin/zsh
set -eu
cd /Users/dingdingzai/Desktop/数学建模
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/B/.mplconfig"
export XDG_CACHE_HOME="$PWD/B/.cache"
/Users/dingdingzai/anaconda3/bin/python -B B/route_algorithm_checks.py
/Users/dingdingzai/anaconda3/bin/python -B B/metaheuristic_experiments.py --launch
# 后台进程依次运行固定点集优化与独立后端配对评估。

# 附加消融，先记录后启动；不替换冻结路线。
/Users/dingdingzai/anaconda3/bin/python -B B/route_ablation.py --launch

# 选择规则已写入 confirmation_plan.md，确认进程等待主矩阵完成后才选定并冻结。
/Users/dingdingzai/anaconda3/bin/python -B B/route_confirmation.py --launch

# 等完成标记生成；这些命令不启动官方会话。原运行目录拒绝覆盖，
# 本文件是该次实验的命令记录；重做时需为各阶段配置新的B/内目录。
b_wait_round=0
while [[ ! -f B/experiments/runs/2026-09-10_metaheuristics/completion.json || ! -f B/experiments/runs/2026-09-10_metaheuristics/confirmation/completion.json || ! -f B/experiments/runs/2026-09-10_metaheuristics/ablation.csv ]]; do
  sleep 5
  b_wait_round=$((b_wait_round + 1))
  if (( b_wait_round >= 360 )); then
    exit 1
  fi
done
/Users/dingdingzai/anaconda3/bin/python -B B/route_final_checks.py
/Users/dingdingzai/anaconda3/bin/python -B B/summarize_metaheuristics.py
/Users/dingdingzai/anaconda3/bin/python -B B/publish_metaheuristic_report.py

# 新入口三种任务的单局冒烟；与3969次评分实验分开计数。
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q3_active
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q4_active --method fireworks
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q4_conservative
