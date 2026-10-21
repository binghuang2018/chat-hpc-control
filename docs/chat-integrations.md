# 多聊天模型接入设计

日期：2026-10-21。状态：接口提案；本项目尚未实现或实测厂商 SDK、MCP 服务及网页应用连接。

## 1. 命名与接入分级

ChatGPT 是 OpenAI 的产品，Claude 是 Anthropic 的产品，Gemini 是 Google 的模型／产品系列。项目采用 `chat-hpc-control` 名称，避免将计算控制协议绑定某一聊天产品。

以下矩阵区分“厂商文档提供了机制”和“本项目已经接通”。官方机制存在，只用于确认设计方向可行，不能当成本项目兼容性测试。

| 目标 | 官方机制／拟接入路径 | v0.1 设计边界 | 本项目状态 |
|---|---|---|---|
| OpenAI API | Responses 工具调用或远程 MCP | 公共工具转换；认证由 broker/网关处理 | 计划，未实现／未实测 |
| ChatGPT 网页／桌面产品 | 以当时产品支持的自定义工具／MCP 接入方式核实 | 按账号、工作区、网络和审批条件单独验收 | 计划，未验证可用性 |
| Anthropic API | Messages 工具调用或 MCP connector | API 接入与可用 transport 按官方版本适配 | 计划，未实现／未实测 |
| Claude 网页／桌面产品 | 以当时客户端支持的连接方式核实 | 不把 Messages API 能力等同产品账号能力 | 计划，未验证可用性 |
| Gemini API | Function calling，由客户端转公共工具 | 先支持客户端执行调用；不依赖原生远程 MCP | 计划，未实现／未实测 |
| Gemini 网页产品 | 单独核实可扩展机制 | 不承诺任意第三方 MCP 连接 | 延后验证 |
| CLI / GitHub | 相同 broker 契约，无模型 API 依赖 | 可不使用任何聊天厂商或 API key | 计划从旧实现提取 |

OpenAI 官方文档说明 Responses 可使用 MCP 服务；Anthropic 官方文档说明 Messages 可通过其 MCP connector 调用远端工具。Gemini 官方文档说明 function calling 可产生外部函数调用参数。由此推导，统一工具后分别包装 API 是可行设计；这仍需要各客户端独立实现和实测。[OpenAI MCP](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)、[Anthropic MCP connector](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)、[Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)。查阅日期：2026-10-21。

## 2. 公共工具表

工具名字和输入语义与厂商无关。传输层注入认证上下文，模型不能在参数中声明自己有管理员权限。

| 工具 | 输入 | 输出 | 副作用／权限 |
|---|---|---|---|
| `list_capabilities` | `site_id` | 可用引擎、profile、执行器、资源策略和版本 | 只读；`capabilities:read` |
| `validate_task` | `site_id, task` | 字段问题、已固定 commit 的任务、候选 manifest 摘要 | 读取允许的来源；不登记任务或入队；`tasks:validate` |
| `submit_task` | `site_id, task, expected_manifest_sha256, idempotency_key, rerun_of` | TaskRef、run ID、执行状态、提交回执 | 登记与入队；`tasks:submit` |
| `get_task_status` | `site_id, run_id` | 状态、身份核验、资源、时间、证据引用 | 只读；`tasks:read` |
| `get_task_results` | `site_id, run_id, collection_id, fields, cursor, page_size` | 记录分页、四类状态及下一页游标 | 只读；`results:read` |
| `get_result_manifest` | `site_id, run_id, collection_id` | 内容摘要、原始包引用、权限和有效期 | 只读；`results:read` |

`task` 是[插件协议](plugin-protocol-v1.md)的 TaskSpec；`validate_task` 返回完整 commit 和计算候选摘要。首次 `submit_task` 使用该已解析对象和摘要，服务端重新冻结并比较；若执行配置、策略或来源已变，返回 `INPUT_CHANGED` 并要求重新 validate。客户端不能只传任意摘要跳过验证。对已有 key 的重试，先核验访问权限并比较保存的请求和摘要；一致则返回原回执，不因环境升级重新冻结或提交。

`rerun_of` 首次提交为 `null`；显式重算指定旧 run ID 并使用新幂等 key，仍须具备提交权限。并行调用相同任务使用相同 key 时只能返回同一运行。不同 key 被视为显式不同执行，客户端不得在网络重试时自动生成新 key。

结果读取的 `collection_id: null` 表示由服务端在首个响应解析为当前固定集合 ID；后续分页必须带该 ID。`fields` 从公开字段枚举中选择，`page_size` 为 1–100，游标绑定集合与字段，不能跨版本拼页。Artifact 暂时失效不改写计算或解析状态；下载可用性另行报告。

发布、续期、取消、删除、配置修改与插件安装不放入首版聊天工具集合，采用单独授权的运维入口。读取某个 run 仍须核验所属站点、所有者和共享权限，不能仅凭 run ID 获取其他人的数据。

### Schema 示例

以下是通用工具定义，适配器将其包装为厂商要求的格式。示例没有服务器地址和凭据，不是可直接调用的部署配置。

```json
{
  "name": "get_task_status",
  "description": "Read an authorized HPC run's observed execution state and evidence.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "site_id": {"type": "string", "minLength": 1},
      "run_id": {"type": "string", "minLength": 1}
    },
    "required": ["site_id", "run_id"],
    "additionalProperties": false
  }
}
```

完整 schema 的未知字段、类型、枚举和哈希校验由 broker 再做。某厂商的 schema 子集不能表达约束时，适配器保留服务端校验；不能把 schema 不兼容转为允许更多命令或参数。

## 3. 调用和返回语义

客户端适配器只做：发布工具定义、验证和转换参数、调用 broker、转换结果及错误、保存厂商调用 ID。它不能选择跳过授权、替换输入、提高资源、放宽结果合同或在失败时猜测重新提交。

`submit_task` 是异步请求。返回 `QUEUED` / `RUNNING` 后立即结束工具调用，聊天端稍后调用状态工具，不维持覆盖整个计算的 HTTP/API 长连接。API 断连不取消计算；切换模型不产生新的执行。

站点 reconciler 独立观察和收集结果。查询响应包含 `observed_at`、`collection_state` 和发布状态；执行 `COMPLETED` 而集合仍待收集时，明确返回未准备好，不能提前报告可用于数值实验。

公共响应 envelope 包含 `schema, request_id, ok, data, error`，其中 `schema` 固定为 `chat-hpc-control/tool-response/v1`。成功时 error 为 null；失败时 data 为 null，error 包含稳定 code、retryable 与证据引用。执行失败可以是成功读取到的任务状态，不等于工具传输失败。

厂商 call ID 只关联一次对话回执；幂等身份来自持久的 `(site, principal, idempotency_key)`。principal 由服务端认证决定；不同客户端若登录为同一主体可查询同一个 run，是否允许跨主体共享由站点 ACL 决定。

## 4. GitHub、MCP 和 API 的边界

- GitHub adapter 将 Issue 与触发事件转换成同一任务契约。旧 Issue 的 marker、任务 ID 和状态映射通过迁移兼容器处理，不能借助编辑 Issue 绕过已冻结输入。
- MCP 服务暴露上述工具，不向模型开放任意 SSH、shell 或文件系统入口。只读提示是客户端提示，真正权限在服务端执行。
- MCP 远程连接要求认证和明确的结果访问范围。连接放在可达的控制网关，不要求把计算节点的 SSH 或监听端口直接暴露到公网。
- 本地 MCP 客户端可经 stdio 调用；远端服务的网络 transport、授权方式及厂商限制在实际接入时分别验证。某厂商 API 是否直接支持本地 stdio 不影响 CLI 和 broker 的任务语义。
- 需要原生 API 工具循环时，在客户端持有 OpenAI/Anthropic/Google API key。计算环境不接收这些 key；未使用厂商适配器时不要求任何模型凭据。
- 模型调用审批和站点提交权限是不同检查。既有授权可以持续生效，不要求用户每次查询都重新确认；无授权时模型不能自行批准。

## 5. 数据和结果交付

默认工具只返回可用能力、请求摘要和所选数值字段。原始日志、研究结构、完整脚本不自动发送给模型厂商。用户选择获取原始结果时，再按授权返回内容或有限期引用，并说明体积和有效期。

对数值实验，客户端固定 collection ID、输入 manifest、方法与态、单位和记录 ID；不得将不同集合分页或不同解析版本的能量／梯度拼成同一数据集。模型解释不能覆盖原始证据或把 `NOT_EVALUATED` 改为科学通过。

## 6. 接入验收分级

1. **规范已定义**：工具 schema、错误和幂等规则已书面定义。本次达到这一层。
2. **模拟调用通过**：各适配器通过相同的 schema、重试和权限 fixture；不要求真实厂商账号。
3. **API 实测通过**：记录厂商、API/SDK 版本、用户选择的模型 ID、认证方式与原始调用证据。
4. **产品端实测通过**：逐一记录网页／桌面产品、账号或工作区约束、连接方式和读写能力。

在达到相应层级前，README 只能写“设计支持／计划接入”，不能写“所有 ChatGPT、Claude、Gemini 用户可直接使用”。
