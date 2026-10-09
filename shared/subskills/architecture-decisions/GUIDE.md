# 架构决策与取舍记录

这是面向任务架构的中文改编指南，为重大决策保存理由、后果与替代关系。
固定上游：[wshobson/agents architecture-decision-records](https://github.com/wshobson/agents/tree/156b7a5e7a8b93642628a339ee4039c925b34c7f/plugins/documentation-generation/skills/architecture-decision-records)。
许可：MIT；Copyright (c) 2024 Seth Hobson；原版权与许可全文保存在 [LICENSE](../upstream/wshobson-agents/LICENSE)。
原文：[SOURCE.md](../upstream/wshobson-agents/plugins/documentation-generation/skills/architecture-decision-records/SOURCE.md)；版本固定，原文保持原样。

## Given / Produces

Given：待裁决的问题、阶段、影响模块、当前架构与既有决策、可核对约束、备选方案和允许读写范围。
Produces：决策ID与状态、背景、驱动因素、已考虑方案、选择理由、正负后果、风险、执行及验证条件。
无法确认的选型能力、性能、成本或版本标为未知，不用示例数据补成项目事实。

## 何时按需读取

- 设计或变更涉及重大选型、难撤销的选择、跨模块取舍、数据迁移或长期运维成本。
- 历史决策复核需要区分当时背景、当前生效选择、已废弃方案及替代关系。
- 普通小修复和无重要取舍的文案或样式修改不强制写ADR。
默认只读本指南；需要完整模板时按预算登记并读取对应SOURCE中的轻量ADR、标准ADR或替代决策段落。
数据库、电商、网关和事件溯源案例只说明组织方式；不把全部案例或关联工具默认载入上下文。

## 方法与取舍

1. 明确问题、影响模块、必须满足与可权衡的约束，给关键事实标注来源和适用版本。
2. 列出合理备选，比较收益、代价、风险、可逆性、安全影响和维护成本；保留不采用方案的理由。
3. 记录当前选择及生效范围，区分proposed、accepted、rejected、deprecated与superseded，不把提案当已执行决策。
4. 将后果转成适用的执行项、迁移与回退条件、验收证据；未解决问题保留负责人或后续裁决位置。
5. 替换已生效决策时保留历史背景，以新记录链接旧记录，核对哪些模块和约束实际被替代。
文档厚度与决策影响相称；现有切片中的简短理由也可满足小范围取舍，不强制独立ADR文件或固定审批人数。
不强制框架、数据库、事件溯源或特定栈；PostgreSQL15、示例工期与负载不能成为当前项目默认值。
原案例MongoDB当时无多文档ACID、MySQL无全文或空间能力不作当前事实；选型应核对实际产品版本与限制。
原文的brew、adr-tools、PR和通知步骤仅为示例，不自动安装工具、发送消息或增加审批流程。

## 架构回写与证据

决策及影响模块写拥有该职责的架构文件 `/模块详情`、`/完整细节`；执行与迁移项写 `/实现清单`。根级变更与验证记录分别使用根文件 `/变更记录`、`/验证证据`；模块局部记录按 [字段归属](../../references/recursive-modules.md#根级字段与模块局部记录)，不使用这些根保留键作为子文件顶层字段。
比较依据、风险及验证结论留在权威决策位置并引用真实证据。递归布局中，全局决策归调用方根 `architecture.json`，局部决策归拥有该职责的模块 `architecture.json`；跨模块决策确定唯一权威位置，其他模块引用。既有集中布局仍落在 `architecture/index.json` 或登记切片。
独立决策文档如确有需要，保存在调用方相应模块目录或 `architecture/` 内，由权威架构引用；已有docs/adr作为历史输入或派生文档。
实际调用记录给出具体文件及Pointer，核对当前生效选择与实现约束一致，不建立第二套架构真相。
`review`：记录输入和文件哈希、备选覆盖、取舍依据、结论、未解决问题及未验证项；审查不证明基准或迁移已运行。
`execution`：实际运行基准、迁移检查或验证时记录命令argv、返回码、输入版本和原始证据，保留失败或unknown。
规划、加载及证据记账沿用 [统一适配契约](../../references/programming-subskills.md#统一适配契约)，不以ADR存在宣称架构或实现完成。
不扩大业务范围，不写全局技能目录状态，不创建中央协调智能体，实施与完成裁决仍由任务架构主流程处理。
