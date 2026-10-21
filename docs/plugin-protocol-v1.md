# 插件协议 v1：chat-hpc-control

日期：2026-10-21。状态：规范提案；类型签名和配置片段用于设计评审，尚非可导入的软件 API。

本文的“必须”“拒绝”是未来实现的验收要求。入口使用 `chat-hpc-control/task/v1`，结果使用 `chat-hpc-control/result/v1`，Python 插件 API 为 `1.0`；项目发行版本拟为 `0.1.0`。三者与 QC 软件版本相互独立。

## 1. 插件类别与发现

| 类别 | entry point group | 责任 |
|---|---|---|
| QC 引擎 | `chat_hpc_control.engines` | 检查输入、生成执行计划、解析原始结果 |
| 执行器 | `chat_hpc_control.executors` | 提交、查询、核验身份、恢复未知提交 |

聊天客户端、传输层及发布器在首版采用项目内薄适配器，不提前提供第三方 Python 插件 ABI。它们依赖相同任务和结果 schema；有独立社区需求后再冻结其 entry point 协议。

引擎分发包的拟用声明如下。`example_qc` 是文档示例，不表示真实存在的包：

```toml
[project.entry-points."chat_hpc_control.engines"]
example-qc = "example_qc.plugin:create_plugin"
```

管理员安装并在站点配置中启用分发包。框架通过 `importlib.metadata.entry_points` 发现对象，固定分发包版本与来源摘要。重复 engine ID、API 主版本不匹配或未启用的插件在提交前拒绝。Issue、脚本和聊天内容不能指定 pip 包、任意 import 路径或动态安装指令。

加载插件会执行 Python 代码。插件属于管理员信任代码，须在无 GitHub 和模型凭据的工作进程中加载；仅做 entry point 枚举不能作为安全隔离。核心调用受控工作进程并校验其结构化响应。第三方插件安装权限不属于聊天工具权限。

## 2. 通用输入 TaskSpec

TaskSpec 及其嵌套对象拒绝重复 JSON key、未知字段、浮点 JSON 数值和不匹配的 schema；精确非整数参数使用十进制字符串。插件私有选项只放在 `engine_options`，并由该插件公开的 JSON Schema 校验。结果数值允许有限浮点数，规则见结果章节。

下面是一份待解析 Git ref 的示例，源仓库和文件均为虚构，不会执行：

```json
{
  "schema": "chat-hpc-control/task/v1",
  "task_id": "water-pbe0-001",
  "engine_id": "pyscf",
  "engine_options": {},
  "source": {
    "kind": "git",
    "repository": "https://github.com/example-lab/qc-inputs",
    "ref": "main",
    "files": ["tasks/water/job.py", "tasks/water/geometry.xyz"]
  },
  "entrypoint": "tasks/water/job.py",
  "resources": {
    "cpus": 4,
    "memory_mib": 4096,
    "walltime_seconds": null
  },
  "expected_results": {
    "contract": "energy-gradient/v1",
    "records": [
      {
        "record_id": "water-0",
        "quantities": ["energy", "gradient"],
        "atom_symbols": ["O", "H", "H"],
        "geometry_file": "tasks/water/geometry.xyz",
        "geometry_unit": "angstrom",
        "charge": 0,
        "multiplicity": 1,
        "method": "PBE0",
        "basis": "cc-pVDZ",
        "state_id": "ground"
      }
    ]
  }
}
```

规则：

- `task_id` 匹配 `[a-z0-9][a-z0-9._-]{0,95}`；属于站点内的逻辑名称。身份由不可变修订摘要决定，同一名称可有明确区分的修订，不能覆写原修订。
- `engine_id` 匹配 `[a-z][a-z0-9-]{0,47}`；从站点已启用集合选择。
- Git repository 必须属于允许列表；`ref` 在入口解析为完整 commit。冻结结果记录 commit、Git blob 身份及逐文件 SHA-256。后续提交使用冻结后的 ref，不再跟随分支。
- 冻结文件包来源采用 `source: {"kind":"bundle","bundle_id":"..."}`，由站点预先接收并给出不可变 ID；不接受任意文件 URL、任意本机路径或隐含的远端下载。Git 和 bundle 使用互斥 schema。
- 文件集合包含实际执行及解析需要的文件。路径为相对 POSIX 路径，拒绝 `..`、绝对路径、重复归一化路径及目录逃逸。`entrypoint` 和 `geometry_file` 均须在集合中。
- `resources.cpus`、`memory_mib` 为正整数；`walltime_seconds` 为正整数或 `null`，且必须显式提供。执行器须报告可接受上限与实际 enforceability；不得把 `null` 换成隐藏的框架超时。
- `expected_results` 可以为 `null`，此时允许执行和导出原始文件，完整性为 `UNVERIFIED`，不能 `data_ready=true`。非空合同时必须声明每条预期记录及所需物理量，不能用实际输出数量反推期望数量。
- `energy-gradient/v1` 允许单独 energy 或 energy+gradient；要求上述几何、方法、态、电子信息字段。geometry 匹配须由命名 parser profile 声明确定性容差及单位转换规则，配置和算法版本纳入解析身份。
- 软件参数不做统一分子／方法限制。`engine_options` 中不接受 shell 命令、凭据、运行目录或发布目标；原生计算内容在冻结输入中表达。

## 3. 冻结、哈希与版本

核心生成 `TaskManifest`，内容至少包括：schema、已解析的 TaskSpec、所有文件的相对路径／大小／SHA-256、引擎插件分发包与代码身份、执行相关运行环境和策略修订、执行器类型和已解析资源策略。

`manifest_sha256` 是以下 `canonical-json-v1` 字节的 SHA-256：UTF-8，无 BOM；对象 key 按 Unicode 码点排序；无缩进；分隔符为 `,` 和 `:`；非 ASCII 字符直接编码；不追加换行。禁止浮点 JSON 值，精确非整数参数使用十进制字符串并由字段 schema 解释；整数限制为正负 `2^53-1` 范围。禁止未配对代理字符。文件名按原样编码，拒绝归一化后冲突的名称，不隐式重写输入文件内容。

manifest 不包含自己的摘要、时间戳、请求身份、输出结果或模型会话 ID。完整冻结配置私有保存；其中影响执行的部分及秘密配置版本号进入指纹，秘密内容不写进 manifest。运行时间、实际分配和软件探测输出保存在后续执行证据中。结果解析器与发布器版本进入结果集合身份，更新它们不强迫重算输入。

**幂等执行指纹**绑定 manifest 摘要、目标 site 和实际执行器配置身份；提交时重新核验，偏移即拒绝。TaskRef 为 `{site_id, task_id, manifest_sha256}`。跨版本导入旧任务时保留旧算法／摘要，由 legacy envelope 引用，不用新算法重写旧身份。

任务 schema 主版本、插件 API 主版本变化都要求显式适配。v1 不静默接收新的未知字段；新增字段通过声明的新 schema 版本及转换器接入。插件 API 次版本只能增加经能力协商的可选方法，不改变既有方法语义。

## 4. 引擎接口

以下为语言层签名示意；类型名称由此文规定的序列化对象承载，非现有 Python 实现：

```python
class EnginePlugin:
    def info(self) -> PluginInfo: ...
    def probe(self, site_runtime: RuntimeConfig) -> ProbeReport: ...
    def validate(self, task: ResolvedTask, context: ValidationContext) -> ValidationReport: ...
    def prepare(self, task: FrozenTask, context: PrepareContext) -> ExecutionPlan: ...
    def parse(self, snapshot: OutputSnapshot, contract: ResultContract) -> ParseReport: ...
```

| 对象 | 必需内容 |
|---|---|
| `PluginInfo` | API 版本、engine ID、插件分发包／版本／来源摘要、选项 schema、输入类型、parser profiles |
| `ProbeReport` | 安装位置与实际程序版本、依赖/MPI身份、支持能力、失败原因；不返回密钥或许可证内容 |
| `ValidationReport` | 合法性、稳定错误码、字段问题、已解析任务、候选 manifest 摘要；不提交计算 |
| `ExecutionPlan` | 固定 argv 列表、环境允许项、工作目录 token、输入映射、输出收集声明、资源请求、程序身份 |
| `ParseReport` | parser ID/版本/代码摘要、实际方法与态证据、数值记录、缺失／歧义／错误项、原始来源位置 |

执行计划由核心再次验证后交给执行器。禁止 shell 字符串和 `shell=True`；可执行程序须是管理员配置并探测过的程序。工作目录由核心分配，输出规则受路径和体积策略限制。引擎不能读取 broker 的凭据或决定任意发布目的地。

该约束防止控制面误用 shell；它不使原生 Python 或 QC 输入变成沙箱。进程隔离和资源限制必须依执行器实际能力报告。

### 新 QC 引擎的最小实现

1. 提供插件元数据、程序探测和选项 schema。
2. 校验入口和依赖文件，构建固定 argv 执行计划。
3. 首先允许 `raw-only` profile，原始结果可收集，数值完整性为 `UNVERIFIED`。
4. 为可证实的方法／态添加命名 parser profile、原生小样本和缺失／歧义案例。
5. 管理员安装、显式启用并完成符合性检查后，工具能力列表才出现该 engine ID。

协议不要求每个插件同时支持能量、梯度和全部计算方法。能力声明必须区分“程序能计算”“插件会解析”“该组合已验收”。

## 5. 执行器接口

```python
class ExecutorPlugin:
    def info(self) -> ExecutorInfo: ...
    def probe(self, site: ExecutorConfig) -> ExecutorCapabilities: ...
    def submit(self, plan: ApprovedExecutionPlan, reservation_id: str) -> SubmissionReceipt: ...
    def query(self, handle: RunHandle) -> ExecutionObservation: ...
    def reconcile(self, reservation: Reservation) -> ReconciliationReport: ...
```

| 对象 | 必需语义 |
|---|---|
| `ExecutorCapabilities` | CPU/内存/时限限制，线程与硬限制区别，是否接受无限计算时限，重启恢复能力 |
| `ApprovedExecutionPlan` | 核心核验通过的计划、授权引用、manifest 和执行指纹、站点与执行器身份 |
| `SubmissionReceipt` | reservation ID、run ID、执行器句柄、持久回执位置、提交结果状态 |
| `RunHandle` | site、executor instance、native job ID、身份核验字段；local/TS 含 boot 与命令身份 |
| `ExecutionObservation` | 观察时间、执行状态、身份是否 VERIFIED、终态证据、退出码／终止原因、实际资源 |
| `ReconciliationReport` | 确认已提交、可证明未提交或仍未知；证据引用 |

executor 必须让长任务独立于控制进程运行，worker 自己落盘终态证据；不能仅把 `Popen` 返回视为持久提交成功。local 执行器需按 PID+启动身份核验，TS 需按队列命令+启动身份核验。

核心先创建 `RESERVED`，确认提交后进入 `QUEUED` 或 `RUNNING`。无法确认提交进入 `SUBMISSION_UNKNOWN`。运行归属无法确认时进入 `UNKNOWN`，该状态不等同失败或可重新提交。终态仅在可靠证据后记录：`COMPLETED`、`FAILED`、`CANCELLED`。外部取消可被观察，首版聊天工具不提供取消管理操作。

`COMPLETED` 需要程序成功退出和引擎所声明的正常终止证据。程序失败可产生有用文件，但执行状态仍为 `FAILED`。资源策略、进程状态、终态文件必须分别保留。

## 6. 结果和 parser profiles

| 字段 | 值及含义 |
|---|---|
| `execution_state` | 上述执行状态 |
| `integrity` | `VERIFIED` / `FAILED` / `UNVERIFIED`：输入、运行身份、输出摘要及来源闭合 |
| `completeness` | `COMPLETE` / `INCOMPLETE` / `INVALID` / `UNVERIFIED`：按声明的记录判定 |
| `scientific_acceptance` | 默认 `NOT_EVALUATED`；只有独立科学验收器附证据时可 `PASS` / `FAIL` |
| `data_ready` | 当且仅当执行 `COMPLETED`、完整性 `VERIFIED`、声明完整性 `COMPLETE` |

`INCOMPLETE` 指受支持解析下缺失预期记录／物理量；`INVALID` 指非有限数值、重复 ID、错误维度／单位／方法／态、几何不匹配或解析歧义；`UNVERIFIED` 指无合同、不支持的 profile、不可判定格式或必要证据无法读取。存在确定错误优先 `INVALID`，其次无法核验为 `UNVERIFIED`，再其次缺失为 `INCOMPLETE`，全部检查通过方为 `COMPLETE`。所有问题逐项保留。

数值记录最少包含 record ID、原子序列、几何来源及坐标单位、charge/multiplicity、method/basis/state ID、实际版本与收敛证据、原始文件及定位。能量统一 `hartree`，梯度统一 `hartree/bohr`、维度 N×3；力与梯度符号关系必须显式转换。保留原始单位、转换算法版本和转换前数值来源。

输出记录集合须与声明的 ID 一一对应，不允许通过去重、排序换原子或丢弃异常记录来“补齐”。输入合同和输出 metadata 不一致时报告差异。解析器不能仅复制合同里的方法和态作为输出证据；无法从所选 profile 的来源确认时必须 `UNVERIFIED`。PySCF JSON profile 的信息可能由用户脚本提供，要标记 `evidence_level=script-reported`，不能视为独立程序解析认证。

初始迁入的 profile 候选：

| profile ID | 目标 | 限制 |
|---|---|---|
| `pyscf-json-v1` | 脚本生成的声明式记录 | 附原生日志；脚本可信但非独立科学验收 |
| `orca-single-v1` | 单点原生能量 | 初始严格方法识别仅 RHF 单重态 |
| `orca-engrad-v1` | 单点能量和 `.engrad` 梯度 | 初始严格方法识别仅 RHF 单重态 |
| `molpro-table-v1` | 具名表格记录 | 记录、方法、态须唯一绑定 |
| `molpro-xml-single-v1` | 单点 XML 数值 | 先完整解析几何；SCF 梯度归属不得猜测 |
| `raw-only` | 任意已启用引擎 | 无数值完整性认证 |

QC 软件版本通过运行时探测固定；不承诺上述 profile 覆盖每一版本和方法。新增算法必须具有新解析身份，并对相同原始快照生成新集合版本，不改旧报告。

### 结果集合

每个集合包含 `summary.json`、`completeness.json`、数值记录、`provenance.json`、原始文件 manifest 和下载引用。所有内容具有摘要；collection ID 由输入身份、终态证据、输出快照、解析身份和合同生成规则共同确定。

集合内容不可变；索引是可更新的指针。发布回执记录目标固定 commit／对象版本、内容摘要、可见权限及保留期。原始文件超过站点配置的内联体积时走 Artifact/对象存储；续期追加回执，不能用同名文件静默替换。

## 7. 错误和符合性

工具错误采用 `{code, message, retryable, evidence_refs}`。稳定 code 至少包括 `AUTH_DENIED`、`SCHEMA_INVALID`、`SOURCE_NOT_ALLOWED`、`INPUT_CHANGED`、`PLUGIN_INCOMPATIBLE`、`CAPABILITY_UNSUPPORTED`、`RESOURCE_UNSUPPORTED`、`IDEMPOTENCY_CONFLICT`、`SUBMISSION_UNKNOWN`、`JOB_IDENTITY_UNVERIFIED`、`RESULT_UNVERIFIED`、`PUBLISH_UNKNOWN`。

`retryable=true` 仅表示同一语义请求可以重试；不能授权新计算。提交结果未知时须复用原幂等 key 并先 reconcile；发布未知时先对固定内容 readback，不生成不关联的重复集合。

后续插件符合性材料包括：入口 schema、固定 argv 样例、软件探测证据、最小原生输出 fixture、缺失/异常输出 fixture、可复现解析结果、资源能力声明和凭据隔离检查。核心 CI 的发现范围必须限定在专用测试目录，避免将冻结 PySCF 输入当作测试执行。当前文档阶段未添加或运行这些软件测试。

## 8. 参考

- [PyPA：创建与发现插件](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)：entry point 机制。查阅日期：2026-10-21。
- [架构说明](superpowers/specs/2026-10-21-chat-hpc-control-v0.1-design.md)：模块边界与范围。
- [聊天接入](chat-integrations.md)：公共工具与客户端约束。
