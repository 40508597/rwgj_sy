---
name: 任务架构
description: >
  用结构化 JSON 架构文件管理 AI 编程项目的完整生命周期。
  触发词：任务架构、架构JSON、模块化管理、按架构编写、结构化编程。
  面向中大型商业项目、长期维护项目、全栈工程项目、多模块系统和 AI 难以稳定维护的复杂代码库，覆盖前端、后端、接口、数据、任务、CLI、桌面端、移动端、EXE/安装包/Docker/SDK/插件等可交付形态、测试、部署和文档；不用于一次性脚本、小 demo、临时小修。若当前项目已存在 architecture.json，任何涉及代码、UI、接口、数据、测试、文件或行为修改的请求，即使用户未显式输入命令，也应自动按本技能执行；除非用户明确要求不要使用任务架构或直接快速修改。
  五个命令：/分析架构、/创建架构、/修改架构、/追加架构、/校验架构。
  六大机制：最大主动性设计、功能簇/功能树展开、专业能力索引、交互完整性、多层递进设计、分治设计法。
---
# 任务架构 — AI 编程项目架构管理

## 定位与适用边界

本技能是面向 Claude Code、Codex 等编程智能体的全栈工程化行为协议，不是完整智能体，也不是外部工具链。目标是让智能体在中大型商业项目中更工程化、稳定、可追踪，减少黑盒式自由发挥和用户反复补充细节的成本。

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

`architecture.json` 是项目唯一真相源：任何需求变更、功能新增、Bug 修复、重构，都先更新 JSON，再改代码。代码追随 JSON，JSON 不追随代码。

三条铁律：
1. **JSON 先行**：先改 JSON，再改代码。
2. **JSON 是法官**：代码与 JSON 不一致时，先做偏差分类；确认 JSON 代表设计真相后修正代码。
3. **禁止代码漂移**：代码中不得出现 JSON 未定义的模块、文件、接口、入口、数据结构。需要超出范围时，先更新 JSON。

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

调用本技能后，智能体必须把每次任务纳入闭环：判定任务 → 锁定用户本次需求 → 按需读取 JSON/切片 → 先更新 JSON → 再改代码 → 验证 → 更新恢复点和变更记录 → 汇报剩余风险。

## 注意力保护原则

本技能的目标是让用户每次需求精准落地，不是让流程占满模型注意力。任何时候都必须优先锁定“本次用户真正要改什么”，再按最小必要范围读取架构。

铁律：
- **用户本次需求优先**：先提取用户明确要求、隐含细节、不要做的事、验收信号，再进入功能簇或模块分析。
- **默认不全量读取**：不为“了解全貌”读取所有 references、所有切片或所有第4层细节。
- **默认不全量展开**：只展开与本次需求相关的功能簇、功能树、模块树和模块详情。
- **细节必须落位**：用户提到的每个具体页面、按钮、字段、接口、文案、状态、异常或约束，都必须落到 JSON 的对应节点、代码文件和验证项。
- **流程不能盖过结果**：如果流程步骤开始挤压对用户需求细节的处理，立即收缩读取范围，只保留能支撑本次落地的规则。

第一段输出必须先给出任务判断、自动选择的命令、是否存在 architecture.json、需要读取的 JSON 层级、影响范围和用户本次需求锁定。详细模板见 `references/execution-templates.md`。没有完成判定和 JSON 读取/更新计划前，不要创建文件、修改代码或扩展业务范围。

## 核心机制

1. **最大主动性设计**：商业级标配如日志、错误处理、健康检查、迁移、测试、安全边界按需纳入。
2. **功能簇/功能树展开**：把模糊需求展开为可验收、可落位、可测试的功能树节点。
3. **专业能力索引**：UI、测试、安全、性能、部署、文档等专业能力只做路由和回写约束，不接管主流程。
4. **交互完整性**：每个操作覆盖请求、反馈、异常、恢复闭环。
5. **多层递进设计**：全景分析 → 拆块骨架 → 逐块深度设计 → 集成验证。
6. **分治设计法**：大功能拆小块，每块按模块、入口、接口、数据、实现、测试完整落位。

## 何时读取参考文件

- 功能簇展开、功能树建模、模糊需求转架构、反薄 Demo：读 `references/function-clusters.md`
- 专业能力索引、技能列表边界、外部技能候选：读 `references/capability-index.md`
- 组件、接口、API、CLI、后台任务、桌面/移动端、可执行交付、系统集成、交互闭环：读 `references/interaction-completeness.md`
- 四层 JSON、逐块设计、三层粒度、拆块/停止规则：读 `references/progressive-decomposition.md` 和 `references/splitting-guide.md`
- 五个命令、创建/分析/修改/追加/校验流程、漂移修复、中断恢复：读 `references/commands-workflows.md`
- 任务前置输出、JSON 前后对比、变更类型矩阵、完成定义、失败恢复：读 `references/execution-templates.md`
- architecture.json 过大、长期迭代、多会话/多人协作需要创建 `architecture/` 架构文件夹时：读 `references/json-sharding.md`
- 上下文压缩、恢复续跑、当前任务状态：读 `references/context-recovery.md`
- 智能关联、影响范围、优先级冲突：读 `references/association-and-priority.md`
- 21 项一致性校验、禁止事项、精细化标准：读 `references/validation-checklist.md`
- JSON schema、字段结构、四层读取策略：读 `references/schemas.md`
- 日常速查：读 `references/principles-card.md` 和 `references/commands-cheatsheet.md`

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

## 辅助文件

- `references/function-clusters.md` — 功能簇三段式、功能树建模、通用展开器、分层裁决、反薄 Demo、架构落位
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
- `assets/architecture-folder-template/` — architecture/ 架构文件夹模板，包含根指针和 index.json 总索引
- `assets/example-architecture.json` — 示例架构文件
- `scripts/` — 可选轻量工具链，用于校验、diff 和漂移扫描；不可用时按文本规则降级
