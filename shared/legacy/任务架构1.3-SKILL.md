---
name: 任务架构
description: >
  用结构化 JSON 架构文件管理 AI 编程项目的完整生命周期。
  触发词：任务架构、架构JSON、模块化管理、按架构编写、结构化编程。
  面向 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、自研 CLI Agent 等任意编程智能体，以及中大型商业项目、长期维护项目、全栈工程项目、多模块系统和 AI 难以稳定维护的复杂代码库，覆盖前端、后端、接口、数据、任务、CLI、桌面端、移动端、EXE/安装包/Docker/SDK/插件等可交付形态、测试、部署和文档；不用于一次性脚本、小 demo、临时小修。若当前项目已存在 architecture.json，任何涉及代码、UI、接口、数据、测试、文件或行为修改的请求，即使用户未显式输入命令，也应自动按本技能执行；除非用户明确要求不要使用任务架构或直接快速修改。
  五个命令：/分析架构、/创建架构、/修改架构、/追加架构、/校验架构。
  六大机制：最大主动性设计、功能簇/功能树展开、专业能力索引、交互完整性、多层递进设计、分治设计法。
---
# 任务架构 — AI 编程项目架构管理

## 定位与适用边界

本技能是面向 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、自研 CLI Agent 等任意编程智能体的全栈工程化行为协议，不是完整智能体，也不是外部多智能体运行平台。目标是让智能体在中大型商业项目中更工程化、稳定、可追踪，减少黑盒式自由发挥和用户反复补充细节的成本。

**适用：**
- 中大型商业项目、长期维护项目、全栈工程项目、多模块系统、复杂功能簇
- 覆盖前端、后端、API、数据库、后台任务、CLI、桌面/移动端、EXE/安装包/Docker/SDK/插件等可交付形态、部署、测试、文档等工程面
- 有真实用户、真实数据、权限、安全、部署、测试或商业交付风险的项目
- 已经出现 AI 维护困难、模块漂移、接口/文档/测试不同步的代码库
- 后续需要多轮追加功能、修改需求、修复 Bug 的项目
- 当前项目根目录或工作目录中已存在 `architecture.json`，且用户请求涉及代码、UI、接口、数据、测试、文件或行为修改

**不适用：**
- 一次性脚本、小 demo、临时实验、小型原型
- 用户明确只要快速验证想法，且没有长期维护预期的任务
- 只解释代码、回答概念问题、运行一个简单命令的即时任务
- 用户明确说“不要用任务架构”“直接快速改”“本次不更新 JSON”

进入适用场景后，保持稳定流程。只要项目已经被 `architecture.json` 管理，涉及代码、UI、接口、数据、测试、文件或行为的修改都必须先更新 JSON，再改代码。

## 最高原则

`architecture.json` 是项目唯一真相源：任何需求变更、功能新增、Bug 修复、重构，都先更新 JSON，再改代码。项目目标、验收标准、非目标和用户明确不要，都必须物化为 `architecture.json` 内部结构，不能作为 JSON 之上的独立裁决层。代码追随 JSON，JSON 不追随代码。

三条铁律：
1. **JSON 先行**：先改 JSON，再改代码。
2. **JSON 是法官**：代码与 JSON 不一致时，先做偏差分类；确认 JSON 代表设计真相后修正代码。
3. **禁止代码漂移**：代码中不得出现 JSON 未定义的模块、文件、接口、入口、数据结构。需要超出范围时，先更新 JSON。

通用编程智能体协议补充铁律：
1. **目标内化**：智能体建议、功能族展开、模块提案和适配层都必须追溯到 `architecture.json` 中的功能树、模块详情、验收标准或非目标。
2. **平台无关**：核心协议不得绑定单一智能体平台；平台差异写入 `adapters/`。
3. **能力降级留痕**：智能体无法运行脚本、无法截图、无法使用子智能体或无法编辑文件时，必须记录降级原因和替代验证。
4. **虚拟多智能体可用**：平台不支持真实多智能体时，必须用标准化输出模拟模块视角审议和门禁结果；不引入中央协调智能体。

受管项目自动接管规则：
- 发现工作目录存在 `architecture.json` 时，默认当前项目已进入本技能管理。
- 用户要求改代码、改 UI、修 Bug、加字段、改接口、删页面元素、改测试、调整配置、改文件结构时，即使没有输入 `/修改架构`，也默认按 `/修改架构` 或 `/追加架构` 执行。
- 用户只说“使用任务架构”“按这个技能”“按架构来”“按照 architecture.json”，但没有写具体命令时，必须根据任务内容自动选择 `/分析架构`、`/创建架构`、`/修改架构`、`/追加架构` 或 `/校验架构`，不得因为命令缺失而绕过 JSON。
- 若用户明确要求跳过 JSON，必须在回复中说明这会产生代码漂移风险，并在最终汇报中记录“本次未更新 architecture.json”。

## JSON 中文化规范

architecture.json 是给用户、后续智能体和开发者共同阅读的工程真相源，字段名和说明必须优先使用中文。

**必须中文：** JSON 对象键名、说明性字段、状态值、分类值、测试描述、交互说明、异常说明、变更记录正文。

**保留原样：** 真实代码标识符、函数名、类名、变量名、模块名、包名、文件路径、路由路径、HTTP 方法、数据库表名和字段名、技术栈名、第三方库名、协议名、命令行参数。

**禁止：** 新建 architecture.json 时使用 `project`、`modules`、`contracts`、`changeLog` 等英文主键名；禁止为了中文化而改写真实代码契约。

## 执行契约

调用本技能后，智能体必须把每次任务纳入最小闭环：需求落位到 architecture.json → 动态姿势语境 → 功能族展开 → 模块/影响范围提案 → JSON 变更 → 代码变更 → 验证证据 → 恢复点 → 变更记录 → 剩余风险。

执行顺序：判定任务 → 锁定用户本次需求并落位到 `architecture.json` → 建立动态姿势语境 → 按需展开功能族和模块智能体提案 → 按需读取 JSON/切片 → 先更新 JSON → 再改代码 → 验证 → 更新恢复点和变更记录 → 汇报剩余风险。

实现期允许循环展开功能族，但不得边写边脑补。编码、测试或模块审议过程中发现缺少状态、异常、权限、数据、接口、交互反馈、验证责任或跨模块契约时，必须暂停当前代码修改，回到 `architecture.json` 展开相关功能族/功能树/模块详情/实现清单，分类为必须补、建议补、待确认或明确排除；只有已落位且属于本轮必须补的内容，才能继续实现。

冲突时按以下优先级裁决：用户明确不要 > 安全/数据/不可逆风险 > architecture.json 真相源 > JSON 先行 > 本次需求锁定 > 功能簇主动性 > 执行速度。

命令自动选择：
- 新项目从零开始：`/创建架构`
- 已有代码迁入且无 architecture.json：`/分析架构`
- 已有 architecture.json 且修改已存在模块/文件/接口/数据/行为：`/修改架构`
- 已有 architecture.json 且新增未登记功能、模块、入口或交付物：`/追加架构`
- 怀疑 JSON 与代码不一致、长期未维护或需要审计：`/校验架构`

动态姿势语境：开始任务时，先根据用户需求、项目目标、是否存在 `architecture.json`、影响范围、模块关系和风险信号，建立当前语境。语境不是角色身份，也不是外部调度结果，而是阶段、风险、作用域、模块关系、触发事件、退出条件和追加硬约束的组合。涉及模糊需求、新功能、UI、数据、安全、上下文恢复、测试失败或发布交付时，读取 `references/dynamic-posture-context.md`；旧的 `references/task-posture.md` 保留为轻量建议器说明。可运行脚本时，可用 `scripts/detect_task_posture.py --request "用户需求"` 输出初始建议，但必须按动态姿势语境人工修正。

虚拟模块智能体：平台不支持真实多智能体时，智能体必须按 `references/module-agent-protocol.md` 用结构化输出模拟模块智能体。模块智能体按模块边界、功能族展开、接口契约、验证责任工作，不按职业角色表演。

## 受控主动性原则

用户描述的是“想要什么”，智能体的职责是思考“它在真实软件中应该是什么”。不要把用户的自然语言需求机械缩小成一个按钮、一个页面或一个函数；必须主动推导该需求天然包含的核心功能、衍生状态、交互闭环、工程标配和验证责任。

主动性必须受控：
- **默认纳入**：功能成立所必需的核心链路、天然绑定能力，以及安全、错误处理、日志、配置、测试、迁移、健康检查等商业级基础设施。
- **默认列出让用户砍**：与功能强相关但可能影响范围的衍生能力，如批量操作、导入导出、统计、审计、通知、后台管理。
- **先列出并询问**：付费、法律、金融风控、高成本外部服务、重平台能力、不可逆数据操作、明显超出本次目标的产品扩张。
- **明确排除**：用户说不要的内容、本次不相关的全局优化、一次性脚本和临时 demo 的重流程。

主动补全不是自行扩大范围。每个主动推导出的能力都必须分类、说明理由，并落到功能树、模块、入口、接口、数据、文件、测试或待确认项；无法落位的能力只作为建议，不进入实现。

## 防扁平化铁律

不得从用户需求直接跳到文件、函数或代码片段。任何新增、修改、修复或优化，都必须先经过：

```text
用户需求 → 功能簇 → 功能树 → 模块树 → 模块详情 → 实现清单 → 代码/测试
```

代码文件不得孤立存在。每个新增或修改的文件，都必须能追溯到至少一个功能树节点、一个模块树/模块详情节点、一个实现清单条目和一个验证责任。若模型只能说明“要改哪个文件”，却不能说明该文件属于哪个功能、哪个模块、承担什么边界和如何验证，说明设计仍然扁平，必须先补架构再编码。

## 注意力保护原则

本技能的目标是让用户每次需求精准落地，不是让流程占满模型注意力。任何时候都必须优先锁定“本次用户真正要改什么”，再按最小必要范围读取架构。

铁律：
- **用户本次需求优先**：先提取用户明确要求、隐含细节、不要做的事、验收信号，再主动推导“应有能力”并分类裁决。
- **默认不全量读取**：不为“了解全貌”读取所有 references、所有切片或所有第4层细节。
- **默认不全量展开**：只展开与本次需求相关的功能簇、功能树、模块树和模块详情；但相关功能不得浅展开成薄 demo。
- **细节必须落位**：用户提到的每个具体页面、按钮、字段、接口、文案、状态、异常或约束，都必须落到 JSON 的对应节点、代码文件和验证项。
- **流程不能盖过结果**：如果流程步骤开始挤压对用户需求细节的处理，立即收缩读取范围，只保留能支撑本次落地的规则。

第一段输出必须先给出任务判断、自动选择的命令、是否存在 architecture.json、需要读取的 JSON 层级、影响范围和用户本次需求锁定。详细模板见 `references/execution-templates.md`。没有完成判定和 JSON 读取/更新计划前，不要创建文件、修改代码或扩展业务范围。

## 核心机制

1. **最大主动性设计**：用户描述的是想要什么，智能体必须思考真实软件应该是什么；商业级标配如日志、错误处理、健康检查、迁移、测试、安全边界按需纳入。
2. **功能簇/功能树展开**：把模糊需求展开为可验收、可落位、可测试的功能树节点。
3. **专业能力索引**：UI、测试、安全、性能、部署、文档等专业能力只做路由和回写约束，不接管主流程。
4. **交互完整性**：每个操作覆盖请求、反馈、异常、恢复闭环。
5. **多层递进设计**：全景分析 → 拆块骨架 → 逐块深度设计 → 集成验证。
6. **分治设计法**：大功能拆小块，每块按模块、入口、接口、数据、实现、测试完整落位。

实现期循环展开属于功能簇/功能树展开机制：初始架构可以先形成可信骨架，逐块实现时再围绕当前模块和当前功能节点做局部展开；每次循环都必须回写 JSON、验证影响范围，并在当前叶子节点闭合后退出。

## 何时读取参考文件

按触发信号读取，不要为了“了解全貌”加载全部 references：

| 触发信号 | 读取 |
|---|---|
| 任意编程智能体、跨平台适配、能力降级、虚拟多智能体 | `references/universal-agent-protocol.md` |
| 动态姿势语境、阶段切换、风险覆盖、语境退出条件 | `references/dynamic-posture-context.md` |
| 模块智能体、模块边界、跨模块提案、功能族在模块内使用 | `references/module-agent-protocol.md` |
| 硬约束门禁、状态跃迁、阻塞/确认/降级结果 | `references/hard-gates.md` |
| 标准化智能体输出、模块提案、门禁结果、验证报告 | `references/agent-output-contract.md` |
| 任务姿态、角色边界、动态任务分类、执行状态校准 | `references/task-posture.md` |
| 模糊需求、功能簇、功能树、实现期循环展开、反薄 Demo | `references/function-clusters.md` |
| 专业能力、技能列表、UI/测试/安全/部署等能力路由 | `references/capability-index.md` |
| 组件、接口、API、CLI、后台任务、桌面/移动端、交付物、系统集成、交互闭环 | `references/interaction-completeness.md` |
| 四层 JSON、逐块设计、模块树、模块详情、拆分粒度 | `references/progressive-decomposition.md`、`references/splitting-guide.md` |
| 五个命令流程、漂移修复、中断恢复、自动分块执行 | `references/commands-workflows.md` |
| 任务前置输出、JSON 对比、完成定义、失败恢复 | `references/execution-templates.md` |
| 架构文件过大、切片、多人/多会话协作 | `references/json-sharding.md` |
| 上下文压缩、恢复续跑、当前任务状态 | `references/context-recovery.md` |
| 影响范围、智能关联、优先级冲突 | `references/association-and-priority.md` |
| 21 项一致性校验、禁止事项、精细化标准 | `references/validation-checklist.md` |
| JSON 字段结构、完整 schema、四层读取策略 | `references/schemas.md` |
| 日常速查 | `references/principles-card.md`、`references/commands-cheatsheet.md` |

只读取当前任务需要的参考文件，不要为了“了解全貌”加载所有细节。默认不读取 `assets/`，除非要创建架构文件；默认不读取 `references/json-sharding.md`，除非发现 `架构切片.启用=true`、根 `architecture.json` 指向 `architecture/index.json`，或用户明确要求切片/架构文件夹；默认不读取所有切片，只读总索引和当前任务相关切片。技能的目的之一是降低模型单次负担，把注意力留给用户本次需求。

## 五个命令

- `/创建架构`：新项目从零开始。先功能簇三段式和功能树建模，再生成骨架 architecture.json，再逐块实现。
- `/分析架构`：已有代码迁入。先现状画像，只记录真实存在内容；再治理建议，指出缺失的商业标配、功能簇缺口、架构风险。
- `/修改架构`：修改 JSON 中已存在的模块、文件、接口、表、组件、路由等。
- `/追加架构`：新增 JSON 中不存在的模块或功能。
- `/校验架构`：检查 JSON 与代码是否漂移，输出偏差清单、影响范围、风险等级和修复建议。

详细流程见 `references/commands-workflows.md`。

## architecture.json 最小结构

新建或维护 architecture.json 时，至少保留这些中文主键：

```json
{
  "项目": {},
  "运行形态": [],
  "功能树": [],
  "专业能力索引": [],
  "入口": {
    "用户入口": [],
    "接口入口": [],
    "命令入口": [],
    "事件入口": [],
    "系统入口": [],
    "资源入口": []
  },
  "模块拓扑": {"节点": [], "依赖图": []},
  "模块树": [],
  "模块详情": {},
  "页面拓扑": [],
  "数据拓扑": [],
  "交付物": [],
  "系统集成": [],
  "接口契约": {},
  "实现清单": {},
  "完整细节": {},
  "测试责任矩阵": [],
  "验证证据": {},
  "架构切片": {"启用": false, "架构模式": "单文件", "切片清单": []},
  "上下文恢复点": {},
  "未决问题": [],
  "变更记录": []
}
```

完整 schema 和示例见 `references/schemas.md`、`assets/architecture-template.json`、`assets/example-architecture.json`。

## 必做校验

每次修改 architecture.json 后，必须执行 21 项一致性自查并把结果写入变更记录。完整清单见 `references/validation-checklist.md`。

## 可选工具链

本技能可以携带轻量脚本辅助确定性检查；工具链是技能增强，不是完整智能体，也不接管需求判断。

优先规则：
- 如果 `scripts/` 可运行，优先使用脚本完成 JSON 校验、架构差异和代码漂移扫描。
- 如果当前环境无法运行脚本，继续按本技能文本规则执行，并在 `验证证据.未验证项` 或最终汇报中记录“工具未运行”和原因。
- 工具只做读取、校验、对比、扫描和架构骨架生成；不得自动修改业务代码，不得扩展用户未要求的功能。
- 日常小改只需按需运行相关脚本；全量漂移扫描用于 `/校验架构`、大重构、长期未维护或怀疑 JSON 与代码不一致时。
- schema 是结构底线，不是完整工程判断；21 项一致性自查、功能树展开和模块详情设计仍由本技能规则完成。
- 初始化生成器只用于新项目或迁入前创建架构骨架；已有受管项目不得用生成器覆盖真实 `architecture.json`，除非用户明确要求并先备份/对比。

可用脚本：
- `scripts/init_architecture.py --output architecture.json`：从 `assets/architecture-template.json` 生成中文键架构骨架，默认不覆盖已有文件。
- `scripts/validate_architecture.py architecture.json`：校验 schema 结构底线、必需主键、通用入口主键、模块拓扑和实现清单基本一致性。
- `scripts/diff_architecture.py OLD.json NEW.json`：输出两个架构 JSON 的新增、删除和修改路径。
- `scripts/scan_code_drift.py PROJECT --architecture architecture.json`：扫描代码文件与 `实现清单` 是否存在缺失或未登记。
- `scripts/detect_task_posture.py --request "用户需求"`：按轻量规则输出任务类型、执行角色、任务场景、专业领域、需加载参考文件、必须校验项和禁止事项；只做建议，不接管执行。
- `scripts/validate_agent_output.py OUTPUT.json --schema assets/schema/agent-output.schema.json`：校验模块提案、接口提案、风险报告、验证报告、阻塞报告和门禁结果的基础结构。

## 完成前自检

最终汇报前必须自问：
1. 是否已先更新 `architecture.json` 或明确记录跳过原因？
2. 是否经过功能树、模块树/模块详情和实现清单，而不是直接跳代码？
3. 主动补全是否已分类，是否混入用户明确不要的内容？
4. 代码、测试、文档和验证证据是否与 JSON 一致？
5. 是否更新上下文恢复点、变更记录和剩余风险？

## 辅助文件

- `references/function-clusters.md` — 功能簇三段式、功能树建模、通用展开器、分层裁决、反薄 Demo、架构落位
- `references/universal-agent-protocol.md` — 跨编程智能体通用协议、执行等级和平台无关硬规则
- `references/dynamic-posture-context.md` — 动态姿势语境、触发事件、退出条件和语境栈
- `references/module-agent-protocol.md` — 模块智能体边界、功能族使用和跨模块提案规则
- `references/hard-gates.md` — 硬约束门禁、状态跃迁和阻塞/确认/降级结果
- `references/agent-output-contract.md` — 标准化智能体输出结构
- `references/task-posture.md` — 动态任务姿态、角色边界、风险信号、姿态切换和脚本输出解释
- `references/capability-index.md` — 专业能力索引、技能列表边界、外部技能候选
- `references/interaction-completeness.md` — 交互完整性检查包
- `references/progressive-decomposition.md` — 多层递进设计、分治设计、状态流转
- `references/commands-workflows.md` — 五个命令和完整工作流
- `references/execution-templates.md` — 任务前置输出、JSON 变更对比、变更类型矩阵、完成定义、失败恢复
- `references/json-sharding.md` — architecture/ 架构文件夹、切片协议、总索引、切片同步和迁移/回退流程
- `references/context-recovery.md` — 上下文压缩恢复协议、当前任务状态、续跑规则
- `references/association-and-priority.md` — 智能关联路由、联想深度、冲突优先级
- `references/validation-checklist.md` — 关键规则、21 项校验、禁止事项
- `references/schemas.md` — 四层递进 JSON Schema + 模块树/模块详情结构 + 四层读取策略 + 完整性检查清单
- `references/splitting-guide.md` — 功能/模块/文件三层粒度与拆分停止规则
- `references/principles-card.md` — 速记卡
- `references/quickstart.md` — 快速上手
- `references/commands-cheatsheet.md` — 命令速查
- `assets/architecture-template.json` — 空白架构模板
- `assets/schema/architecture.schema.json` — architecture.json 机器可读结构底线
- `assets/schema/agent-output.schema.json` — 智能体标准化输出机器可读结构底线
- `assets/example-agent-output.json` — 智能体标准化输出示例
- `assets/task-posture-rules.json` — 任务姿态建议器的机器可读轻量规则
- `assets/architecture-folder-template/` — architecture/ 架构文件夹模板，包含根指针和 index.json 总索引
- `assets/example-architecture.json` — 示例架构文件
- `adapters/` — Codex、Claude、Trae 和通用 CLI Agent 等平台适配说明
- `scripts/` — 可选轻量工具链，用于校验、diff、漂移扫描和智能体输出校验；不可用时按文本规则降级
