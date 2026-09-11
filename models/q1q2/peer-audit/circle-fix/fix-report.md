# Q1 最小圆与覆盖修复验证

生产改动仅在 `models/q1q2/circle.py`；未修改同学代码、独立真值生成器或 benchmark 判定脚本。新增测试冻结了原审计 515 个 OURS_WRONG/BOTH_WRONG 最小圆反例及 3 个覆盖符号反例。

## 根因与修复

- 原归一化 `max(1, scale)` 与带绝对米级下限的包含/面积容差使小点集被零圆包含，并将良态小三角形误判共线。现在使用实际局部尺度；浮点包含只用于提出支撑候选。
- 支撑圆使用 Fraction 精确计算；发布最小圆之前，精确检查全点包含和圆心属于支撑点凸包。这两个条件共同证明全局最小性。候选失败时使用精确 Welzl 回退；枚举核验器也精确比较平方半径与包含关系。
- 半径使用 80 位 Decimal 开方，避免先转浮点平方半径导致溢出/下溢。圆心导出采用局部圆直径的相对误差预算，不以巨大平移的坐标 ULP 放宽。无法表达的圆心、半径及数值溢出诚实返回未决，不增大半径掩盖问题。
- Thales 点积用 Fraction 确定符号，消除假 YES。正残差沿用公开覆盖 API 的保守未决区间；κ 仅在 MEC 已解时提供，η 与中点半径由精确平方量计算。清障半径参数拒绝 NaN/Inf。

## 验证

- 全仓 pytest：**1434 passed in 19.23s**。使用 `--import-mode=importlib` 避免仓库 portable-package 副本的同名测试收集冲突。
- 原覆盖 benchmark：**312/330 例通过，21436 次检查**。18 个失败全部仅为 `forced.exception`：旧脚本要求以原固定绝对面积阈值抛出异常，而修复后返回经过精确计算的非共线三点圆。未修改或抑制这些失败；所有圆心、R、覆盖、κ、η、支撑、平移缩放不变性及正常尺度检查均无失败。
- 对称四站锚点：d=41.321338，R=20.660669，R/d=0.5，覆盖 YES；原测试中边长 20/36 等边三角形的 κ=2/√3、η=√3 均通过。

| 原审计同口径指标 | 修前 | 修后 |
|---|---:|---:|
| 独立点集最小圆 WRONG | 515（纯我方 7 + BOTH_WRONG 508） | 0 |
| 独立点集最小圆 OK | 3471 | 4192 |
| 独立点集最小圆 UNRESOLVED | 331 | 125 |
| 覆盖状态错误 | 3 | 0 |
| κ 错误 | 509 | 0 |
| η 错误 | 0 | 0 |

总输入 8602，独立圆点集 4317。保持原种子 2026091107、随机 8000、原严格容差与原基准容差；未修改裁判。

工作区另有并行任务修改 geometry.py，故最后一次完整对拍在当前源码的独立快照运行，快照内前后源码哈希全部一致，circle.py 的哈希与当前工作区相同。集成结果中的上游几何/直径改进不能归功于本次圆修复。快照位置和逐文件哈希见 snapshot.json；完整前后计数见 verification.json。

## 复现与产物

```sh
models/q1q2/.venv/bin/python -m pytest --import-mode=importlib -q
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q1_circle_cover.run
# 原脚本在隔离快照中的完整运行；同学代码仍取其原只读路径
models/q1q2/.venv/bin/python -B /var/folders/jt/zqnnfv9942qglzppjt2wjn000000gn/T/q1-circle-audit-by_qn31e/models/q1q2/peer-audit/differential_q1.py --seed 2026091107 --random-cases 8000
```

原基准报告 benchmark-report.json 保留全部 18 项失败；differential-q1-summary.json 保存运行前后源码哈希，differential-q1-results.jsonl 保存逐例结果，pytest.log 保存全套测试输出。本次有限样本审计不构成全输入证明；精确证书针对已提交的 binary64 输入，不能恢复提交前已经舍入丢失的坐标信息。
