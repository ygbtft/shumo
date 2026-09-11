# 发布 NTJ_B 分支

用户明确要求将当前 B 题工作区推送到 https://github.com/ygbtft/shumo.git 的新分支 NTJ_B。本次仅执行归档发布，持续算法优化仍暂停。

远端基线 b 为 253bf943a58d6f21de88f14fdc940da66b87ab96；查询时 NTJ_B 不存在。在本目录独立 clone 中创建分支，新增 B/，以及兼容原脚本相对路径的三份题面附件和 b_probe/common 依赖副本，保留原仓库内容及历史。工作区根目录不是 Git 仓库。

保留 B/ 代码、报告、配置、完整数值结果、参考资料和暂停状态。发布副本排除 .git、macOS/编译缓存、pytest 临时文件、PID 文件及 B/publish 递归目录；不删除原文件，不改 A/、C/ 或原题面。对发布文件检查秘密、大文件、符号链接、哈希和报告入口；结果不伪称全部通过。

固定当前源快照，使用已有 Git 身份提交，检查提交范围为 B/、CUMCM2026Problems/B题/ 及两个 project/topic_probes 依赖，推送 origin refs/heads/NTJ_B，不 force、不合并 b、不调用官方模拟器。以上副本的物理路径全部位于用户指定的 B/publish 内；原公共代码和原附件不写入。最后以远端分支提交 SHA 核验。
