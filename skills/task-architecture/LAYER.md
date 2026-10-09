# 任务架构总入口

本层负责范围、路由和完成契约。深度设计、物理事实、协作协议分别由后续能力层负责；资料按需读取。技能适用于任意编程智能体，不限制项目语言、文件后缀、框架或 IDE。Python 是随包工具运行时。

## 启用与降级

满足下列任一条件时判定本次范围：

- 用户要求“使用任务架构”“按架构来”“rwgj”，或输入 `/创建架构`、`/分析架构`、`/追加架构`、`/修改架构`、`/校验架构`。
- 项目存在 `architecture.json` 或 `architecture/`，或任务涉及新项目、纳管、功能变更、架构重构和一致性检查。

用户已明确使用或已发现受管入口时直接处理。同一任务仅在适用性尚不明确时运行一次 `detect_should_trigger.py`；`TASK_ARCH_AUTO_TRIGGER=off` 时不主动提醒，显式要求仍有效。检测建议不扩大授权；未受管项目若引入完整管理会显著扩大任务范围，说明依据并确认一次。已有授权不重复询问。

三档由 [小命令降级](../../shared/references/small-command-degradation.md) 和 `small-command-rules.json` 统一定义：

| 档位 | 范围与动作 |
|---|---|
| 完全跳过 | 概念问答、纯只读、一次性脚本、小 demo、临时实验；说明后直接处理，不读写阶段状态 |
| 最小闭环 | 受管项目的启动/运行或局部小修改；功能簇最小定位。运行类记录真实执行，修改类架构先行并做适用校验 |
| 完整流程 | 新项目、纳管、新功能、重构、漂移治理等；进入深度设计与物化层 |

非受管项目无锚点时最小闭环降为完全跳过。复合请求逐项判定，实际高风险操作不能被问答、否定句或文案引用掩盖；纯只读不因已有锚点升级。拿不准的实际操作按完整流程处理。

## 第一动作与可见回执

同一任务输出一次简短启动回执，允许与正常进度说明合并：

```text
✅ 已启用任务架构技能
入口链路：SKILL.md → skills/task-architecture/LAYER.md
触发原因：用户要求或项目入口
任务判定：类型、主要模块/文件、执行档位
下一步：本次定位、设计、修改或验证动作
```

完全跳过时说明已检查、本次不进入完整流程及原因即可。无可见回执不得声称已启用或降级；范围未变不重复贴模板。工具原始结果与常规日志保存在证据中，不反复粘贴。

内部判定七项：五命令类型、受管入口、所需信息层、影响范围、最低交付条件、任务姿态、小命令档位。主会话只说明类型、范围、档位和下一步；需求、范围或风险改变时更新相关判断，不逐项打印未变化内容。

工具可用时运行 `detect_task_posture.py` 与 `detect_small_command.py` 取得建议，核对实际意图并合并说明判定依据与降级要求。`dynamic/linear/reactive` 是执行节奏：动态裁决、批量推进、定向修复；与检测器的执行角色/场景/专业领域三轴分开，见 [任务姿态](../../shared/references/task-posture.md)。三档决定流程范围，工具建议不替代用户约束或工程判断。

完整流程和最小闭环先读取已有状态，只显示本次相关阶段、阻塞项和下一步：

```bash
python "<manage_state_path>" show --state-path architecture/_state.json
```

修改类缺少状态时初始化；纯运行不为流程记录创建状态，记录状态缺失与实际执行证据。完成范围判定和适用状态读取前，不创建业务文件、修改代码或扩展需求。后续能力层复用这次判断，不重复初始化。

## 设计与物化路由

```text
用户需求
→ skills/project-depth-core/CORE.md      # 完整流程的需求全景、功能簇与深度设计
→ skills/architecture-json/SCHEMA.md    # 模块事实、契约、源码归属与验证
→ skills/agent-protocol/PROTOCOL.md     # 按需：跨执行者、标准提案、虚拟模块智能体与能力降级
```

完整流程的最低交付条件、实施批次和资料预算不限制功能发现。按 CORE 充分呈现核心、天然绑定、适用商业标配、强相关衍生与关联功能，由用户取舍；用户已限定的局部任务按三档范围处理。不得从本入口跳过必要设计直接编码或宣布完成。

三条铁律：

1. **架构先行**：受管项目改代码、UI、接口、数据、测试或文件前，定位并更新拥有本次事实的架构。已覆盖的局部实现补本次变更、测试与影响记录，不机械重写未变化设计；写入位置与准确键名遵循 [根级与局部记录归属](../../shared/references/recursive-modules.md#根级字段与模块局部记录)。
2. **架构是法官**：代码与架构不一致时先判断哪个已过期，再依据真实需求修正。
3. **禁止代码漂移**：职责、契约、源码归属和关键行为可追踪到项目架构，并与实际实现核对。字段齐全不等于实现正确。

新项目从充分需求与方案比较进入真实模块目录。根 `architecture.json` 保存全局目标、约束、共同契约、总体路由和根自身事实；模块可按职责任意有限深度递归，每层可有源码与测试，不按层数或文件数硬拆。局部完整语义归所属模块，上层只保留必要导航摘要。修改从根沿相关分支进入，取得本模块细节、依赖契约、消费者、源码与测试；跨模块任务明确主要/协作责任。格式与工具合同以 [递归模块架构](../../shared/references/recursive-modules.md) 为准。

既有集中布局跟随真实 `指向` 与切片登记，不为形式迁移源码。入口失效先报告未验证并修复；全局技能目录只存规则和工具，项目状态、证据和恢复点留在项目中。具体文件定位与逐项回退沿用 [SKILL 定位规则](../../SKILL.md#定位规则)。

## 工具与完成契约

执行前从已加载的 SKILL.md 所在目录解析每个工具绝对路径，工作目录保持调用方项目：

```bash
python "<技能安装目录>/shared/scripts/resolve_tool.py" <工具名> --json
```

返回的 `path` 是脚本文件。项目级对应文件优先，缺失逐项回退安装目录；工具缺失按相应规范降级，记录未运行原因。长程项目需要查询、结构化变更、版本协调、交接或恢复时，按需使用 [项目工具链](../../shared/references/project-toolchain.md)；单次简单操作不套用完整工具链。

每个相关变更批次完成后三重校验一次；设计进行中检查适用结构底线，不要求最终门禁先通过才能补设计或实现：

```bash
python "<check_placeholders_path>" <当前架构入口>
python "<validate_architecture_path>" <当前架构入口> --stage skeleton
python "<manage_state_path>" update <已实际完成的阶段> completed --note "完成说明"
```

9 个必需阶段与可选接口契约以 `manage_state.py` 的 STANDARD_STAGES 为准。按 [21 项检查与硬约束门禁](../../shared/references/validation-checklist.md) 核对本次适用规则；结构工具不能代替接口语义、异常覆盖与真实行为验证。结果、未验证项和必要的继续位置写入权威记录，其他位置引用，见 [上下文恢复](../../shared/references/context-recovery.md) 和 [执行记录](../../shared/references/execution-templates.md)。

完整实现交付配置本次必需质量规则与观察事实，并运行：

```bash
python "<gate_check_path>" <项目根> --quality-required --json
```

0=选定自动检查通过，1=明确失败，2=证据缺失、损坏或无法判定；不能把非零或声明/推断当实测通过。已启用专业能力计划时核对实际使用、产物和架构回写，规划或加载不代表已完成。质量与真实执行协议见 [通用质量](../../shared/references/universal-quality.md)，能力协议见 [能力索引](../../shared/references/capability-index.md)。

完整交付结论首行保持机器契约：通过用 **`【任务完成】`** 加结果；未通过用 **`【未通过验证】`** 加失败与下一步，仅表述已完成设计/实现及未通过验证的边界。启动、查看等局部任务只报告本次结果，不宣告项目整体完成。失败不妨碍继续修复。

## 按需参考

| 需要解决的问题 | 规范 |
|---|---|
| 功能全景、展开与停止、交互完整性 | [function-clusters](../../shared/references/function-clusters.md)、[interaction-completeness](../../shared/references/interaction-completeness.md) |
| 递进设计、拆分粒度、影响与优先级 | [progressive-decomposition](../../shared/references/progressive-decomposition.md)、[splitting-guide](../../shared/references/splitting-guide.md)、[association-and-priority](../../shared/references/association-and-priority.md) |
| JSON 信息层与命令工作流 | [schemas](../../shared/references/schemas.md)、[commands-workflows](../../shared/references/commands-workflows.md) |
| 递归模块与既有集中布局 | [recursive-modules](../../shared/references/recursive-modules.md)、[json-sharding](../../shared/references/json-sharding.md) |
| 跨宿主、协作与标准输出 | [universal-agent-protocol](../../shared/references/universal-agent-protocol.md)、[module-agent-protocol](../../shared/references/module-agent-protocol.md)、[agent-output-contract](../../shared/references/agent-output-contract.md) |
| 专业方法、代码审查、交接与转换 | [capability-index](../../shared/references/capability-index.md)，再按信号读取 semantic-code-review、handoff-integrity、artifact-integrity |
| 完整图纸与交互画布 | [architecture-visualization](../../shared/references/architecture-visualization.md)；只读派生不创建或推进阶段 |
| 人用速查 | [principles-card](../../shared/references/principles-card.md)、[commands-cheatsheet](../../shared/references/commands-cheatsheet.md)、[quickstart](../../shared/references/quickstart.md) |

默认不全量读取参考、模块和第4层；相关功能、异常/生命周期、专业方法和必要验证仍需完整覆盖。
