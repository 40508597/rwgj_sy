# 架构模式与模块边界

这是面向任务架构的中文改编指南，补充当前模块设计与审查，不替代主流程。
固定上游：[wshobson/agents architecture-patterns](https://github.com/wshobson/agents/tree/156b7a5e7a8b93642628a339ee4039c925b34c7f/plugins/backend-development/skills/architecture-patterns)。
许可：MIT；Copyright (c) 2024 Seth Hobson；原版权与许可全文保存在 [LICENSE](../upstream/wshobson-agents/LICENSE)。
原文：[SOURCE.md](../upstream/wshobson-agents/plugins/backend-development/skills/architecture-patterns/SOURCE.md)；版本固定，原文与参考文件保持原样。

## Given / Produces

Given：已确认任务、阶段、功能节点与模块范围，当前架构切片、代码事实、风险、技术约束和允许读写范围。
Produces：模块职责、依赖方向、边界契约、适配责任、必要的一致性约束、替代方案及测试边界。
输入不足时标明未知；先定位调用方架构，不凭示例替用户选择技术栈或部署形态。

## 何时按需读取

- 模块设计或重构涉及业务与数据库、UI、网络或外部系统耦合。
- 需要排查依赖循环、跨模块模型共享、替换外部实现或独立验证业务规则。
- 验证阶段需要审查已选架构的依赖约束；无此需求的纯视觉修改和小脚本不加载。
默认只读取本指南；需要核对术语、具体端口或聚合例子时，按预算将对应 SOURCE 或原目录参考登记后再读。
已确认上下文映射、防腐层或事件一致性问题时，再读 `references/advanced-patterns.md` 对应段落；不全量加载参考。

## 方法与取舍

1. 从实际职责、变化原因和测试困难识别边界，列出当前依赖及允许、禁止的依赖方向。
2. 对需隔离的外部变化设计端口和适配责任；组合入口负责注入实现，不让业务层反向依赖具体基础设施。
3. 有复杂领域规则时讨论实体、值对象、聚合不变量和上下文关系；按一致性需求衡量拆分与协调成本。
4. 比较现有结构、轻量分层、Clean或Hexagonal等方案的收益、迁移成本和额外抽象负担，再记录选择理由。
5. 明确领域、用例、适配器和集成各自的测试责任；内存替身验证规则，必要的真实集成验证边界行为。
不强制DDD、微服务、固定层数或Python目录；限界上下文不自动等于独立部署服务，框架约定按项目需求评估。
Related Skills中的microservices、CQRS、Saga和event-store仅为额外候选，不是本指南的必需依赖。
原例的Stripe Charge接口、Money字段和outbox用例含过时或不完整部分；只提取设计问题，不复制为当前事实或可运行保证。

## 架构回写与证据

职责及依赖写调用方 `/模块树`、`/模块详情`；端口写 `/接口契约`，不变量和失败路径写 `/完整细节`。
验证边界写 `/测试责任矩阵`，审查与运行结果写 `/验证证据`；以上JSON Pointer落在调用方根或所属模块 `architecture.json`（集中布局为 `architecture/index.json` 或登记切片）。
实际调用记录必须给出具体文件及Pointer；只允许本次范围内回写，先回写设计，再由主流程推进已授权实现。
`review`：记录实际输入、文件哈希、覆盖模块、设计取舍、结论、发现和未验证项；零发现可以记录，不证明运行通过。
`execution`：只有实际运行检查或测试才记录命令argv、返回码、输入版本和证据；分别保留completed、partial、failed、unknown。
规划、加载及证据记账沿用 [统一适配契约](../../references/programming-subskills.md#统一适配契约)，不以文件存在或读取原文宣称完成。
不执行原文安装命令，不擅自重排全仓或增加服务，不写全局技能目录状态，不创建中央协调智能体。
