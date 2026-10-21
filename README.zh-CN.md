# chat-hpc-control

面向社区的多模型原生量化计算控制框架，当前交付为 **v0.1 本地发行候选**。
现有生产站点不属于本项目的迁移范围，本次未改变其部署。

- [中文 quickstart](docs/quickstart.zh-CN.md) / [English](docs/quickstart.md)
- [站点配置](docs/site-guide.md)、[插件教程](docs/plugin-guide.md)
- [结果规则](docs/results-guide.md)、[发布与原始文件](docs/publication-guide.md)
- [兼容性矩阵](docs/compatibility.md)、[验收报告](docs/v0.1-acceptance.md)

支持原生 PySCF Python、ORCA 和 Molpro 输入。分子与方法由冻结输入决定；
程序能运行、解析器支持、数值齐全和科学通过分别记录。Linux x86_64 提供
local/独立 Task Spooler 执行器；macOS 提供核心协议与客户端能力。

任务显式声明 CPU、内存和时限。`walltime_seconds: null` 不设置框架计算超时；
站点明确设定上限时会拒绝不兼容请求。内存为 advisory，CPU affinity 不代表
独占分配。原生脚本及插件属于可信代码，框架不是沙箱或匿名多租户服务。

结果采用不可变集合和固定分页。只有执行完成、证据闭合、声明的数量与物理量
齐全时 `data_ready=true`；科学验收默认 `NOT_EVALUATED`。模型 SDK 可选，
OpenAI/Anthropic/Gemini 的协议与 SDK 测试不能替代真实 API 或网页产品验收。

本地候选包含代码、测试、示例、文档和发行产物；没有推送或实际发布，没有使用
生产凭据或付费模型调用。新代码采用 Apache-2.0，商业程序及许可证由站点提供。
