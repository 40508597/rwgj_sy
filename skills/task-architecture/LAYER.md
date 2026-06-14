# 任务架构总入口

> 这是薄入口，不是能力全集。**加载本技能即进入强约束模式**：项目级任务必须按三层路由执行，禁止跳过任何一层。

## 何时触发

满足任一条件立即进入：

- 用户说「使用任务架构做 XXX」「用架构来」「按这个技能」「按架构来」「rwgj」。
- 用户输入五个命令之一：`/创建架构` `/分析架构` `/追加架构` `/修改架构` `/校验架构`。
- 当前项目根存在 `architecture.json` 或 `architecture/`（**自动接管，无需显式命令**）。
- 任务涉及：新项目从零、已有代码纳管、需求变更、功能扩展、架构重构、多模块系统设计、代码漂移排查、接口契约定义。

**不触发**：一次性脚本、小 demo、临时实验、概念问答、运行单条命令。直接用编程智能体自身能力即可。

## 第一动作：先判定，再行动

加载后**第一段输出必须**给出：

1. 任务判定：属于 创建/分析/追加/修改/校验 中的哪一种（用户未写命令时自动判定）。
2. 受管状态：当前项目根是否存在 `architecture.json` 或 `architecture/`。存在=受管项目，必须架构先行。
3. 本次读取哪些层（骨架/契约/清单/细节）。
4. 影响范围：会触碰哪些模块、文件、切片。
5. 最小闭环：本次至少要完成什么才算交付。

**未完成判定前，不得创建文件、修改代码、扩展业务范围。**

## 三层路由（固定执行顺序，不得跳过）

```text
用户需求
  ↓
1. skills/project-depth-core/CORE.md     ← 想得深：功能簇展开、反薄Demo、智能关联
  ↓
2. skills/architecture-json/SCHEMA.md    ← 落得稳：写入 architecture/ 切片、模块详情、实现清单
  ↓
3. skills/agent-protocol/PROTOCOL.md     ← 仅按需：跨平台适配、硬门禁、标准输出、能力降级
```

- **project-depth-core**：任何需求先进入，除非只是概念问答或单条命令。
- **architecture-json**：需要创建/修改/校验 `architecture/` 架构文件夹、`architecture/index.json` 或切片时进入。
- **agent-protocol**：仅在需要跨平台适配、标准化输出、硬门禁、能力降级、虚拟模块审议时进入。

不得从本入口直接写代码、直接展开业务细节、直接判断完成。

## 三条铁律（永远有效）

1. **架构先行** — 受管项目改代码/UI/接口/字段/测试前，必须先改 `architecture/index.json` 或相关切片。用户没输入 `/修改架构` 不是绕过的理由。
2. **架构是法官** — 代码与架构文件夹不一致时，先判断架构是否过期，再修正架构或代码，不得凭直觉覆盖。
3. **禁止代码漂移** — 代码不得有 architecture/ 架构文件夹未定义的东西。

## 五个命令（用户侧接口）

| 命令 | 何时用 | 自动判定场景 |
|------|--------|------|
| `/创建架构` | 新项目从零 | 用户描述需求，项目无 architecture |
| `/分析架构` | 已有代码纳管 | 用户给已有项目目录 |
| `/追加架构` | 加新功能/新模块 | 架构文件夹中不存在的模块 |
| `/修改架构` | 改已有模块 | 修 Bug、改字段、优化、删 UI |
| `/校验架构` | 检查一致性 | 找漂移、评估现状 |

用户只说「使用任务架构做 XXX」但没写命令时，必须自动判定并选择其一，**不得跳过架构文件夹**。

## 修改后必跑校验

每次修改 `architecture/` 架构文件夹、总索引或切片后，必须立即跑 21 项一致性校验（依赖完整性/路由页面对应/接口实现/数据迁移/认证/异常测试/依赖无环/交互完整性/代码漂移/变更可追踪/入口类型/验证证据/恢复点/功能树落位/模块详情/模块树/切片同步等）。完整清单见 `../../shared/references/validation-checklist.md`，校验结果写入变更记录。

## 完成前自检（缺一不可）

- [ ] 架构先行：先改 `architecture/index.json` 或切片再改代码
- [ ] 代码与架构文件夹一致：无漂移
- [ ] 验证证据已记录：命令/截图/手检/未验证项
- [ ] 上下文恢复点已更新：当前任务、继续位置、下一步、约束、风险
- [ ] 变更记录已追加：时间、操作类型、原因、影响范围、验证结果
- [ ] 剩余风险已说明

未满足完成定义时，只能汇报「已完成设计/实现，未完成验证」，并写入恢复点和变更记录。

## 详细参考路由（按需加载，不全量读取）

按触发信号读取对应参考，**默认不全量加载**（注意力保护）：

### project-depth-core 层

- 模糊需求、功能簇、反薄 Demo、展开停止规则：`../../shared/references/function-clusters.md`
- 组件、接口、API、CLI、后台任务、交付物、交互闭环：`../../shared/references/interaction-completeness.md`
- 多层递进、逐块深度设计、状态流转：`../../shared/references/progressive-decomposition.md`
- 功能/模块/文件拆分粒度和停止规则：`../../shared/references/splitting-guide.md`
- 影响范围、智能关联、优先级冲突：`../../shared/references/association-and-priority.md`
- UI/测试/安全/性能/部署/文档等专业能力路由：`../../shared/references/capability-index.md`
- 受控主动性、注意力保护、日常速查：`../../shared/references/principles-card.md`

### architecture-json 层

- JSON 字段、中文化规范、四层读取策略、schema 底线：`../../shared/references/schemas.md`
- 五个命令、创建/分析/修改/追加/校验工作流：`../../shared/references/commands-workflows.md`
- 21 项一致性校验、禁止事项、完成前自检：`../../shared/references/validation-checklist.md`
- 强制切片目录、架构文件夹、多人/多会话协作：`../../shared/references/json-sharding.md`
- 上下文压缩、中断续跑、恢复点：`../../shared/references/context-recovery.md`
- 任务前置输出、架构变更对比、失败恢复：`../../shared/references/execution-templates.md`

### agent-protocol 层（仅按需）

- 跨 Codex/Claude Code/Trae/Cursor/Windsurf/Cline/自研 Agent：`../../shared/references/universal-agent-protocol.md`
- 动态姿势语境、阶段切换、风险覆盖：`../../shared/references/dynamic-posture-context.md`
- 虚拟模块智能体、模块边界、跨模块提案：`../../shared/references/module-agent-protocol.md`
- 硬约束门禁、状态跃迁、阻塞/确认/降级：`../../shared/references/hard-gates.md`
- 标准化模块提案、门禁结果、风险/验证报告：`../../shared/references/agent-output-contract.md`

## 定位规则（多项目共用）

1. 先检测当前工作项目是否存在 `architecture.json`。
2. 若存在，项目真相源只读取当前项目的 `architecture.json -> architecture/index.json`。
3. 能力文件优先从当前项目根目录的 `skills/`、`shared/` 读取。
4. 当前项目没有能力文件时，从本技能安装目录读取 `skills/`、`shared/`。
5. **不得把项目状态、恢复点、变更记录或架构切片写入全局技能目录**。

子技能中的 `../../shared/` 路径按同一规则解析：先看当前项目根目录是否有 `shared/`，没有则回到本技能安装目录的 `shared/`。

## 辅助参考（给人看）

- 命令速查：`../../shared/references/commands-cheatsheet.md`
- 快速上手：`../../shared/references/quickstart.md`
