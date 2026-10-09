# 项目工具链

本参考用于长程开发、递归模块变更、多执行者协作和交接。技能指导设计与判断；工具精确查询和操作；项目文件保存事实。具体业务语义由 AI 根据需求编写。现有功能簇全景、深度设计、动态专业子能力、质量分析和故障探针继续适用，不因工具化缩减。

先按 LAYER 的路径规则解析 `taskarch.py`，保持工作目录为调用方项目。以下用 `<taskarch_path>` 表示解析得到的完整脚本路径；Python 3.9+ 是工具运行要求，项目语言和源码后缀不限。

```text
项目根 architecture.json
  ├─ 模块目录/architecture.json → 本层源码、测试与子模块路由
  └─ architecture/toolchain/ → 变更、事件、交接、快照；不是业务架构第二真相源
```

目录包含树负责逐层定位，模块依赖图负责检查影响。任何有限深度可递归，不按层数强行拆模块。父模块可有源码，查询允许跨模块，写入范围显式登记。全局能力安装目录与本能力仓库均禁止保存项目状态。

## 操作与返回

```bash
python "<taskarch_path>" --project "<项目根>" --architecture architecture.json query search --query "退款"
python "<taskarch_path>" --project "<项目根>" query context --selector "module:refund"
```

全局参数放在命令组之前。正常操作和错误均输出 JSON：`schema_version / operation / status / code / data / evidence / limitations`。`pass=0` 表示该操作完成，`fail=1` 为已知冲突或拒绝，`unknown=2` 为输入、能力或证据不足。`--help` 为常规帮助文本。`change.verify` 和 `project.gate` 的顶层状态直接表达真实门禁结果，其余操作成功不等于任务验证通过。旧工具继续保留各自公开退出码，维护清单记录其差异。

查询分页明确 `total/offset/limit/has_more`，事件分页明确 `after/limit/next_after/has_more`，不静默截断事实。对象 ID 是类型加 URL 编码编号，如 `behavior:refund-rule`；模块可用无歧义模块编号。显式编号与路径分离，迁移后保持身份。无编号记录使用标注为不稳定的物理 Pointer 身份，应在需要持续追踪时补显式编号。

| 命令组 | 操作 | 用途 |
|---|---|---|
| query | index/search/read/expand/context/route/impact | 六类事实、定位、上下文、包含与依赖影响 |
| change | begin/stage/preview/read/status/list | 记录目标与依据、暂存操作、查看差异 |
| change | coordinate/apply/verify/accept/abort/recover | 跨模块协调、应用、真实门禁、接受与恢复 |
| lease | claim/renew/release/list | 模块写入责任、过期与冲突 |
| handoff | export/resume/list | 换会话或执行者后复核依据并接力 |
| run | begin/status/pause/resume/step/end/guard/record | 可观察操作的暂停点和单步 |
| checkpoint | capture/preview/restore/recover/list/restore-list | 共同恢复架构与源码，保留恢复日志 |
| timeline | show | 完整事件 JSON 或独立 HTML 时间线 |
| project | gate | 既有严格完整交付门禁 |

`query index` 每次从真实权威文件重建，不将缓存作为架构。索引含模块、行为、契约、数据、测试和决策，关系保留包含、依赖、实现、消费者与测试的区别。搜索仅给候选；未知引用、重号、自然语言关系和缺失文件明确诊断，不猜连线。`context` 返回当前目标、上层约束、相关依赖与消费者、契约、实现和测试路径、未决项及来源。每项事实有物理文件、JSON Pointer 和 SHA。允许继续展开；不按固定小预算裁掉必要事实，也不预先承诺节省 token。

## 从任务到接受

变更操作通过 `--input <UTF-8请求文件>` 提交对象。简单字段也可用同名命令参数，二者冲突会拒绝。请求文件建议放项目之外或 `architecture/toolchain/requests/`，避免建立依据后又把临时请求文件加入受校验项目输入。`request_id` 必须由调用者生成，同一操作重试保持原值；不同内容复用同一值会拒绝。缓存回执代表原操作结果，当前证据是否仍然有效由接受时重新核验。

1. 先查询目标，取得充分功能全景与本次工作上下文，设计方案。
2. `change begin` 保存目标、明确模块范围和当前输入快照。
3. `change stage` 在隔离临时目录应用操作，只有整批结构、归属和引用可用才保存暂存结果。
4. `change preview` 查看完整差异、包含与声明依赖影响；此时项目源码未改。
5. `change apply` 检查依据、其他租约与未恢复日志，持久化原像后先写架构，再写源码。
6. 用项目真实分析器、测试和 `run_verification.py` 取得当前版本证据；按需运行原质量探针与专业能力核验。
7. `change verify` 执行原严格总门禁并保存本次输入和工具版本；失败或未知不能接受。
8. `change accept` 再次检查证据、恢复分支、参与者与未决项，留下已接受记录。它不会创建 Git 提交或推送。

这是可反复查询与修正的工作路径，不是固定业务方案。轻量查询可直接调用 query；一次性实验不强制建立全部流程。

建立请求：

```json
{"actor":"worker-1","goal":"补齐退款失败边界","scope":["refund"],"request_id":"refund-begin-1"}
```

```bash
python "<taskarch_path>" --project "<项目根>" change begin --input "<begin.json>"
```

暂存请求中的 `id` 使用 begin 返回的 change ID。结构化编辑只作用于真正声明该事实的物理架构文件，不写合成 `模块目录/模块归属事实`：

```json
{
  "actor":"worker-1","id":"<change-id>","request_id":"refund-stage-1",
  "operations":[
    {"type":"set","file":"refund/architecture.json","pointer":"/模块详情/refund/错误边界","value":"无效金额拒绝；重试保持幂等"},
    {"type":"write","file":"refund/service.any","text":"具体语言源码由 AI 根据项目编写"}
  ]
}
```

支持的暂存操作：

| type | 必要字段与含义 |
|---|---|
| set | file、pointer、value；父级必须已存在；数组 `/-` 可追加 |
| remove | file、pointer；字段必须存在 |
| write | file，以及 text 或 base64 二选一；保留任意语言字节 |
| delete | file；必须删除真实已存在的源码，并在同批架构中移除登记 |
| module.create | parent、directory、module、name、responsibility；directory 相对父架构目录；创建后自动纳入本次明确范围 |
| module.move | module、to_directory、可选 parent；目标目录相对项目根；稳定编号不变 |

新源码必须在暂存后的实现清单登记；行为中引用别人的源码不会取得写入归属。创建模块需父模块已在 scope，骨架保留设计占位符，不假装完成。移动必须包含原父、新父、整棵子树和实际需更新引用的其他模块；不够时拒绝并提示扩展。迁移同步真实路由和显式模块树的父子关系，更新清单、落位等已声明的精确路径引用（含 `file::case` 测试选择器）；源码中的动态导入、业务字符串和自然语言路径需 AI 与项目原生验证处理。未声明为路径的同值字符串保持原值，并在预览中列出待审候选。

单次 stage 是完整可预览批次。可把创建模块、补齐模块字段、登记源码及写入源码放同一批。`set` 可局部编辑任意已声明业务字段，不限制功能发现或设计深度。

后续命令：

```bash
python "<taskarch_path>" --project "<项目根>" change preview --id "<change-id>"
python "<taskarch_path>" --project "<项目根>" change apply --id "<change-id>" --actor worker-1 --request-id refund-apply-1
python "<taskarch_path>" --project "<项目根>" change verify --id "<change-id>" --actor worker-1 --request-id refund-verify-1
python "<taskarch_path>" --project "<项目根>" change accept --id "<change-id>" --actor worker-1 --request-id refund-accept-1
```

verify 检查已有事实和收据，**不自动执行策略里任意声明命令**。测试仍由已授权执行者显式运行；门禁要求当前适用质量规则与事实，缺失为 unknown。CRAP、接口契约、依赖边界、循环、决策、收据、故意改坏测试继续由原质量工具处理；没有通用源码语义解析器的承诺。

默认依据范围为项目普通文件，明确排除版本库、依赖安装目录、Python 缓存和工具链自身状态；文件集合及摘要随变更保存。新增、移除、内容变化均使原依据失效。此保守范围可能让无关文件变化也要求重新协调；当前不声称精确判断全部语义影响。大型生成目录应在工程配置中清理或在项目外保存，勿把无关生成物不断写入受验证输入。

应用先将完整原像与目标摘要写入 SQLite 日志，再修改文件。元数据事务可协调遵循协议的写者；外部编辑器、文件系统故障、服务调用不受同一事务覆盖。每个文件替换前再查原像；中断状态持久存在。`change recover --id ... --actor ...` 仅回滚本变更已写且仍匹配原像/后像的文件；第三方编辑会被保留并阻断恢复。`abort` 对 draft 放弃；对已应用变更仅在后像未改时撤回，不重置整个项目。接受后用新变更处理后续修改。

## 协作与交接

```bash
python "<taskarch_path>" --project "<项目根>" lease claim --actor worker-1 --modules refund --ttl-seconds 300
```

claim 返回 ID 与 token。renew/release 需要 id、actor、token。父子范围互斥，兄弟可并行；过期可重领，过期持有者不能续旧权。租约是合作客户端的责任登记，不是系统权限或隔离沙箱。

跨模块提案通过共同 change 记录组织。`change coordinate` 请求中的 `action` 可取：

- `expand`：发起者在 draft 提供完整 scope，检查依据后扩大明确范围。
- `refresh`：先读 preview 中完整 `current_inputs`，审查变化后以 `expected_current` 原样提交。只允许本变更将写入的文件原像未变时刷新其他依据；自身文件已有修改须明确重新设计，不能静默合并。重新确认会清除旧参与者就绪记录。
- `participant`：提供 module、status（pending/ready/blocked）、note；记录当前依据、暂存操作版本与分支。
- `unresolved`：发起者提供 items 数组保存未决事项。

参与者 ready 必须对应最终实际输入和暂存操作，修改后需重新确认。已登记参与者 blocked/pending、依据过期或仍有未决项时禁止接受。单个执行者可顺序处理多个模块，无需每个模块常驻 AI。actor 是审计标识，不是身份认证；语义冲突仍需审查及行为测试。

handoff export 请求包含 actor、modules、next_step，以及可选 unresolved、constraints、to_actor。交接包带完整相关上下文、文件/目录版本、当前活动变更与下一步。resume 使用 id、actor；重新检查文件集合、活动变更版本和责任冲突。成功只返回可继续依据，不自动转移租约或证明任务完成。

## 工作流调试与检查点

run begin 请求包含 actor、goal、breakpoints 数组（操作名 glob，如 `change.*`）。在命令尾加 `--run <run-id> --actor ...`，工具先 guard，实际执行后 record 输入和结果。遇暂停点返回 unknown/permitted=false，操作尚未执行；用 run step 允许一次操作，结束后自动暂停；resume 持续执行；pause 等待当前可观察边界。status 可查看当前操作；end 需要没有未记录操作。直接接工具 API 时用 guard/record 显式配对，崩溃的外部操作可用 unknown 及原因记录。

这套调试记录面向查询、补丁、验证等可观察操作，不观察隐藏推理，也不暂停任意宿主进程。

checkpoint capture 请求包含 actor、label、可选 files 数组。自动捕获所有权威架构与登记源码/测试，任意后缀按原始字节保存。恢复分三步：

1. `checkpoint preview --id ...` 输出目标、当前摘要，以及后来新增的受管路径和拟删除文件。
2. 把返回的完整 `expected_current` 作为 restore 请求字段，包含 id、actor。
3. restore 复查整个集合，先写持久日志，恢复架构和源码，创建新分支记录，验证状态回到 unknown。

当前架构正常时恢复受管树：后来新增登记的模块架构及源码可在明确预览后删除；未登记文件与目录保留并显示。当前架构损坏时只恢复已捕获路径，mode=captured_only 与未知项明确显示。外部服务、数据库副作用、未捕获文件不会被撤销。中断恢复用 checkpoint recover；并发编辑冲突保持现场。未完成的检查点恢复与变更应用互相阻断，避免两个写日志交错。

```bash
python "<taskarch_path>" --project "<项目根>" timeline show --after 0 --limit 100
python "<taskarch_path>" --project "<项目根>" timeline show --format html --output reports/new-timeline.html
```

HTML 输出需要项目内新的相对路径；默认查看事件摘要，按需展开完整详情，支持全文搜索、事件类型筛选和批量展开/收起。分页范围始终显示，筛选只作用于本次导出的页。全部事件详情保留并转义输入，支持直接查看，不是独立 IDE。事件有顺序、输入/结果及哈希链；可检测意外损坏，但不是签名或防恶意重写认证。读操作不创建项目状态；显式记录工作流、交接、输出 HTML 等操作按其契约写入。

## 维护与验证

旧 CLI 持续可用，`taskarch_cli.py` 的原 slice/gate-file/lineage 保留，新命令组转发统一核心。需要一次完整受管修改时优先新变更入口；直接旧工具或编辑器修改后，已有变更会按输入摘要识别过期。

工具维护清单由实际文件、AST 参数、依赖、类/函数签名和测试引用重建：

```bash
python "<check_toolchain_inventory_path>" --json
python "<check_toolchain_inventory_path>" --verify-help --json
```

第二条显式执行已审阅工具帮助，仅证明入口可运行。完整行为由单元/集成、真实文件变更、并发与故障恢复测试覆盖，不能用帮助 smoke 替代。具体维护范围见 [工具维护说明](../../docs/toolchain-maintenance.md)。

维护仓库/开发分发另有 `scripts/benchmark_long_task.py --skill-root <待测能力包> --output <报告JSON>`：在独立临时订单工程上执行固定 12 个连续实际场景，包括原生 CLI/测试、当前必需质量门禁、递归上下文、跨模块变更、过期依据/收据拒绝、交接与精确恢复。详细报告保存逐步 argv、输入、实际输出、退出码和字节哈希；上下文计量是实际读取字节，不是 token。基准属于开发核验，不是运行包必需入口，也不代替既有单元、并发/中断恢复、质量探针或项目自身的真实验收；性能记录不设通用阈值。
