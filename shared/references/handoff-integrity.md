# 协作交接完整性

用于跨模块、换执行者、中断恢复或部分结果合并；单人短任务不强迫长交接。遵守 `module-agent-protocol.md` 的模块边界，不引入中央协调智能体。

## 交接必须保留

- 本次已确认需求、验收标准、非目标、原有授权与尚未解决的约束；准确保留模块、接口、任务及产物ID和路径。
- 当前阶段、已修改文件、只读依赖、可写范围、接口影响；已选择、实际加载和仍缺失的专业能力分别记录。
- 已完成、失败、部分完成、未运行和无法判断的结果；保留原始失败与修复依据，不用摘要把失败改成成功。
- 证据位置及其对应输入版本、待复核风险、下一步、停止条件和恢复点。不要凭摘要或旧收据认定当前代码通过。

## 接收与合并

接收者先核对约束、ID、作用域和当前文件，再继续执行。必要上下文装不下时，保存有路径的可追溯交接资料，先读取必需部分；不得静默截断关键约束。缺必要上下文时记录未验证并补齐，不能凭角色提示补造事实。

独立任务可以并行；合并前分别处理全部完成、部分完成和全部失败。冲突结论保留各自证据，明确裁决依据；任务完成数量不能代替共同接口或集成验收。重试前确认操作可重复或有补偿方案；截止时间、预算、外部条件及用户要求决定停止，不把超时当成批准。

交接输出沿用 `agent-output-contract.md`，具体结果回写到相应架构切片与恢复点。未解决约束即使某能力退出也必须继续保留；“退出当前专项”不等于项目完成。

## 来源

参考 [agency-agents Multi-Agent Systems Architect](https://github.com/msitarzewski/agency-agents/blob/main/engineering/engineering-multi-agent-systems-architect.md) 与 [Handoff Templates](https://github.com/msitarzewski/agency-agents/blob/main/strategy/coordination/handoff-templates.md) 的上下文、部分失败和交接思路，自行转述为模块边界规则。上游采用 [MIT License](https://github.com/msitarzewski/agency-agents/blob/main/LICENSE)；不采用默认中央编排器、固定代理数量或超时自动批准规则。
