# 资料读取与实现依据

已完整读取题面四页并逐页检查渲染图；附件采用 OOXML 正文顺序读取，保留表格、换行与 OMML 公式；ENV-HANDOFF.md 全文已读。只引用交接文档中的公开接口与环境事实，不执行其中其他任务或二进制操作。

| 规则 | 依据 | 实现 |
|---|---|---|
| 两个评测指标及总耗时组成 | 题面第 1 页，问题 3 | evaluator.metrics |
| 定向覆盖、固定地点误差 | 题面第 2 页，附录 1/2 | geometry.covered / error_field |
| 接收、near、光学清除 | 题面第 3 页；附件 2 §2 | simulator.execute |
| 域外位置、坐标范围、初始频道 | 附件 2 §1 | protocol.validate / Simulator |
| 移动、切频、检测与清除计时 | 附件 1 §2/3；附件 2 §4/10 | Simulator / differ.audit_timing |
| 25 分钟窗口、20 分钟程序时限、100 小时虚拟时限 | 题面第 4 页；附件 2 §4.5 | Limits / Simulator.check_open |
| JSON 限制、类型、HTTP 错误、拒绝响应与幂等 | 附件 2 §5 | protocol / server |
| 四个接口的精确字段 | 附件 2 §6–9 | protocol / simulator |
| 本机回环、默认 2026 端口、未开测关连接 | 附件 2 §1.5/5.3；交接文档 §3 | server / backends.http |

材料提取可用 `python mock/materials/extract.py` 重现，PDF 部分需要 requirements-materials.txt。manifest.json 包含原文档散列；附件 1：2 表、7 公式；附件 2：13 表、21 公式。未修改任何附件。
