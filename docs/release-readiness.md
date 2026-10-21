# 社区发布条件

日期：2026-10-21。当前状态：独立本地设计项目，没有公共远端、发行包、可执行 Action 或发布版本。

## 1. 发行边界

拟用名称统一为 `chat-hpc-control`，Python 导入名为 `chat_hpc_control`。GitHub repo、PyPI 发行名和 CLI 名称分别核查可用性；本地命名不等于外部名称已注册。

建议以一个 Python 项目承载核心协议、CLI 和首批引擎／执行器实现；GitHub Action 只负责安装固定版本及转换调用。可选模型客户端依赖分别安装，核心不要求任何模型 SDK。Action 的可执行 metadata 与 workflow 在实施阶段生成，本次没有生成可误用的安装命令或发布标签。

首版内置演示站点和合成输入，商业 QC 引擎仅提供接口和管理员配置方法。依赖的软件及许可证由站点自行提供。

## 2. 发布前阻塞项

- [x] 用户于 2026-10-21 确认书面架构及上述设计范围。
- [ ] 审阅已编写的 [v0.1 实施计划](superpowers/plans/2026-10-21-v0.1-implementation.md)，选择执行方式。计划编写已完成，尚未开始实现。
- [ ] 核心、CLI、QC 插件、local/TS、GitHub、MCP 和客户端适配器按实际实现状态验收。
- [ ] 为 demo engine 编写独立扩展示例，证明不修改核心即可接入新软件。
- [ ] 决定 Python 支持版本与依赖矩阵，并冻结构建和发布流程。
- [ ] 对输入授权、幂等／故障恢复、运行身份、资源、结果和发布回执进行专项验证。
- [ ] 用全新目录／环境完成用户文档中的安装和 quickstart，而非借用旧站点安装。
- [ ] 三种模型 API 和各网页／桌面产品逐项分级；未实测的连接明确写“计划”。
- [ ] 检查文档和源码中私有路径、账号、内网地址、真实科研任务、结果、凭据及历史提交。
- [ ] 确认所有迁入代码和 fixture 可再分发，包含必要归属声明。
- [ ] 所有者明确选择 LICENSE。当前提案 Apache-2.0 尚未授予，不假定旧私有源码已有开源许可。
- [ ] 确认公共仓库所有者／可见性、包名和发布目标，再执行发布。

## 3. 文档和贡献要求

v0.1 实现完成时至少提供：安装、合成输入 quickstart、站点配置、资源和权限说明、PySCF/ORCA/Molpro 示例、第三方插件教程、多模型接入矩阵、结果读取示例、版本兼容说明及迁移／回退操作文档。

当前完整规范为中文，已提供英文 README。社区发布前补齐英文 quickstart 和插件开发指南，并保持协议字段与中文规范一致；不把语言覆盖尚不完整的材料称为完整国际化文档。

贡献 QC 插件需附：软件版本、安装前提、原生输入格式、资源与 MPI 启动方式、支持和不支持的方法／态解析范围、合成或获准公开的输出 fixture、失败案例、许可证边界。禁止提交商业程序、许可证文件、真实 API token 或未经许可的研究数据。

维护者评审时分别记录：代码质量、控制面安全、运行完成、文件完整性、数值完整性及科学验收；一个维度通过不能替代另一个维度。用户选择无计算时限不取消 CPU/内存声明与站点授权要求。

## 4. 发布回执

后续发布记录须包含：源码 commit、构建依赖、分发文件 SHA-256、软件包版本、插件 API/schema 版本、兼容性矩阵、已执行验收和明确缺口。Action 引用应提供固定 commit 的使用方法，包与 Action 的对应关系可追溯。

公共文档应说明它提供计算控制及证据，不保证任意科学输入得到正确的物理结论。未实现接口、未实测产品和未来 Slurm 支持不得标为当前能力。

## 5. 官方参考

- [GitHub 自定义 Actions](https://docs.github.com/en/actions/concepts/workflows-and-actions/custom-actions)：后续 Action 分发与元数据设计参考。
- [PyPA 插件发现](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)：引擎和执行器扩展机制。
- [OpenAI MCP](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)、[Anthropic MCP connector](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)、[Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)：多模型工具接入机制。

参考查阅日期：2026-10-21；实施和发布前应重新核对相关版本。厂商文档证明接口机制，不证明本项目已实现或通过实测。
