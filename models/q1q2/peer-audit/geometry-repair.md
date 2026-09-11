# Q1 区域分类与直径修复验证

本轮仅修改生产文件 `geometry.py`；新增几何回归测试及冻结反例。`circle.py` 与圆模块测试存在同期其他工作，本报告不将其改进计为本轮几何修复。未修改同学源码、对拍脚本或独立真值。

## 根因与修法

- 旧可行性、交点枚举和 deque 将固定长度容差作为可行证据，微小空隙和低维集合会被膨胀。现在保存归一化前的 binary64 原始系数，用 Fraction 做增量可行性、衰退锥和全交点检查；空集/无界/维数不再由容差决定。
- 测向角在浮点取模、三角函数和法向量归一化过程中会改变近退化系统。现在保留输入十进制角度，用标准库 Decimal 的 80 位三角计算和精确象限/对角恒等式，再用有理运算形成偏移。接近三角精度极限的不同边界返回 NUMERICAL_UNRESOLVED；这不是超越数的符号证明。
- 凸包方向采用浮点过滤加 Fraction 精确符号回退。规范化仍保留 CCW、字典序起点、去重和共线内点清理；区域清理按坐标 ulp 和区域尺度限制，防止微小区域的真实角点被固定米级容差删除。清理保护精确最远点对。
- 直径使用全对精确平方距离比较，维持最小索引并列规则；用 hypot 距离输出长度。坐标无法表达区域维数、直径平方上溢/下溢及高精度角度不足时，明确未决。

## 验证

| 项目 | 修复前 | 修复后 |
|---|---:|---:|
| 几何确定错误 WRONG | 195 | 0 |
| 几何未决 | 804 | 0 |
| 几何正确 OK | 3286 | 4285 |
| 独立点集直径失败（4317 例） | 3 | 0 |

原 195 例全是几何 BOTH_WRONG，纯 OURS_WRONG 为 0；不是将圆模块的 WRONG 混入几何计数。195 个几何最小反例和 3 个点集直径反例均冻结在 `tests/data/q1_differential_geometry.json`，测试要求这些可表示案例返回正确确定答案，不能用未决绕过。

- 全套 pytest：1433 passed in 19.30s。根目录直接收集存在打包副本与原测试同名冲突，因此使用 `--import-mode=importlib`，没有删除或跳过测试。
- q1_geometry benchmark：285/285，通过既有分类、直径、顶点规范化、相似变换与见证检查；全套 pytest 同时覆盖 d/R/覆盖已有行为。
- 原对拍命令、种子 `2026091107`、8000 随机例 + 602 夹具，共 8602 例，主评测几何 4285 例全 OK。
- 对拍脚本正常退出，前后受保护源码哈希相同。同学源码与原审计哈希也相同。

复现（仓库根目录）：

```bash
models/q1q2/.venv/bin/python -m pytest --import-mode=importlib -q
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q1_geometry.run
models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q1.py --seed 2026091107 --random-cases 8000
```

代价：半平面交点枚举最坏 O(n³)，直径全对比较 O(v²)，有理运算较旧浮点路径更慢。本轮优先保证当前 Q1 规模的确定答案正确；有限对拍结果不构成全输入证明。

机器证据：`geometry-repair-verification.json`、`differential-q1-summary.json` 和 `differential-q1-results.jsonl`。对拍自动生成的 Markdown 含固定历史叙述，最新计数应以 JSONL/本报告为准。
