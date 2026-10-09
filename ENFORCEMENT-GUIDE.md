# 任务架构检查机制

本指南说明工具如何支持完整性与完成判断。任务范围、启动回执和状态动作以 [LAYER](skills/task-architecture/LAYER.md) 为准；不再复制一套执行流程。工具检查结构、记录和可执行规则，不能独立判断项目设计是否适合或实现是否正确。

## F+B+C 的职责

| 机制 | 能证明什么 | 事实源与边界 |
|---|---|---|
| F：占位符 | 尚未填写的核心设计与示例残留可见 | schema 的重要性与字段规则；不能以填满代替真实设计 |
| B：阶段状态 | 记录哪些阶段已实际完成、哪些待办/阻塞 | `manage_state.py` 的 STANDARD_STAGES；进度记录不是代码观察 |
| C：完成裁判 | 占位符、必需阶段、已实现结构规则是否满足设计完成声明 | `judge_progress.py`；未来阶段待完成不阻止继续设计/实现 |

9个必需阶段为需求理解、功能树、模块树、模块详情、入口定义、数据拓扑、实现清单、测试责任、验证证据；接口契约为适用时完成的可选阶段。阶段枚举以脚本为准，不为使门禁通过提前写completed。

## 骨架与占位符

新项目先充分理解与比较方案，再用解析后的 `module_architecture.py init` 建真实根总架构，按职责添加模块。每个模块持有本地语义与待填设计，格式见 [SCHEMA](skills/architecture-json/SCHEMA.md) 和 [递归模块](shared/references/recursive-modules.md)。显式集中布局才使用 `init_architecture.py --mode init`；既有项目按实际入口继续读取。

占位符含义：

- `__待填__`：尚需真实设计的项；不能当完成。
- `__待选填__`：按适用性处理条目；schema必需键仍按合同保留。
- `__自动生成__`：由工具生成的元信息。
- `__示例*__`、`__注释__`、`__占位符说明__`：模板元数据；业务产物中不应残留假模块或示例key。

`check_placeholders.py` 结合schema分级检查value与示例key。核心缺口禁止声明相应设计完成；补设计、完成已明确模块和其他允许的工作仍可进行。不适用项写简短依据，不编造异常、配置或性能指标。

## 工具使用

以下变量表示已经由 [resolve_tool](skills/task-architecture/LAYER.md#工具与完成契约) 解析的脚本绝对路径；工作目录为调用方项目。`<架构入口>` 是实际根文件，工具按声明合成模块或既有切片。

```bash
python "<check_placeholders_path>" <架构入口>
python "<manage_state_path>" show --json
python "<validate_architecture_path>" <架构入口> --stage skeleton
python "<manage_state_path>" update <已实际完成阶段> completed --note "完成依据"
python "<judge_progress_path>" <架构入口> --json
```

同一相关批次执行适用检查一次。skeleton支持进行中的设计；full用于完整检查。完成裁判返回缺口时按具体原因继续补齐，不能把未来阶段pending当成禁止开始实现的理由。状态丢失时先核对权威架构与实际工作再恢复，不从记忆直接补“已完成”。

触发检测只在是否适用尚不明确时提供与语言/后缀无关的提醒；已有授权或受管入口不重复询问。纯只读与一次性实验按入口范围降级。

## 质量红线、独立审查与真实执行

F+B+C不覆盖全部语义。保留 [21项检查](shared/references/validation-checklist.md)、[通用质量](shared/references/universal-quality.md) 与按需专业审查：

- `check_quality_redlines.py` 的动作词与安全信号是启发式；命中需查真实路径，不为凑关键词扩权限体系。误报按当前证据记录语义复核。
- `audit_architecture.py generate/report` 提供固定问题的审查产物。逐题填真实结论与依据，保留不适用或失败；生成问卷只代表模板存在。
- 实际测试、构建、分析器或工程原生工具由 `run_verification.py` 绑定命令、选定输入和结果；GUI手检保留真实操作证据，不伪造CLI收据。
- 有适用理由时用 `run_quality_probes.py` 在隔离副本引入受控问题，检验检查器能否拒绝坏样例；复制范围和成本边界见通用质量协议。
- 同模型复核说明独立性受限，零发现允许有依据成立；不预设复查轮数。

模型review、实测execution、未采集与过期证据分别记录。依赖、复杂度/覆盖率、决策和接口规则使用工程实际事实，不限制业务语言。工具输出只说明选定范围与规则，不以总分或文件存在宣称全面正确。

完整实现交付配置本次必需规则与观察事实后运行：

```bash
python "<gate_check_path>" <项目根> --quality-required --json
```

缺必需规则、事实或当前证据为unknown；已知必需失败优先。完成首行依LAYER使用 `【任务完成】` 或 `【未通过验证】`，明确实际结果及边界。

## 返回码与自动化边界

| 工具 | 0 | 1 | 2 / 其他 |
|---|---|---|---|
| check_placeholders | 核心检查通过 | 核心缺失/占位符 | 输入或工具错误 |
| manage_state show | 状态已读取 | 状态缺失等已知错误 | 输入/IO错误；写操作版本或锁冲突为3 |
| judge_progress | 可声明设计完整 | 明确未完成 | 输入或检查无法判定 |
| detect_should_trigger | 建议触发 | 不建议触发 | 检测关闭或无法判定 |
| validate_architecture | 当前stage检查通过 | 明确结构/一致性错误 | 输入或工具错误 |
| check_quality_redlines | 无未解决适用错误 | 未解决错误 | 输入/工具/复核未知 |
| audit_architecture generate/report | 模板生成/审查结构通过 | 已知操作失败或不通过结论 | 参数或输入错误 |
| render_architecture | 派生视图生成 | 已知操作失败 | 参数/输出冲突/IO错误 |
| gate_check --quality-required | 本次必需规则通过 | 必需项明确失败 | 无已知失败但有必需未知 |

具体接口以工具help与结构化结果为准。参数格式错误通常为2；检测器0/1仅是提醒，不是项目质量结论。工具不可用记录原因及替代核对，不能宣称未运行门禁通过。

## 可视化与连续工作

根/模块架构或登记集中切片是事实源，`render_architecture.py` 的Mermaid、交互HTML和JSON是只读派生，保留全景到细节的完整阅读路径。查看或生成图纸不新建阶段，不反向写架构；真实变更走事实归属与批次校验。

证据详情唯一维护，变更记录与恢复点引用它；继续执行所需最小事实按 [上下文恢复](shared/references/context-recovery.md) 保存。查询、版本协调与交接等长程重复操作可按需用 [项目工具链](shared/references/project-toolchain.md)，不增加一套泛用流程。
