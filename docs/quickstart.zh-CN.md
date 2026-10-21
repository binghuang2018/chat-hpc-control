# 全新 Linux 站点入门

需要 Linux x86_64、Python 3.11–3.13。演示不需要 QC 软件、API key、root、旧账号、
runner 或 Task Spooler。请选择较短的新目录，避免 Unix socket 路径长度限制。

```sh
python3 -m venv /tmp/chc-venv
/tmp/chc-venv/bin/python -m pip install ./dist/chat_hpc_control-0.1.0-py3-none-any.whl ./dist/chat_hpc_demo_engine-0.1.0-py3-none-any.whl
/tmp/chc-venv/bin/chat-hpc-control demo --root /tmp/chc-demo
```

源代码目录先本地构建核心 wheel/sdist 和独立 demo wheel：

```sh
python3 -m pip install build
python3 -m build --outdir dist
python3 -m build --wheel --outdir dist examples/plugins/demo-engine
```

演示在独立 `example-demo` 站点执行公开 CLI 的 validate→submit→status→results，
保存冻结输入、幂等意图、回执及结果集合。正确输出包括：执行 `COMPLETED`、集合 ID、
`synthetic=true`、`data_ready=false`。这里没有声明科学结果合同，演示数值不是物理结果。

```sh
/tmp/chc-venv/bin/chat-hpc-control demo --root /tmp/chc-demo --resume
```

续接必须返回同一 run ID，不因客户端超时换 key 重算。`--wait-seconds` 只限制演示的
控制等待，不限制计算时长。演示仅停止自己创建的 broker；服务/cgroup 对长任务的影响
需在实际新站点另行验收。

真实任务先使用站点配置启动 broker，再导入冻结文件包或使用允许列表内的固定 Git
来源；保存 validate 返回的固定任务和摘要后提交。输入、CPU/内存及所需物理量必须明确。
示例 task.json 的全零 bundle ID 是占位符，不能直接提交。

商业 QC 软件不随框架分发；原生脚本是可信代码，不是沙箱。原始数据完整、量齐全和
科学通过分别判断。详情见 [站点指南](site-guide.md)、[结果指南](results-guide.md)
及 [兼容性](compatibility.md)。
