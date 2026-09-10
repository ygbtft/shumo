# A题 药材烘干研究工作区

本目录独立存放A题的输入、模型、实验、图表、论文与支撑材料。其他题目应建立并列工作区，不依赖本目录的临时文件。

## 仓库版本说明

`A`分支仅提交实现代码、论文生成模板、依赖清单和复现说明。原始赛题数据、已生成的Excel/PDF/图表、缓存及第三方运行时不上传，均可按下述流程在本地生成。

克隆仓库并切换到`A`分支后，进入本目录，将题目提供的三个输入恢复到以下位置，保持原文件内容不变：

```text
A题/
  A题.pdf
  附件/
    附件1.xlsx
    附件2.xlsx
```

题给结果模板不是程序运行依赖，导出器会生成所需工作簿。请勿将其他题目的附件放入本目录。

## 使用边界

- 这是明确假设下的可复现有效输运模型，不是具有实验标定数据的真实药材预测模型。
- 当前成果由AI辅助推导、编码、验证和起草。最终参赛者必须独立复算、审核并遵守当年AI工具使用规定，不应将其表述为没有使用AI。
- 提供的2026格式规范明确禁止竞赛期间在GitHub等平台浏览、发布、讨论赛题相关内容。在确认非正式训练或允许发布的时间与条件之前，不自动上传。
- 不承诺奖项，不将经典Kirchhoff变换、有限体积法或PCHIP声称为首次提出的算法。

## 目录

| 路径 | 内容 |
|---|---|
| `附件/`、`A题.pdf` | 原始输入，未经修改 |
| `src/` | 数据读取、求解器、实验、导出和图表程序 |
| `results/` | 数值汇总、验证、敏感性、Excel结果与清单 |
| `figures/` | 可用于论文的PNG及PDF图表 |
| `paper/` | 中文论文文本和PDF生成程序 |
| `output/pdf/` | 匿名电子论文，含源码附录 |
| `cache/` | 大型中间数组与导出数据，可由程序重建，不建议提交到Git |
| `tmp/` | 渲染检查资料，不属于正式提交内容 |

## 计算

使用Python 3.11或更高版本（本次计算使用3.13.3），在A题目录中安装依赖后运行：

```powershell
python -m pip install -r requirements.txt
$env:PYTHONIOENCODING='utf-8'
python src/experiments.py --stage production --full-second-output
python src/experiments.py --stage validation
python src/experiments.py --stage sensitivity
python src/experiments.py --stage axial
python src/plots.py
```

生产模型使用1024个径向子区间；256、512、1024、2048级网格用于误差检查。无需GPU。二维检查仅用于评估中部截面的一维近似，不用低分辨率二维结果替换高分辨率主结果。

本次环境的受管理Node进程在启动时发生`CSPRNG`初始化错误，Artifact Tool及其操作标记脚本无法运行。因此实际交付通过`src/export_fallback.py`使用openpyxl流式导出，并逐单元格回读校验。该备用导出器不修改模型、输入或原始模板。`src/export_workbooks.mjs`是未在本机运行成功的可选工具入口，不属于已验证的主复现链。

`result2.xlsx`包含1至207120 s的全程逐秒温度和含水率；`result2_3h.xlsx`仅是前三小时的便捷节选。标准支撑包包含全程文件。为减少文件体积，导出器对连续、无空缺的密集工作表省略OOXML中可选的单元格地址属性，保留行号、数值、顺序和格式，再按标准DEFLATE压缩；回读确认所有数值完全一致。它不是降采样、删列或将数字转为文本。

第四问结果中，超过当时半径的位置留空；最后一列为移动表面，另有半径表。空白不是零含水率。执行停止时刻采用整分钟并保证保留四位小数后全域最大含水率仍小于0.15；论文另外报告临界阈值时刻，避免将安全裕量误当成数值误差。

## 导出、论文与打包

在一个安装了`requirements.txt`全部依赖的Python环境中继续执行：

```powershell
python src/export_fallback.py all
python src/audit_workbooks.py
python src/render_equations.py
python src/audit_model.py
python paper/build_paper.py
python src/verify_pdf.py
python src/verify_pdf.py --input tmp/workbook_previews/工作簿回读预览.pdf --preview-only
python src/package_release.py
```

PDF默认使用Windows宋体、黑体，以及Segoe UI Symbol补足数学字符。其他系统可设置`CJK_FONT_REGULAR`、`CJK_FONT_BOLD`、`MATH_SYMBOL_FONT`为本机对应的TrueType字体路径。实际计算环境将数值求解/绘图和openpyxl/ReportLab分置于两个Python运行时；复现时可以合并安装在同一环境，不依赖本机的绝对目录。

正文由`paper/manuscript_template.md`和实验JSON自动生成；`paper/论文.md`可编辑，公式LaTeX源保存在模板中。改动模板或源码后需重新生成PDF、检查渲染，再打包。`tmp/pdfs/`包含逐页渲染和联系表，必须进行人工视觉检查，不能只依赖自动边界测试。

若PDF被查看器锁定，生成器会保留已打开文件，另存为`论文_审阅版.pdf`或带时间戳的版本。当前有效文件名以`results/paper_build.json`中的`pdf_path`为准；核验与打包程序自动使用该路径。

`src/audit_model.py`检查稀疏Jacobian、均匀平衡、瞬时收支、解的范围、移动域空白和全程/节选重叠一致性；`src/audit_workbooks.py`逐单元格核对导出数值与四位小数格式。`results/release_manifest.json`记录支撑文件及论文SHA256，压缩包写入后再次回读核验。

完整数值实验需要CPU和数GB内存；高网格验证及Excel导出比主模型耗时更多。1024网格的两次长时间主积分各约十几至二十秒，2048网格验证单次约三分钟，本机整条交付流程应预留20至40分钟。该耗时不是竞赛限时或其他硬件上的保证。

## 本次关键结果

| 指标 | 第三问 | 第四问 |
|---|---:|---:|
| 临界时长/h | 57.4723 | 51.0871 |
| 整分钟执行时长/h | 57.5333 | 51.1333 |
| 执行停止时最大含水率（未舍入） | 0.1499360690 | 0.1499145831 |

可信度证据包括常系数导热解析基准、256至2048级网格、同网格BDF/Radau对照、粗网格通量反例、二维端面对照、同物性收缩消融及26个参数/边界情景。数值误差估计与物理模型假设的不确定性分开报告；没有真实材料验证数据，不能声称实验预测精度。

## 交付审核

电子论文从摘要开始，不含承诺书、编号页或学校、参赛者身份。正文不超过30页，源码附录另计。论文PDF和支撑ZIP分别检查20MB限制。支撑包不重复包含赛题原始数据，也不包含Git元数据或本机路径日志。

推送目标为用户指定仓库，但本地成果是否已推送须以交付时的实际Git记录为准；本说明不表示远程提交已经成功。
