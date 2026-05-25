---
name: 任务架构
description: >
  用结构化 JSON 架构文件管理 AI 编程项目的完整生命周期。
  触发词：任务架构、架构JSON、模块化管理、按架构编写、结构化编程。
  面向中大型商业项目、长期维护项目、多模块系统和 AI 难以稳定维护的复杂代码库；不用于一次性脚本、小 demo、临时小修。
  五个命令：/分析架构、/创建架构、/修改架构、/追加架构、/校验架构。
  五大机制：最大主动性设计、功能簇展开、交互完整性、多层递进设计、分治设计法。
---
# 任务架构 — AI 编程项目架构管理

## 定位与适用边界

本技能是面向 Claude Code、Codex 等编程智能体的工程化行为协议，不是完整智能体，也不是外部工具链。目标是让智能体在中大型商业项目中更工程化、稳定、可追踪，减少黑盒式自由发挥和用户反复补充细节的成本。

**适用：**
- 中大型商业项目、长期维护项目、多模块系统、复杂功能簇
- 有真实用户、真实数据、权限、安全、部署、测试或商业交付风险的项目
- 已经出现 AI 维护困难、模块漂移、接口/文档/测试不同步的代码库
- 后续需要多轮追加功能、修改需求、修复 Bug 的项目

**不适用：**
- 一次性脚本、小 demo、临时实验、小型原型
- 用户明确只要快速验证想法，且没有长期维护预期的任务
- 只解释代码、回答概念问题、运行一个简单命令的即时任务

进入适用场景后，不再按项目大小切换轻重模式。保持稳定流程，避免智能体误判“小项目可以省略关键工程步骤”。

## 最高原则

`architecture.json` 是项目唯一真相源：任何需求变更、功能新增、Bug 修复、重构，都先更新 JSON，再改代码。代码追随 JSON，JSON 不追随代码。

三条铁律：
1. **JSON 先行**：先改 JSON，再改代码。
2. **JSON 是法官**：代码与 JSON 不一致时，先做偏差分类；确认 JSON 代表设计真相后修正代码。
3. **禁止代码漂移**：代码中不得出现 JSON 未定义的模块、文件、接口、入口、数据结构。需要超出范围时，先更新 JSON。

## JSON 中文化规范

architecture.json 是给用户、后续智能体和开发者共同阅读的工程真相源，字段名和说明必须优先使用中文。

**必须中文：** JSON 对象键名、说明性字段、状态值、分类值、测试描述、交互说明、异常说明、变更记录正文。

**保留原样：** 真实代码标识符、函数名、类名、变量名、模块名、包名、文件路径、路由路径、HTTP 方法、数据库表名和字段名、技术栈名、第三方库名、协议名、命令行参数。

**禁止：** 新建 architecture.json 时使用 `project`、`modules`、`contracts`、`changeLog` 等英文主键名；禁止为了中文化而改写真实代码契约。

## 执行契约

调用本技能后，智能体必须把每次任务纳入同一个闭环：

```
识别任务类型
  → 功能簇展开
  → 更新 architecture.json
  → 影响范围分析
  → 分块设计与实现
  → 测试/验证
  → 一致性自查
  → 更新上下文恢复点
  → 写入变更记录
  → 汇报结果与剩余风险
```

第一段输出必须先给出：任务判断、适用边界、需要读取的 JSON 层级、影响范围。没有完成判定前，不要创建文件、修改代码或扩展业务范围。

每次汇报至少包含：
- 任务判断：创建 / 分析 / 追加 / 修改 / 校验
- 功能簇展开摘要：核心功能、天然绑定功能、商业标配功能、待确认扩展
- 影响范围：模块、入口、接口、文件、数据、交互、测试
- JSON 变更摘要：新增、修改、废弃、状态变更
- 执行块列表：本次完成什么，哪些依赖未完成
- 验证结果：测试、手动检查、一致性校验、验证证据
- 上下文恢复点：当前任务状态、继续位置、未验证项、用户约束
- 变更记录与剩余风险

## 核心机制

1. **最大主动性设计**：商业级标配如日志、错误处理、健康检查、迁移、测试、安全边界直接纳入，不要求用户逐条说明。
2. **功能簇展开**：把模糊需求展开为应有功能，再把功能本体展开为天然绑定细节，最后落位到 architecture.json。
3. **交互完整性**：每个操作必须覆盖请求、反馈、异常、恢复闭环。
4. **多层递进设计**：全景分析 → 拆块骨架 → 逐块深度设计 → 集成验证，不跳步。
5. **分治设计法**：大功能拆小块，每块按模块、入口、接口、数据、实现、测试完整落位。

## 何时读取参考文件

- 功能簇展开、模糊需求转架构、反薄 Demo：读 `references/function-clusters.md`
- 组件、接口、CLI、前端交互闭环：读 `references/interaction-completeness.md`
- 四层 JSON、逐块设计、拆块粒度：读 `references/progressive-decomposition.md` 和 `references/splitting-guide.md`
- 五个命令、创建/分析/修改/追加/校验流程、中断恢复：读 `references/commands-workflows.md`
- 上下文压缩、恢复续跑、当前任务状态：读 `references/context-recovery.md`
- 智能关联、影响范围、优先级冲突：读 `references/association-and-priority.md`
- 13 项一致性校验、禁止事项、精细化标准：读 `references/validation-checklist.md`
- JSON schema、字段结构、四层读取策略：读 `references/schemas.md`
- 日常速查：读 `references/principles-card.md` 和 `references/commands-cheatsheet.md`

只读取当前任务需要的参考文件，不要为了“了解全貌”加载所有细节。技能的目的之一是降低模型单次负担。

## 五个命令

- `/创建架构`：新项目从零开始。先功能簇三段式，再生成骨架 architecture.json，再逐块实现。
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
  "入口": {
    "页面路由": [],
    "API路由": [],
    "静态资源路由": [],
    "CLI命令树": [],
    "后台任务": [],
    "事件入口": []
  },
  "模块拓扑": {"节点": [], "依赖图": []},
  "页面拓扑": [],
  "数据拓扑": [],
  "接口契约": {},
  "实现清单": {},
  "完整细节": {},
  "测试责任矩阵": [],
  "验证证据": {},
  "上下文恢复点": {},
  "未决问题": [],
  "变更记录": []
}
```

完整 schema 和示例见 `references/schemas.md`、`assets/architecture-template.json`、`assets/example-architecture.json`。

## 必做校验

每次修改 architecture.json 后，必须执行一致性自查并把结果写入变更记录。校验包括依赖完整性、入口类型、接口实现、数据迁移、认证依赖、异常契约测试、依赖图无环、交互完整性、代码漂移、变更可追踪、验证证据完整等。完整清单见 `references/validation-checklist.md`。

## 辅助文件

- `references/function-clusters.md` — 功能簇三段式、通用展开器、分层裁决、反薄 Demo、架构落位
- `references/interaction-completeness.md` — 交互完整性检查包
- `references/progressive-decomposition.md` — 多层递进设计、分治设计、状态流转
- `references/commands-workflows.md` — 五个命令和完整工作流
- `references/context-recovery.md` — 上下文压缩恢复协议、当前任务状态、续跑规则
- `references/association-and-priority.md` — 智能关联路由、联想深度、冲突优先级
- `references/validation-checklist.md` — 关键规则、13 项校验、禁止事项
- `references/schemas.md` — 四层递进 JSON Schema + 四层读取策略 + 完整性检查清单
- `references/splitting-guide.md` — 拆块策略参考
- `references/principles-card.md` — 速记卡
- `references/quickstart.md` — 快速上手
- `references/commands-cheatsheet.md` — 命令速查
- `assets/architecture-template.json` — 空白架构模板
- `assets/example-architecture.json` — 示例架构文件
