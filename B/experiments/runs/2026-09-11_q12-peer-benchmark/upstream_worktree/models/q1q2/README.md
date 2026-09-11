# 问题1 / 问题2：实现、设计、验证与论文

本目录是 2026 国赛 B 题问题 1、2 的完整工作区：数学设计、生产代码、评审、正确性 benchmark、认证上下界与论文草稿。合同来源为 [PLAN.md](PLAN.md) v3（两轮审计 + 三维评审 + 整合定稿）。核心口径：纯角锥定位区域 P 与完整物理条件集 K 分开；Q2 默认结果是数值候选（`NUMERICAL_CANDIDATE`），样本半径不代表覆盖保证。

## 目录与文件职责

### 生产代码（九个职责模块）

| 文件 | 职责 |
|---|---|
| `geometry.py` | 角锥→半平面、半平面交与区域分类（空/点/线段/多边形/无界）、凸包、旋转卡壳直径 |
| `circle.py` | Welzl 最小覆盖圆、强制/普通三点圆、Thales 覆盖判定、κ/η 膨胀系数、20 米三段判据 |
| `q1.py` | 任意 N 组观测校验与问题 1 结果装配 |
| `feasible.py` | 首测可行集 F、C_sig / C_dir 候选域、四圆盘约化、物理后验与外包 |
| `q2.py` | 源采样、不可区分点对评分、全域网格 + 局部细化、预算曲线、第二点选择 |
| `diagnostics.py` | 条件 R(K)、清除三态、面积近似、GDOP（可选辅助）、敏感性接口 |
| `adapters.py` | 手工 JSON / mock 观测 / JSONL 转换，三种误差模式，真值隔离 |
| `plots.py` | 从已保存结果生成论文图表，不参与求解 |
| `run.py` | 命令入口（q1/q2/examples/figures）与结果 + 复现清单输出；`--certify` 惰性调用认证模块 |

### 设计、论文与评审

| 路径 | 职责 |
|---|---|
| `PLAN.md` | 设计文档 v3：数学定义、定理、算法、验收标准的唯一权威 |
| `paper-q1q2.md` | 问题 1/2 论文正文草稿（竞赛风格，含相关工作与 8 篇核心参考文献） |
| `reviews/creativity.md`、`assumptions.md`、`correctness.md` | 三维规划评审（建模创造性 / 假设合理性 / 结果正确性） |
| `reviews/static-review.md` | 实现完成后的静态代码审查（抓出并已修复 5 个阻断 bug） |
| `reviews/literature-review.md` | 文献调研：核心文献精读、15 篇相关文献、与本模型的对照、可引用清单与贡献定位 |

### 验证与认证

| 路径 | 职责 |
|---|---|
| `tests/` | 单元测试与回归测试（含 benchmark 抓出的真 bug 回归） |
| `benchmarks/` | 正确性 benchmark，真值独立于生产代码；见 `benchmarks/README.md` |
| `benchmarks/q1_geometry`、`q1_circle_cover`、`q2_candidate`、`q2_worst_diameter` | 四块：半平面交/直径、覆盖圆/κ-η、候选域/四圆盘、最坏直径 |
| `optional/certified.py` | Q2 的 J(q) 区间分析认证式上下界 [L,U]（mpmath.iv，隔离依赖）；生产主链路不依赖它 |
| `data/`、`outputs/` | 解析案例输入配置；运行产物（JSON/CSV/图） |
| `requirements.txt` | 生产依赖（numpy/matplotlib/pytest）；认证依赖单列于 `benchmarks/q2_worst_diameter/requirements-certify.txt` |

## 运行

环境用本目录 `.venv`。从仓库根目录调用（Windows 用 `.venv/Scripts/python.exe`）：

```text
models/q1q2/.venv/bin/python -m models.q1q2.run q1 models/q1q2/data/standard.json
models/q1q2/.venv/bin/python -m models.q1q2.run q2 models/q1q2/data/standard.json --config models/q1q2/data/default_config.json
models/q1q2/.venv/bin/python -m models.q1q2.run examples --include-q2 --sensitivity --frontier
models/q1q2/.venv/bin/python -m models.q1q2.run figures <已保存的bundle.json> --output <图表目录>
```

求解命令保存结果、绘图数据与复现清单；`figures` 只读已保存数据不重求解；输出目录须不存在以免覆盖。测试与 benchmark：

```text
models/q1q2/.venv/bin/python -m pytest models/q1q2/tests -q --import-mode=importlib
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q1_geometry.run   # 四块之一
```

误差模式：`OFFICIAL_UNKNOWN` 不自选半宽，送求解前须显式选理论 1° 或最近舍入外包 1.005°（后者仅在潜在 ±1° 后最近舍入到 0.01° 的假设下适用）。

## 当前状态

- 实现完成，经静态代码审查（5 个阻断 bug 已修）与动态运行；`tests/` 全套通过。
- 四块正确性 benchmark 已跑，真值独立于生产：抓出并修复 3 个真 bug（单角锥/无界分类、Q2 最坏直径低估、C_dir 见证元数据）。修复后通过率 q1_geometry 264/285、q1_circle_cover 329/330、q2_candidate 502/531（核心 IN/OUT 判定 0 错）、q2_worst_diameter 46/48（低估 grade A 归零）。残留为 benchmark 过严或几何无害的顶点去重瑕疵，非错答案。
- Q2 认证式上下界 [L,U] 已实现并接入 benchmark（补上此前只有下界、抓不到高估的空缺），线段闭式、polar 等 7 案例全部收敛且夹住真 J。
- 论文正文草稿 `paper-q1q2.md` 已成稿，引用与文献调研一致。

## 待办（非阻断）

- 完整敏感性方案 S1–S9（当前 S1/S3/S4/S7 为骨架）与全链路容差审计。
- 部分论文图表合同（F1/F4/F8/F10 等标注）与配图生成。
- 认证模块在 Windows guest 的实跑验证（附录 A 要求；当前仅宿主验证）。
- mock 真实后端集成测试（现 mock 局部测试用合成观测）。
- benchmark 残留过严项收敛（极端尺度归 scale_limit、变换边界源探针容差）与顶点去重打磨。
