# 运行前检查

已下载用户指定b分支到独立B/副本，提交253bf943a58d6f21de88f14fdc940da66b87ab96。网页工具两次无法取回GitHub页面，git clone成功，以下依据实际提交文件，不依据缓存摘要。

四组固化案例文件均已存在，分别285、330、531、48例，不调用随机生成器。生产代码/案例哈希另存upstream_input_sha256.json，原报告另存original_reports。执行在upstream_worktree拷贝内，参考仓库、此前上游及原始题面只读。

指定Python与现有依赖可用：numpy2.1.3、scipy1.15.3、matplotlib3.10.0、pytest8.3.4、mpmath1.3.0。无需安装依赖。运行环境禁止pyc和pytest外部插件，临时目录、pytest工作目录和绘图库缓存均位于B/；CPU单线程。

尚未宣称任何新测试通过。HANDOFF公布通过率仅作待复核对照。此前Q3/Q4优化工作已按用户要求停止；157—166未生成。
