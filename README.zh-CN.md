# chat-hpc-control

面向社区的聊天模型与 HPC 计算控制框架，首版聚焦量子化学任务。

## 当前交付

本目录是 **2026-10-21 的 v0.1 设计项目**，已统一命名为 `chat-hpc-control`，拟用 Python 命名空间为 `chat_hpc_control`。本阶段交付架构说明、插件协议和迁移清单，尚无可安装的软件包、可运行的 Action、MCP 服务或模型 SDK 适配器。

| 文档 | 内容 |
|---|---|
| [v0.1 架构说明](docs/superpowers/specs/2026-10-21-chat-hpc-control-v0.1-design.md) | 模块边界、数据流、授权、任务生命周期、首版范围 |
| [插件协议 v1](docs/plugin-protocol-v1.md) | QC 引擎、执行器、任务输入、结果、第三方扩展规则 |
| [聊天模型接入](docs/chat-integrations.md) | ChatGPT/OpenAI、Claude/Anthropic、Gemini 共用工具及接入矩阵 |
| [迁移清单](docs/migration-checklist.md) | 从现有 hpc-control 提取、兼容、旁路核验、切换与回退 |
| [社区发布条件](docs/release-readiness.md) | 文档、许可证、脱敏、发布和验收边界 |

## 核心约定

- 不绑定聊天模型厂商；模型 ID 与 API 凭据由使用者在客户端配置。
- GitHub、CLI、MCP 共用 broker；聊天模型不能自行授予提交权限。
- 接受任意分子的原生 PySCF Python 脚本、ORCA/Molpro 输入，通过固定提交或冻结文件包登记来源和哈希。是否需要人工审核由站点策略决定，不把节点本地人工登记设为框架的统一前提。
- 核心不内置计算时长上限；`walltime_seconds: null` 表示不由框架设置计算超时。外部调度器、站点和 GitHub 控制流程的限制须单独报告。
- 原始结果、完整性、执行状态和科学验收分别记录；`data_ready=true` 不代表科学结论已获验证。
- 通过 QC 引擎插件接入新软件；核心不携带商业软件、许可证或模型 SDK。

## 与现有部署的关系

现有 `hpc-control` 和 n008 继续独立运行。本次仅在新的本地目录编写设计文档，未改变服务、队列、已登记输入、历史结果、运行环境或仓库远端，也未推送或发布公共仓库。

依照 `brainstorming` 技能的架构流程，下一阶段先审阅本次书面设计，再编写实施计划；软件实现与部署须在之后进行。
