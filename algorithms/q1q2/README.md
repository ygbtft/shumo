# Q1/Q2 算法与数学实验

主入口：从仓库根目录执行 `python -m algorithms.q1q2.run q1 ...` 或 `q2 ...`，完整命令见 [仓库说明](../../README.md)。环境统一使用根目录 `.venv`。

| 文件/目录 | 作用 |
|---|---|
| `q1.py`、`geometry.py`、`circle.py` | 角锥交集、区域分类、直径和最小覆盖圆 |
| `q2.py`、`feasible.py` | 第二检测点可行域与最坏定位直径的数值搜索 |
| `basic_geometry.py` | 四个独立几何函数；运行不依赖本地模拟器 |
| `adapters.py`、`run.py`、`data/` | 输入解析、命令入口和标准案例 |
| `diagnostics.py`、`sensitivity.py`、`plots.py` | 数学诊断、敏感性计算、已有数据绘图 |
| `optional/` | 固定点区间认证与标准场景外层排除证书 |
| `tests/`、`benchmarks/` | 几何/求解测试、独立真值案例、认证结果与复核源码 |
| `outputs/`、`reviews/` | 既有数学实验结果、敏感性数据、论证及文献素材 |

主要思路见 [Q1](../../docs/q1.md)、[Q2](../../docs/q2.md)；完整数学设计见 [设计长文](../../docs/q1q2-design.md)，论文推导见 [Q1/Q2正文](../../paper/modeling-q1q2.md)。

```sh
python -m pytest algorithms/q1q2/tests -q --import-mode=importlib
python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify
```

生产搜索返回数值候选，不能把有限样本给出的半径当作覆盖保证；认证结果以证书的模型假设和收敛状态为准。
