# 任务架构总入口

> 这是薄入口，不是能力全集。**加载本技能即进入强约束模式**：项目级任务必须按三层路由执行，禁止跳过任何一层。

## 何时触发

满足任一条件立即进入：

- 用户说「使用任务架构做 XXX」「用架构来」「按这个技能」「按架构来」「rwgj」。
- 用户输入五个命令之一：`/创建架构` `/分析架构` `/追加架构` `/修改架构` `/校验架构`。
- 当前项目根存在 `architecture.json` 或 `architecture/`（**自动接管，无需显式命令**）。
- 任务涉及：新项目从零、已有代码纳管、需求变更、功能扩展、架构重构、多模块系统设计、代码漂移排查、接口契约定义。

### 自动检测机制（防止遗漏）

当用户开始一个新任务但**未明确提及任务架构**时，Agent 必须先运行自动检测：

```bash
python shared/scripts/detect_should_trigger.py
```

> 若需关闭自动检测（常驻型工具中减少提醒摩擦），设置环境变量 `TASK_ARCH_AUTO_TRIGGER=off`，
> 此时脚本返回码 2，Agent 不得再主动提醒，但用户显式要求时仍须进入本流程。

若检测结果为"建议使用任务架构"，**必须主动提醒用户**：

```
🔍 检测到项目符合任务架构适用场景：
  • [检测到的特征列表]

建议使用任务架构技能来管理本项目。
是否使用任务架构？[是/否]

如果选择是，将自动进入架构先行模式。
```

**不触发**：一次性脚本、小 demo、临时实验、概念问答、运行单条命令。直接用编程智能体自身能力即可。

## 工具执行前置：先解析路径（强制）

本文件与子能力层中的 `shared/scripts/...`、`../../shared/scripts/...` 均为相对路径，**执行前必须先解析为实际存在的位置**：

1. 先检查当前项目根目录：`<项目根>/shared/scripts/<工具>.py` 是否存在。
2. 不存在时，使用本技能安装目录：`<技能安装目录>/shared/scripts/<工具>.py`。
3. 解析后用**绝对路径**执行（或先进入对应目录再执行），禁止把未解析的相对路径直接交给 shell。

两处都不存在（工具缺失）时，按文本规则降级执行，并在验证证据中记录「未运行原因」。

## 第一动作：主会话回执 → 读状态 → 判定 → 行动

加载后**第一段主会话输出必须可见**，禁止静默调用、禁止只在内部读文件不反馈。

### 0. 启动回执（必须输出到主会话）

```text
✅ 已启用任务架构技能
入口链路：SKILL.md → skills/task-architecture/LAYER.md
触发原因：[用户显式触发 / 项目存在 architecture.json 或 architecture/ / 自动检测建议]
本次初判：[创建 / 分析 / 追加 / 修改 / 校验 / 不进入完整流程]
受管状态：[未检查 / 未受管 / 已受管]
下一步：读取状态文件并给出任务判定
```

如果判断本次**不进入完整流程**，也必须输出：

```text
✅ 已检查任务架构技能
结论：本次不进入完整流程
原因：[一次性脚本 / 小 demo / 临时实验 / 概念问答 / 单条命令 / 用户明确不要]
后续：使用普通编程智能体能力处理
```

**无上述回执，不得声称已启用任务架构。**

加载后必须按以下顺序执行：

### 1. 强制读取进度状态（如果存在）

```bash
python shared/scripts/manage_state.py show --state-path architecture/_state.json
```

若状态文件存在，**必须先输出状态摘要**：
- 当前在哪个阶段
- 整体完成度
- 下一步行动是什么

若状态文件不存在且项目有 `architecture/` 目录，**必须先创建状态文件**：
```bash
python shared/scripts/manage_state.py init --project-name "项目名" --state-path architecture/_state.json
```

### 2. 任务判定

给出以下信息：

1. 任务判定：属于 创建/分析/追加/修改/校验 中的哪一种（用户未写命令时自动判定）。
2. 受管状态：当前项目根是否存在 `architecture.json` 或 `architecture/`。存在=受管项目，必须架构先行。
3. 本次读取哪些层（骨架/契约/清单/细节）。
4. 影响范围：会触碰哪些模块、文件、切片。
5. 最小闭环：本次至少要完成什么才算交付。

**未完成状态读取和任务判定前，不得创建文件、修改代码、扩展业务范围。**

### 3. 执行凭证（必须留痕）

进入完整流程后，主会话必须持续输出可核验凭证，至少包含：

- 已读取的能力层文件：`LAYER.md` / `CORE.md` / `SCHEMA.md` / `PROTOCOL.md`（按实际读取列出）
- 已运行或跳过的工具：命令、返回码、跳过原因
- 已创建或修改的架构文件/切片路径
- 当前阶段状态：来自 `manage_state.py show` 或 `show --json`
- 下一步行动：来自任务判定或 `judge_progress.py` 裁判结果

不得只说「已调用技能」或「已按任务架构处理」而不给出上述凭证。

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

## 修改后必跑三重校验

每次修改 `architecture/` 架构文件夹、总索引或切片后，**必须按顺序运行以下三重校验**：

### 1. 占位符检查（强制，不通过禁止继续）

```bash
python shared/scripts/check_placeholders.py architecture/index.json
```

检测所有 `__待填__` 占位符。有核心占位符时返回错误码，**必须修复后才能继续**。

### 2. 状态更新（每完成一个阶段）

```bash
# 标记当前阶段为进行中
python shared/scripts/manage_state.py update <阶段名> in_progress

# 完成后标记为已完成
python shared/scripts/manage_state.py update <阶段名> completed --note "完成说明"
```

阶段名包括（9 个必需 + 1 个可选）：需求理解 / 功能树 / 模块树 / 模块详情 / 入口定义 / 数据拓扑 / 实现清单 / 测试责任 / 验证证据（必需），接口契约（可选，跨模块调用业务才需要）

真相源：`shared/scripts/manage_state.py` 的 STANDARD_STAGES。

### 3. 架构一致性校验（21 项）

```bash
python shared/scripts/validate_architecture.py architecture/index.json
```

依赖完整性/路由页面对应/接口实现/数据迁移/认证/异常测试/依赖无环/交互完整性/代码漂移/变更可追踪/入口类型/验证证据/恢复点/功能树落位/模块详情/模块树/切片同步等。完整清单见 `../../shared/references/validation-checklist.md`，校验结果写入变更记录。

**三重校验顺序不可颠倒**：占位符未清空时运行其他校验无意义。

## 完成前自检（缺一不可）

运行以下命令完成自检：

```bash
# 1. 检查占位符（强制）
python shared/scripts/check_placeholders.py architecture/index.json

# 2. 检查进度状态（强制）
python shared/scripts/manage_state.py show

# 3. 检查架构一致性（强制）
python shared/scripts/validate_architecture.py architecture/index.json
```

自检清单：

- [ ] 🔴 无核心占位符：`check_placeholders.py` 返回 0，无 `__待填__`
- [ ] 🔴 所有必需阶段已完成：`manage_state.py show` 显示必需阶段完成度 100%
- [ ] 🔴 架构先行：先改 `architecture/index.json` 或切片再改代码
- [ ] 🔴 代码与架构文件夹一致：无漂移
- [ ] 🟡 验证证据已记录：命令/截图/手检/未验证项
- [ ] 🟡 上下文恢复点已更新：当前任务、继续位置、下一步、约束、风险
- [ ] 🟡 变更记录已追加：时间、操作类型、原因、影响范围、验证结果
- [ ] 🟡 剩余风险已说明

🔴 = 硬性要求，不满足禁止声明完成  
🟡 = 重要但非阻塞，不满足需说明原因

未满足完成定义时，只能汇报「已完成设计/实现，未完成验证」，并写入恢复点和变更记录。

## 详细参考路由（按需加载，不全量读取）

按触发信号读取对应参考，**默认不全量加载**（注意力保护）：

### project-depth-core 层

- 模糊需求、功能簇、反薄 Demo、展开停止规则、实现期循环展开：`../../shared/references/function-clusters.md`
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
