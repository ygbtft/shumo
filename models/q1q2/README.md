# Q1/Q2 默认实现

合同来源：[PLAN.md v3](PLAN.md)。九个职责模块，不包含 certified、Q3/Q4 搜索或统计置信承诺。纯角锥 P 与完整物理条件集 K 分开；Q2 结果均为数值候选，样本半径不代表覆盖保证。

环境使用本目录 `.venv`，依赖在 `requirements.txt`。从仓库根目录调用：

```text
models/q1q2/.venv/bin/python -m models.q1q2.run q1 models/q1q2/data/standard.json
models/q1q2/.venv/bin/python -m models.q1q2.run q2 models/q1q2/data/standard.json --config models/q1q2/data/default_config.json
models/q1q2/.venv/bin/python -m models.q1q2.run examples --include-q2 --sensitivity --frontier
models/q1q2/.venv/bin/python -m models.q1q2.run figures <已保存的bundle.json> --output <图表目录>
```

Windows 使用 `.venv/Scripts/python.exe`。没有 shell 或编译库运行依赖。求解命令保存结果、绘图数据与复现清单；`figures` 只读已保存的数据，不重新求解。输出目录须不存在，避免覆盖既有实验。

`OFFICIAL_UNKNOWN` 保存为明确的误差模式，但不自行选择半宽；送入求解前必须显式选择理论 1° 或最近舍入外包 1.005°。后者仅在潜在 ±1° 后最近舍入到 0.01° 的假设下适用。

本次交付仅写代码与测试，进行语法/导入和 pytest 收集检查。尚未执行测试、完整动态实验或生成图表，结果正确性及运行成本待静态 review 后统一验证。

## TODO（静态 review 后暂缓）

本轮只修 B1—B5 与指定配置/适配校验。其余按 `reviews/static-review.md` 保留：S1/S3/S4/S7 完整场景矩阵、全链路容差审计及 tie 对照；F1/F4/F7/F8/F9/F10 与 T2/T3 的图表合同、预算 V(B) 与不同站点状态的独立表达；公开评分/后验的保收前提、不可实现反馈校验、近切源集数值未决与边界元数据、自定义网格嵌套、一般 N 站物理外包；真实 mock 后端集成、连续夹具自动采样/细化及报告其余测试缺口。当前稳定性仅针对已完成并记录的数值对照，不代表全链路 S7 或严格误差界。
