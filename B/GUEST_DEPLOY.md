# Q3、Q4 Windows运行包

当前交付包为[dist/q34-formal2.zip](dist/q34-formal2.zip)，代码和参数见[Q34_CURRENT.md](Q34_CURRENT.md)。Python须安装NumPy、SciPy；实际测试使用Windows ARM64 Python 3.14.7。

解压后先执行`python run_q34_official.py --problem 3 --check-config`及问题4对应命令核对参数。配置检查不访问官方接口。模拟器与机器人须在同一台Windows机器，官方接口为`127.0.0.1:2026`。

当前整理代码已在原Windows环境通过27个保存案例的无网络回放，5746条指令全部匹配，坐标差为0。记录见[replay.json](cleanup_formal2/replay.json)。此过程没有启动新的演练或正式测试。
