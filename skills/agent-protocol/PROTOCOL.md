# Agent Protocol

本技能负责“跑得广”，不能压住 `project-depth-core`。

仅在以下情况加载：

- 需要跨 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue 或自研 Agent 使用。
- 需要标准化模块提案、门禁结果、风险报告或验证报告。
- 需要虚拟模块智能体审议。
- 需要能力降级记录。
- 需要硬门禁结果。

## 边界

- 不负责功能簇展开。
- 不负责判断项目应该是什么。
- 不负责替代模块详情设计。
- 不引入中央协调智能体。

## 支撑能力

- 读取 `../../shared/references/universal-agent-protocol.md`。
- 读取 `../../shared/references/module-agent-protocol.md`。
- 读取 `../../shared/references/hard-gates.md`。
- 读取 `../../shared/references/agent-output-contract.md`。
- 读取 `../../shared/adapters/` 中的平台适配说明。

CLI 只做查验，不做认知判断。

## 交叉审计

平台支持多模型、多会话或独立审计 Agent 时，允许把审计作为协议层步骤，但不得引入中央协调智能体。

流程：

1. 实现方先完成架构变更、代码修改和基础验证。
2. 审计方独立读取同一份当前项目 `architecture/` 和变更后的代码。
3. 审计方对照硬门禁、模块详情、接口契约、实现清单和验证证据输出审计报告。
4. 实现方只根据审计报告中的可复现问题修正；修正后重新审计或记录未复审风险。

仅单模型可用时，可以模拟一次独立审计，但必须在验证证据中记录“同模型审计，独立性受限”。

## 详细参考路由

按触发信号读取，不要全量加载：

- 跨 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、自研 Agent 使用：`../../shared/references/universal-agent-protocol.md`
- 动态姿势语境、阶段切换、风险覆盖、退出条件：`../../shared/references/dynamic-posture-context.md`
- 虚拟模块智能体、模块边界、跨模块提案：`../../shared/references/module-agent-protocol.md`
- 硬约束门禁、状态跃迁、阻塞/确认/降级结果：`../../shared/references/hard-gates.md`
- 标准化模块提案、门禁结果、风险报告、验证报告：`../../shared/references/agent-output-contract.md`
- Codex、Claude Code、Trae、通用 CLI Agent 等平台差异：`../../shared/adapters/`
- 任务姿态建议器和轻量规则：`../../shared/assets/task-posture-rules.json`、`../../shared/scripts/detect_task_posture.py`
- 协议语义回归：`../../shared/scripts/validate_protocol_semantics.py`
