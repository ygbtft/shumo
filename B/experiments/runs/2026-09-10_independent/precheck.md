# 运行前检查

- 已读适用规范：/Users/dingdingzai/Desktop/AGENTS.md，无 B 子目录规范。
- 已完整读取 PDF 四页、两幅图、两份 DOCX 全文及公式/表格；原件哈希写入 inputs_readonly_extract/input_sha256.json。
- Python 为用户指定路径；NumPy、SciPy、Matplotlib、pypdf 已存在，无新增安装。
- 用户要求先 CPU，覆盖通用规范中的远端优先；无远端任务。
- 用户要求唯一写入 B/，故通用 experiments/runs 目录也置于 B/ 内。
- 命令先保存；长实验通过 B/launch.py 启动后台进程。
- 不读取/修改 A/、C/，不导入旧探索代码，不产生公共目录 pycache。
- 不建立官方 HTTP 连接，不注册、不使用报名身份，不调用 /enter 到官方模拟器。
- 几何和物理/协议检查必须在正式离线比较前通过。
