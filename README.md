# 任务架构（rwgj）

> 任务架构通用智能体能力包，全局薄入口，承载任务架构规则、能力定义与共享工具。
> 让 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、CLI Agent 与自研 Agent 按同一套任务架构协议工作。

[![Project license: MIT](https://img.shields.io/badge/Project-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/40508597/rwgj_sy?style=social)](https://github.com/40508597/rwgj_sy)
[![GitHub forks](https://img.shields.io/github/forks/40508597/rwgj_sy?style=social)](https://github.com/40508597/rwgj_sy)
[![GitHub release](https://img.shields.io/github/v/release/40508597/rwgj_sy)](https://github.com/40508597/rwgj_sy/releases)
[![verify](https://github.com/40508597/rwgj_sy/actions/workflows/verify.yml/badge.svg)](https://github.com/40508597/rwgj_sy/actions/workflows/verify.yml)
[![中文文档](https://img.shields.io/badge/文档-中文-red.svg)](README.md)
[![跨平台](https://img.shields.io/badge/平台-Codex%20%7C%20Claude%20%7C%20Trae%20%7C%20Cursor%20%7C%20...-blue)](README.md)

---

## 一、仓库简介

本包由薄入口、内部四层规则和按需专业能力组成。默认专业能力目录包含原有三项审查资料与本轮新增的十二项编程能力，覆盖架构设计、决策、接口、规划、调试、测试、误用审查和 UI。宿主按已确认需求、任务姿态与真实场景读取最小适配指南；完整清单与条件见 [编程子技能](shared/references/programming-subskills.md)。规划、审查与事实协议不限制项目语言，具体工具的运行支持由项目环境决定。

项目自有文件采用 [MIT](LICENSE)；第三方原文及中文适配分别保留 MIT、Apache-2.0 或 CC-BY-SA-4.0，具体归属与条款见 [第三方声明](THIRD-PARTY-NOTICES.md)。

当前版本包含 2026-10-04 通用质量升级：架构决策记录、按指定关系检查模块边界与循环、项目配置的质量指标与 CRAP、绑定选定输入的真实执行收据，以及在隔离副本中故意引入字节故障验收检查器。规则与事实协议不限制项目语言，`.e`、未知工程格式、二进制和无后缀实现单元均可接入；外部信息不足时显示未验证，不声称内置全语言解析器。完整交付使用 gate_check 的 --quality-required。说明与模板见 [通用质量协议](shared/references/universal-quality.md)。技能元数据名规范为 task-architecture，中文标题与使用说明保留。

- **角色**：薄入口技能包，承载任务架构规则与共享工具
- **使用方**：Codex / Claude Code / Trae / Cursor / Windsurf / Cline / Continue / CLI Agent / 自研 Agent
- **核心特性**：真相源分离（能力在仓库，项目状态在调用方 `architecture/`）、跨平台一致（差异只写在 `shared/adapters/`）

---

## 二、版本演进

本仓库以 **17 个历史版本** + 当前 rwgj 入口为时间线，按目录内文件夹的 mtime 顺序**逐个 commit** 形成完整演进链。

完整 commit 历史：`git log --reverse --oneline`

**版本阶段**：
- **任务架构 1.0 ~ 1.1.9**（11 个版本）：早期演进
- **任务架构 1.2 / 1.3**：动态任务姿态、跨智能体协议
- **任务架构-通用智能体版**：平台无关化变体
- **任务架构-能力体系 1.0 / 1.1.1 / 1.1.2**：能力体系化（1.1.2 = 现行入口的前身）
- **rwgj (current)**：薄入口化、组织化
- **rwgj v1.1.0（2026-08-04 发布）**：F+B+C 强制机制成熟 + 质量工程（质量红线、独立审计、CI/单测/数字对账）

**能力继承关系**：

| 来源版本 | 保留能力 | 当前位置 |
|----------|----------|----------|
| 1.0 / 1.1 | 最大主动性、功能簇、交互完整性、多层递进、分治、智能关联 | `project-depth-core` |
| 1.1.2 | 主入口瘦身、references 分拆 | 总入口 + `shared/references/` |
| 1.1.5 / 1.1.6 | 功能树、模块树、模块详情、切片意识 | `architecture-json` |
| 1.1.7 / 1.1.8 | validate/scan/diff/init 工具链 | `shared/scripts/` |
| 1.1.9 | 受控主动性、防扁平化、注意力保护、完成前自检 | `project-depth-core` + `architecture-json` |
| 1.2 | 动态任务姿态建议器、三轴任务校准 | `shared/scripts/` + 辅助参考 |
| 1.3 | 跨智能体协议、适配层、虚拟模块审议、硬门禁、标准输出契约 | `agent-protocol` |

**继承原则**：
```text
1.1 做认知内核
1.2 做结构落位
1.3 做协议外壳
```

---

## 三、仓库结构

```text
任务架构/
├── .git/                       # git 仓库
├── .github/                    # CI 工作流
│   └── workflows/verify.yml    # 一键验证 + 单元测试（push/PR 自动运行）
├── .gitignore                  # 忽略 __pycache__/报告/项目状态
├── .gitattributes              # 保留导入子技能文件的原始字节
├── .source.json                # 技能来源元数据
├── README.md                   # 本文件（仓库门面 + 完整能力 + 详细使用）
├── SKILL.md                    # Agent 薄入口
├── AGENT-USAGE.md              # Agent 通用入口
├── CLAUDE.md                   # AI 在本仓库工作须知（瘦身版）
├── ENFORCEMENT-GUIDE.md        # F+B+C 强制执行机制指南
├── CONTRIBUTING.md             # 贡献指南
├── LICENSE                     # 项目自有文件的 MIT 许可
├── THIRD-PARTY-NOTICES.md       # 第三方原文与适配的分项许可
├── verify-all.sh               # 一键验证脚本
├── tests/                      # 单元测试（stdlib unittest）
├── docs/                       # 设计文档
│   ├── regression-assertions.md  # 回归断言场景清单
│   └── adr/                      # 架构决策记录（4 篇）
├── scripts/                    # 顶层脚本
│   ├── validate_task_architecture_system.py
│   ├── check_doc_counts.py       # 文档数字/引用对账
│   └── demo_project.py           # 端到端演示（临时受管项目全验证链）
├── shared/                     # 共享资源（Agent 加载）
│   ├── adapters/               # 平台适配
│   ├── assets/                 # 资产模板 + Schema + folder-template 样张
│   ├── legacy/                 # 历史 SKILL 归档
│   ├── references/             # 参考文档（数量见 §4.5）
│   ├── scripts/                # 工具脚本（数量见 §4.5，含 _archlib 等内部辅助）
│   └── subskills/              # 专业 GUIDE + 固定上游原文、参考与许可
└── skills/                     # 能力层（单一技能入口）
    ├── task-architecture/      # 路由层 LAYER.md
    ├── project-depth-core/     # 主动理解内核 CORE.md
    ├── architecture-json/      # 架构物化层 SCHEMA.md
    └── agent-protocol/         # 外围协议层 PROTOCOL.md
```

---

## 四、技能能力

### 4.1 能力地图（5 大类）

#### 4.1.1 注意力保护区（核心能力 3 项）

| 能力 | 子能力层 | 目标 |
|------|--------|------|
| 主动理解 | `project-depth-core` | 想得深 |
| 物化架构 | `architecture-json` | 落得稳 |
| 外围协议 | `agent-protocol` | 跑得广 |

#### 4.1.2 共享资源（6 类）

> 数量口径统一由 §4.5 技术指标表维护（check_doc_counts.py 自动对账），本表不重复数字。

| 资源类型 | 数量 | 路径 |
|----------|------|------|
| 参考文档 | 见 §4.5 | `shared/references/` |
| 脚本工具 | 见 §4.5 | `shared/scripts/` + `scripts/`（含内部辅助：`_archlib`、`run_with_progress`、`check_doc_counts`，不计入用户工具表）|
| 资产模板 | 见 §4.5 | `shared/assets/`（顶层 .json）|
| 平台适配 | 见 §4.5 | `shared/adapters/` |
| 历史档案 | 见 §4.5 | `shared/legacy/` |
| Schema | 见 §4.5 | `shared/assets/schema/` |

#### 4.1.3 工具能力（面向用户 CLI + 内部辅助）

> 下表为面向用户 CLI；`_archlib.py` 共享底座、`run_with_progress.py` 工具包装器、`check_doc_counts.py` 文档数字与引用对账为开发自检，不计入用户工具表（数量口径见 §4.5）。

##### 强制执行工具（F+B+C 三件套）🆕

| 工具 | 类型 | 主要功能 |
|------|------|----------|
| `check_placeholders.py` | **强制执行** | 检测占位符，核心字段未填写返回错误码 |
| `manage_state.py` | **强制执行** | 管理进度状态文件（9 个必需阶段 + 1 个可选追踪）|
| `judge_progress.py` | **强制执行** | 事中验证裁判（综合三重检查）|
| `detect_should_trigger.py` | **强制触发** | 检测项目是否应使用任务架构 |

##### 传统验证工具

| 工具 | 类型 | 主要功能 |
|------|------|----------|
| `validate_architecture.py` | 验证 | 校验 architecture.json 完整性 |
| `validate_protocol_semantics.py` | 验证 | 协议层语义回归 |
| `validate_agent_output.py` | 验证 | Agent 输出契约一致性 |
| `validate_task_architecture_system.py` | 验证 | 整体系统（顶层入口） |
| `scan_code_drift.py` | 扫描 | 代码与架构 drift 检测 |
| `diff_architecture.py` | 对比 | 两个 architecture.json 差异 |
| `gate_check.py` | 门禁 | 硬门禁规则检查 |
| `init_architecture.py` | 初始化 | 单文件迁移 / 新建切片（默认使用占位符模板）|
| `detect_task_posture.py` | 姿态 | 任务姿态分类（dynamic/linear/reactive） |
| `detect_small_command.py` | 降级 | 小命令降级检测（三档 + 运行/修改分型 + 高风险词升档） |
| `check_regression_assertions.py` | 回归 | 21 项回归断言 |
| `taskarch_cli.py` | 聚合 | 顶层 CLI（lineage/slice/gate-file 等） |
| `check_quality_redlines.py` | 质量 | 质量红线检查（交互完整性/可验收/导出类安全信号/空壳模块） |
| `audit_architecture.py` | 审计 | 独立审计问卷（generate 生成 10 问 / report 核验完整性） |
| `render_architecture.py` | 可视化 | 单向渲染真相源（md=Mermaid 报告 / html=单文件交互 / json=结构化） |
| `demo_project.py` | 演示 | 临时受管项目端到端验证链（接入 verify-all） |
| `resolve_tool.py` | 定位 | 解析工具脚本绝对路径（项目锚点优先 → 安装目录兜底；--json / --list） |
| `check_project_quality.py` | 通用质量 | 根据选定范围的观察事实检查依赖边界、循环、质量指标、CRAP、决策记录和执行收据；缺证据为未验证 |
| `run_verification.py` | 执行证据 | 运行明确 argv，记录命令结果、选定输入前后哈希与原始输出，供质量门禁复核 |
| `run_quality_probes.py` | 检查器验收 | 在两份隔离副本中运行正常与故意改坏样例，核对目标检查是否检出，固定分母保留失败与未知 |
| `plan_capabilities.py` | 专业能力规划 | 按已确认任务/姿态与当前可用catalog选择最小读取计划，输出文件指纹与变化；不自动加载或执行技能 |
| `check_capability_usage.py` | 专业能力核验 | 核对启用计划、输入、使用记录、作用域、执行收据与产物/架构回写；结构通过不证明审查正确 |
| `check_subskill_sources.py` | 来源完整性 | 核对本地来源锁、目录绑定、文件哈希和许可记录；不联网认证远端提交或执行者身份 |

**F+B+C 三件套机制**：
- **F（占位符）**：让缺失可见 - `__待填__` 强制填写
- **B（状态文件）**：让进度可查 - 客观记录完成度
- **C（事中裁判）**：让缺失被拦截 - 不通过禁止继续

完整使用指南：[ENFORCEMENT-GUIDE.md](ENFORCEMENT-GUIDE.md)

#### 4.1.4 平台适配

| 平台 | 适配文件 | 状态 |
|------|----------|------|
| Claude Code | `shared/adapters/claude.md` | ✓ |
| Codex | `shared/adapters/codex.md` | ✓ |
| Trae | `shared/adapters/trae.md` | ✓ |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | ✓ |

> 适配层**只写差异**，**不复制规则**。其余平台（Cursor / Windsurf / Cline / Continue）无独立差异时走 `generic-cli-agent` 适配。

### 4.2 子能力层详细说明

#### 4.2.1 `task-architecture` — 总入口

- **职责**：薄路由，不承载完整规则
- **加载时机**：所有用户需求的第一站
- **关键能力**：决定是否进入完整三层流程（含小命令降级三档判定：完全跳过 / 最小闭环 / 完整流程）
- **不做**：不直接写代码、不展开业务细节

#### 4.2.2 `project-depth-core` — 主动理解内核

- **职责**：把模糊需求变成清晰架构
- **核心机制**（6 大）：
  1. **最大主动性设计**：主动补全安全、日志、错误处理、测试、部署
  2. **功能簇展开**：菜单栏不只是横条，导出不只是按钮
  3. **交互完整性**：操作必须有"请求/处理中/成功/失败/异常恢复"
  4. **多层递进设计**：全景 → 骨架 → 逐块 → 集成
  5. **分治设计法**：大功能拆小块，每块让不熟悉项目的人也能独立实现
   6. **实现期循环展开**：发现状态、边界或验证责任缺口时局部回展开，先更新架构再继续实现
- **强制停止规则**：每个叶子节点必须满足"单一可测试操作 / 不可拆解的外部事实 / 明确排除"才能停止展开
- **架构归位前置**：进入实现前必须判断"功能本体/状态/上下游/应落位位置"

#### 4.2.3 `architecture-json` — 物化层

- **职责**：把理解结果落到 `architecture/` 切片目录
- **强制结构**：
  ```text
  architecture.json              # 轻量指针
  architecture/
    index.json                   # 真相源总索引
    features/
    modules/
    data/
    pages/
    tasks/
  ```
- **落位顺序**：需求理解 → 功能树 → 模块树 → 模块详情 → 入口/接口/数据/页面/任务/交付物 → 实现清单 → 测试责任矩阵 → 验证证据 → 变更记录
- **模块详情底线**（每个实现模块必须有）：职责/非职责、功能树节点、上下游、内部结构、状态机、数据读写、错误边界、配置/安全/日志/性能/测试责任

#### 4.2.4 `agent-protocol` — 外围协议层

- **职责**：跨平台、门禁、标准化、能力降级
- **加载时机**：仅在需要时（**不得抢占 `project-depth-core` 入口优先级**）
- **5 大触发条件**：
  1. 跨 Codex/Claude/Trae/Cursor/Windsurf/Cline/Continue/自研 Agent
  2. 标准化模块提案、门禁、风险/验证报告
  3. 虚拟模块智能体审议
  4. 能力降级记录
  5. 硬门禁结果
- **边界**：不展开功能簇、不判断项目应是什么、不替代模块详情设计
- **交叉审计**：支持多模型/多会话独立审计，但**不得引入中央协调智能体**

#### 4.2.5 专业子能力接入

内部四层负责同一技能的规则路由；专业子能力服务当前功能节点与模块。默认目录现有 15 项，原有三项审查资料与新增十二项编程方法都已注册，按本次适用性选择：

| 方向 | 随包能力 | 说明与来源 |
|------|----------|------------|
| 基础审查与交接 | 代码语义审查、交接完整性、产物独立核验 | [能力索引](shared/references/capability-index.md) |
| 架构与接口 | 架构模式与模块边界、架构决策记录、接口契约设计 | [架构设计](shared/subskills/architecture-patterns/GUIDE.md)、[决策记录](shared/subskills/architecture-decisions/GUIDE.md)、[接口契约](shared/subskills/api-contract-design/GUIDE.md)；wshobson/agents |
| 规划、调试与测试 | 实现任务规划、系统调试、行为测试设计 | [实现规划](shared/subskills/implementation-planning/GUIDE.md)、[系统调试](shared/subskills/systematic-debugging/GUIDE.md)、[行为测试](shared/subskills/behavior-test-design/GUIDE.md)；obra/superpowers |
| 质量与缺陷检查 | 属性与不变量测试、接口与配置误用审查、同类缺陷排查 | [属性测试](shared/subskills/property-testing/GUIDE.md)、[误用审查](shared/subskills/api-misuse-review/GUIDE.md)、[同类缺陷](shared/subskills/defect-variant-review/GUIDE.md)；Trail of Bits |
| UI 与浏览器 | UI 视觉与交互设计、Web 浏览器验收 | [UI 设计](shared/subskills/frontend-visual-design/GUIDE.md)、[浏览器验收](shared/subskills/browser-acceptance/GUIDE.md)；Anthropic |
| Web 界面审查 | 交互、键盘操作、可访问性和状态反馈 | [Web UI 审查](shared/subskills/web-ui-review/GUIDE.md)；Vercel |

新增十二项默认各读取一份 `GUIDE.md`；原有三项读取对应参考文档。原文和额外参考按实际需要与预算登记后再读取。UI 设计需要真实界面，Web 审查需要真实 Web 场景，浏览器验收还需要可用浏览器工具，同类缺陷排查需要已确认的缺陷实例。可用性使用实际任务事实及 JSON 布尔值，不能用关键词、数字 1 或字符串 true 代替。已有宿主 UI、测试、安全、性能、部署等技能也可按元数据接入。

宿主提供的技能名称、描述、路径可用于筛选适用本地技能并构造最小 catalog，日常使用无需用户反复填写注册表。`plan_capabilities.py` 只生成适用计划；宿主实际读取选中的 `read_files` 才把资料载入上下文。没有系统提示注入 API 时，明确表述为按需读取。阶段、范围或输入变化时重新规划；能力退出不消除未解决的必需证据，缺失仍为 unknown，不能改记 skipped。退出证据核验后，才在新语境中明确记录已解除或已完成的能力。

`check_capability_usage.py` 复核当前计划、输入、实际使用、作用域、产物及架构回写；模型审查与执行收据分开。结构校验通过不证明代码正确，缺必需证据为unknown，旧索引未启用专项可以skipped。完全跳过不建状态，小任务只做相称记录；具体契约、CLI与模板见 [专业能力索引](shared/references/capability-index.md)。

### 4.3 参考文档矩阵

按主题分组（数量口径见 §4.5）：

| 类别 | 文档 | 内容 |
|------|------|------|
| 主动理解 | `function-clusters.md` | 功能簇展开与停止规则 |
| 主动理解 | `interaction-completeness.md` | 交互闭环 |
| 主动理解 | `progressive-decomposition.md` | 多层递进设计 |
| 主动理解 | `splitting-guide.md` | 拆分粒度与停止规则 |
| 主动理解 | `association-and-priority.md` | 影响范围、关联、优先级 |
| 主动理解 | `capability-index.md` | 专业能力路由（UI/测试/安全/性能/部署/文档）|
| 专业方法 | `programming-subskills.md` | 随包编程能力、真实场景条件、固定来源与分项许可 |
| 专业审查 | `semantic-code-review.md` | 状态、异常、并发、持久化与公共契约审查 |
| 协作恢复 | `handoff-integrity.md` | 原约束、ID、部分失败和退出条件完整交接 |
| 产物核验 | `artifact-integrity.md` | 独立解析与来源/产物/回写等价检查 |
| 主动理解 | `principles-card.md` | 原理卡片与速查 |
| 架构物化 | `schemas.md` | JSON 字段、中文化规范、四层读取 |
| 架构物化 | `commands-workflows.md` | 5 个命令、创建/分析/修改/追加/校验 |
| 架构物化 | `validation-checklist.md` | 21 项一致性校验 + 硬约束门禁 |
| 架构物化 | `json-sharding.md` | 强制切片目录 |
| 协议适配 | `universal-agent-protocol.md` | 跨 Agent 通用协议 |
| 协议适配 | `module-agent-protocol.md` | 虚拟模块审议 |
| 协议适配 | `agent-output-contract.md` | 标准化输出契约 |
| 工作流 | `quickstart.md` | 快速上手 |
| 工作流 | `commands-cheatsheet.md` | 命令速查 |
| 工作流 | `context-recovery.md` | 上下文恢复 |
| 工作流 | `execution-templates.md` | 执行模板 |
| 工作流 | `task-posture.md` | 任务姿态与动态姿势语境 |
| 工作流 | `small-command-degradation.md` | 小命令降级（三档/两型/回执） |

### 4.4 能力边界

**明确不做的**：
- ✗ **不**做代码实现的"中央调度"
- ✗ **不**在技能目录持久化项目业务状态
- ✗ **不**复制子能力层细则到总入口
- ✗ **不**让 `agent-protocol` 抢占 `project-depth-core` 入口
- ✗ **不**做功能簇展开的"中央判断"（这是认知层职责）
- ✗ **不**维护分叉规则（所有 Agent 读同一份）

**工具降级策略**：工具不可用时按文本规则降级执行，并在验证证据中记录"未运行原因"。

**性能与规模**：结构检查与实际执行分别评估；构建、测试及故障样例运行时间取决于调用方项目和指定命令。大型工程按模块和关系划定检查范围，并保留未采集范围。

### 4.5 技术指标

> 真相源：脚本/文件以仓库实际盘点为准，文档对账用。全仓库唯一数字口径表格，其余章节引用本表（check_doc_counts.py 自动对账）。

| 指标 | 数值 |
|------|------|
| 子能力层数 | 4 |
| 参考文档数 | 25 |
| 工具脚本数 | 31（shared/scripts 28 + scripts 3，含内部辅助；optional/ 宿主适配器单独分发）|
| 必需阶段数 | 9（manage_state.STANDARD_STAGES required=True）|
| 平台适配数 | 4 |
| Schema 数 | 5 |
| 资产模板数 | 11（shared/assets 顶层 .json）|
| 历史归档 | 4（shared/legacy/ 下含 README.md 索引 + 3 份历史 SKILL）|
| 设计文档数 | 6（docs/ 下 1 篇回归断言 + docs/adr/ 5 篇决策记录含索引）|
| 顶层入口文件 | 2（SKILL.md / AGENT-USAGE.md）|
| 单元测试 | 31 个测试文件（tests/test_*.py，stdlib unittest；用例数由 check_doc_counts.py 动态统计）|
| CI 工作流 | 1（.github/workflows/verify.yml）|
| 总文件数 | ~219（不含 .git/、缓存和生成的验证报告，含测试与 CI）|

#### 4.5.1 分发最小运行集

技能运行只需要以下内容；`tests/`、`.pytest_cache/`、`.github/`、`verify-all.sh` 与 `scripts/check_doc_counts.py` 均属开发自检资产，第三方嵌入或内嵌分发可按此裁剪：

```text
SKILL.md
LICENSE                    THIRD-PARTY-NOTICES.md
skills/task-architecture   skills/project-depth-core   skills/architecture-json   skills/agent-protocol
shared/scripts             shared/references           shared/adapters            shared/assets
shared/subskills
```

使用默认专业目录时，`shared/subskills/` 中的 GUIDE、固定来源和许可文件，以及根目录的许可与第三方声明一起分发。若选择 Claude Stop hook，需额外分发 `optional/claude_stop_hook.py`；一键项目验证可额外分发 `verify-all.sh`，其 --project 模式不依赖 tests/、README 或开发自检脚本。完整 --self-test 则需要开发分发资产。安装、提供源码或配置示例都不等于宿主集成已经启用。

来源锁按原始字节校验。仓库的 `.gitattributes` 为 `shared/subskills/` 保留原始字节，避免 Git 自动换行转换破坏记录的哈希；重新分发时也保留这些来源与适配文件的编码和换行。

### 4.6 适用场景评估

**强适用场景 ✓**：
- 新建项目：从 0 到 1 完整功能设计
- 复杂功能开发：需要多层递进 + 模块详情 + 验证责任
- 跨智能体协作：Codex/Claude/Trae 团队协作
- 架构演进：从单文件迁移到切片目录
- 代码与架构一致性治理：drift 检测、回归断言
- 模糊需求澄清：通过功能簇展开把"想要什么"变成"应该是什么"

**一般适用场景 ○**：
- 简单功能修改：单文件 1-2 处变更
- Bug 修复：定位后定向修改
- 文档生成：基于 `architecture/` 生成

**不适用场景 ✗**：
- 纯概念问答：不进入完整流程
- 临时性小脚本：不值得启动三层流程
- 已严格规范化的项目：可能与现有规范冲突
- 超大型项目（>100 万行）：建议按子模块单独使用

### 4.7 与传统开发流程的对比

| 维度 | 传统开发 | 任务架构（rwgj） |
|------|----------|------------------|
| 需求理解 | 文档/PR/口头 | 功能簇展开 + 强制停止规则 |
| 架构设计 | 自由发挥 | 强制切片目录 + 模块详情底线 |
| 跨平台 | 各平台独立实现 | 同一份能力 + 平台适配差异 |
| 一致性 | 人工 review | 工具验证结构与部分一致性，21 项语义清单配合工程复核 |
| 代码 drift | 滞后发现 | 实时扫描 |
| 上下文恢复 | 重新看文档 | 切片目录 + 恢复点 |

---

## 五、详细使用说明

### 5.1 安装与部署

#### 全局安装模式（推荐）

适用场景：多个项目共用同一套能力包，避免每个项目重复维护。

```bash
# 1. 克隆或复制到全局 skills 目录
#    路径根据你的平台/工具调整：
#    - Codex/Claude: ~/.codex/skills/rwgj/ 或 ~/.claude/skills/rwgj/
#    - Trae: ~/.trae/skills/rwgj/
#    - 通用: ~/skills/rwgj/

# 2. 让 Agent 触发（不同 Agent 触发方式略有差异）
#    Codex/Claude: 通过 SKILL.md 自动识别
#    Trae: 在项目根目录创建 .trae/skills/rwgj 软链接
#    自研 Agent: 按 agent-protocol 适配层协议加载
```

#### 项目级复制模式

适用场景：项目需要隔离的能力定义，或离线/无网络环境。

```bash
# Git Bash / POSIX shell：分别设置实际源目录和项目根目录
TASK_ARCH_SOURCE="/absolute/path/to/task-architecture"
TASK_ARCH_PROJECT="/absolute/path/to/project"
TASK_ARCH_INSTALL="$TASK_ARCH_PROJECT/.agents/skills/task-architecture"
mkdir -p "$TASK_ARCH_INSTALL"
cp "$TASK_ARCH_SOURCE/SKILL.md" "$TASK_ARCH_SOURCE/LICENSE" "$TASK_ARCH_SOURCE/THIRD-PARTY-NOTICES.md" "$TASK_ARCH_INSTALL/"
cp -R "$TASK_ARCH_SOURCE/skills" "$TASK_ARCH_SOURCE/shared" "$TASK_ARCH_INSTALL/"
# 可选一键项目验证入口：
cp "$TASK_ARCH_SOURCE/verify-all.sh" "$TASK_ARCH_INSTALL/"

# 告诉 Agent：读取 .agents/skills/task-architecture/SKILL.md，处理本项目。
```

只分发运行能力集到上述子目录，保留项目根现有 README、.gitignore、CLAUDE.md 和 .github。不要复制能力仓库的安装/自检标识到业务项目根。项目的 architecture.json 与 architecture/ 独立保存在项目根，并按项目协作要求版本化。Windows PowerShell 可用 Copy-Item -LiteralPath 复制同一组文件到同一子目录。

选择 Claude Stop hook 时另复制 `optional/claude_stop_hook.py` 到安装目录的 `optional/`，按 `shared/adapters/claude.md` 合并配置并实际验证宿主加载；核心最小集本身不包含已启用的 hook。

#### 两种模式对比

| 维度 | 全局安装 | 项目级复制 |
|------|----------|------------|
| 共享能力更新 | 一次更新，多项目生效 | 每个项目单独更新 |
| 项目真相源（architecture/）| 每个项目独立 | 跟随项目 |
| 适配层差异（adapters/）| 跟随全局 | 跟随项目（可定制）|
| 适合 | 标准化工作流 | 项目特化需求 |

#### Proma Agent 专属集成指南

**Proma** 是由 Claude Agent SDK 驱动的桌面应用，本技能包完全兼容 Proma Agent。

##### 安装到 Proma 工作区

```bash
# 方式 1：全局安装（推荐）
# 将本目录复制到 Proma 工作区的 skills 目录
cp -r <本目录> ~/.proma/agent-workspaces/<workspace-id>/skills/rwgj/

# 方式 2：作为附加目录
# 在 Proma 工作区设置中添加本目录作为附加工作目录
# 路径: C:\Users\<用户名>\Desktop\AI项目\技能\技能架构
```

##### Proma 特定功能集成

**1. 协作子 Agent**
```text
与 Proma 内置的 collaboration MCP 工具集成，可以：
- 创建并行验证子会话（多个独立验证任务）
- 跨模块审议（不同子 Agent 审查不同模块）
- 对抗性验证（一个实现，一个审查）

示例：
使用任务架构做架构设计，并创建 3 个子 Agent 分别验证功能完整性、性能风险和安全问题
```

**2. 定时架构验证**
```text
与 Proma 内置的 automation MCP 工具集成，可以：
- 创建每日架构一致性检查任务
- 定期扫描代码与架构偏移
- 自动生成架构健康度报告

示例：
创建定时任务，每天早上 9 点自动运行架构验证并生成报告
```

**3. 一键验证脚本**
```bash
# 能力包自身自检（只能证明包与工具的回归结果）
bash verify-all.sh --self-test
# 实际项目验证（读取调用方架构与质量配置，不用样例替代）
bash verify-all.sh --project "/absolute/path/to/project"

# 或在 Proma Agent 对话中：
运行一键验证脚本，检查项目架构完整性
```

**4. Proma Cloud API 集成**
```text
如果需要在验证流程中调用 AI 模型（如生成架构建议、智能分析），
可以使用 Proma 内置的 proma_cloud MCP 工具获取 API 凭据。
```

##### Proma Agent 触发方式

在 Proma Agent 对话中直接输入：

```text
使用任务架构做 XXX
```

Proma Agent 会自动：
1. 加载 SKILL.md 薄入口
2. 按三层顺序执行（project-depth-core → architecture-json → agent-protocol）
3. 生成或更新 architecture/ 切片目录
4. 运行验证工具并提供反馈

##### Proma 工作区文件组织

```text
~/.proma/agent-workspaces/<workspace-id>/
├── skills/
│   └── rwgj/                    # 本技能包（全局安装）
├── workspace-files/
│   └── .context/                # 工作区级知识沉淀
│       └── note.md              # 架构分析、方案对比
└── <session-id>/
    ├── .context/                # 会话级临时文档
    │   ├── plan/                # 执行计划
    │   └── todo.md              # 任务清单
    └── architecture/            # 项目架构真相源（如果在会话中创建）
```

**关键原则**：
- **能力文件**（本技能包）→ 工作区 skills/ 目录
- **项目架构**（architecture/）→ 项目根目录或会话目录
- **知识沉淀**（分析报告）→ workspace-files/.context/
- **临时文档**（计划、TODO）→ 会话 .context/

##### 快速验证工具增强

本技能包为 Proma 提供了增强的工具脚本包装器：

```bash
# 使用增强版工具（提供进度反馈和友好错误提示）
python shared/scripts/run_with_progress.py validate_architecture.py '验证架构文件' architecture.json
```

特性：
- ✓ 实时进度反馈
- ✓ 友好的错误提示
- ✓ 智能问题诊断
- ✓ 解决方案建议

##### 与 Proma 内置工具协同

| Proma 工具 | 任务架构协同场景 |
|-----------|----------------|
| `mcp__collaboration__delegate_agent` | 创建并行架构验证子会话 |
| `mcp__collaboration__delegate_agents` | 批量创建模块审议子会话 |
| `mcp__automation__create_automation` | 定期架构健康检查 |
| `mcp__proma_cloud__get_credentials` | AI 辅助架构分析 |

##### Proma 最佳实践

1. **工作区级使用**：在同一工作区的多个项目中共享本技能包
2. **知识沉淀**：重要的架构分析输出到 workspace-files/.context/note.md
3. **定时验证**：设置每日自动架构检查任务
4. **协作验证**：复杂项目使用子 Agent 并行验证不同维度

### 5.2 用户使用方式

用户**不需要**直接调用任何子能力层或脚本，只需要：

```text
使用任务架构做 XXX
```

宿主按本次范围读取内部规则与所选专业指南。用户可直接描述要交付的行为、硬约束和希望验证的边界，例如：

```text
使用任务架构设计这个项目的模块边界、依赖方向和接口契约，并记录架构取舍。
使用任务架构把这个功能拆成按依赖执行的任务，写清修改范围和验收责任。
使用任务架构实现这个界面，覆盖处理中、成功、失败和键盘操作，并做实际可用的验收。
使用任务架构排查这个异常，保留复现证据，并用固定预期验证修复。
```

用户无需逐项点名子技能；宿主根据已确认需求和实际工具条件选择，缺少必需证据时报告未验证。

### 5.3 三层执行顺序（核心）

技能采用**薄入口 → 认知 → 物化 → 协议**的固定三段式：

```text
┌──────────────────────────────────────┐
│ 用户需求                              │
└──────────────┬───────────────────────┘
               ↓
   ┌────────[1] project-depth-core────────┐
   │ "想得深"                              │
   │ • 最大主动性设计                        │
   │ • 功能簇展开                            │
   │ • 交互完整性                            │
   │ • 多层递进设计                          │
   │ • 分治设计法                            │
   └──────────────┬───────────────────────┘
                  ↓
   ┌────────[2] architecture-json─────────┐
   │ "落得稳"                              │
   │ • architecture/ 切片目录                │
   │ • 功能树 → 模块树 → 模块详情              │
   │ • 实现清单 / 验证责任                    │
   └──────────────┬───────────────────────┘
                  ↓
   ┌────────[3] agent-protocol (按需)──────┐
   │ "跑得广"                              │
   │ • 跨平台适配                            │
   │ • 硬门禁                               │
   │ • 标准化输出                            │
   │ • 能力降级记录                          │
   └──────────────────────────────────────┘
```

**触发信号**：

| 信号 | 进入哪层 |
|------|----------|
| 模糊需求、新功能、功能深度、交互闭环 | `project-depth-core` |
| 创建/修改 `architecture/` 切片 | `architecture-json` |
| 跨 Agent 使用、门禁、标准化输出 | `agent-protocol` |
| 小命令、概念问答 | **小命令降级**：最小闭环 / 完全跳过 |

### 5.4 工具链使用

技能自带 Python 脚本（数量口径见 §4.5），**工具不可用时按文本规则降级执行**。

**运行环境**：随包脚本使用 Python 3.9+；这是检查工具运行时，被检查项目的语言不受限制。`verify-all.sh` 一键验证需 Git Bash / WSL 环境，也可直接运行 Python 测试。本轮在 Windows 与 Python 3.12.14 的本地运行时验证；仓库 CI 配置中的版本矩阵不等于本轮已经运行的结果。

下列相对脚本路径展示参数用法；实际执行先按 LAYER 的 resolve_tool 规则取完整脚本绝对路径，保持工作目录为调用方项目。包自身回归运行 `bash verify-all.sh --self-test`；项目完整验证运行 `bash "<安装目录>/verify-all.sh" --project "<项目根>"`。默认有受管架构锚点时选择项目模式；仅能力包自身无项目锚点时自动自检。一键项目模式与 gate 使用同一文件盘点语义：实际运行 --all-files --json，声明文件缺失阻断，未登记文件保留原始列表作为提示；不按格式猜业务代码，不将导出的报告、审计文件或可视化自动当作业务实现。输入/返回码与输出矛盾记为 unknown。独立 scan_code_drift CLI 仍把任一种清单偏差返回 1，其清单需要按当前用途解释；以上提示不等于未登记文件内容已通过语义检查。

#### 5.4.1 架构验证类

```bash
python shared/scripts/validate_architecture.py architecture/index.json
python shared/scripts/validate_protocol_semantics.py . --architecture architecture/index.json
python shared/scripts/validate_agent_output.py shared/assets/example-agent-output.json
python scripts/validate_task_architecture_system.py
```

#### 5.4.2 扫描与对比类

```bash
python shared/scripts/scan_code_drift.py . --architecture architecture/index.json --max-items 200
python shared/scripts/diff_architecture.py old.json new.json
python shared/scripts/gate_check.py . --quality-required --json
```

#### 5.4.3 初始化与脚手架类

```bash
# 把单文件 architecture.json 迁移为切片目录
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .
# 初始化新的 architecture/ 目录
python shared/scripts/init_architecture.py --mode init --output .
```

#### 5.4.4 任务姿态与小命令降级

```bash
python shared/scripts/detect_task_posture.py --request "使用任务架构检查当前项目"
python shared/scripts/detect_small_command.py --request "启动项目" --project-root .
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

`detect_small_command.py` 三档判定：完全跳过（概念问答/一次性脚本/纯只读查看）/ 最小闭环（启动项目、运行单条命令、修改某个元素；分**运行类**与**修改类**，修改类才做三重校验）/ 完整流程（新功能、重构、漂移排查）。判定链：复合请求分句 → 区分纯问答/只读与实际操作 → 逐项判定取最严格档位 → 高风险实际操作升档（删除/支付/生产等强制完整流程）→ 受管降级；非受管项目的最小闭环自动降为完全跳过。

#### 5.4.5 顶层 CLI 工具

```bash
python shared/scripts/taskarch_cli.py <子命令> [参数]
# 常用子命令
python shared/scripts/taskarch_cli.py lineage --root .                # 查看版本继承
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树  # 切片查看
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md  # 文档门禁
```

#### 5.4.6 端到端演示（快速看全貌）

```bash
python scripts/demo_project.py               # 临时目录生成受管示例项目，跑通完整验证链
python scripts/demo_project.py --keep demo/  # 保留项目目录便于查看
```

演示流程：生成指针 + 架构 + 代码文件 + 状态文件 → 依次运行 占位符检查 / 架构校验 / 状态查看 / 事中裁判 / 漂移扫描 / 收尾门禁 / 质量红线 / 审计问卷。全部通过返回 0，已接入 `verify-all.sh` 作为端到端回归。

#### 5.4.7 质量红线与独立审计（补格式校验盲区）

格式校验（占位符/状态/结构）无法拦截劣质架构——把导出做成按钮、把后台塞进普通页面都能跑绿。两条补充机制：

```bash
# 自动：质量红线（操作类缺异常路径 / 导出类缺安全信号 / 空壳模块 / 状态机冲突）
python shared/scripts/check_quality_redlines.py architecture/index.json
# 真实项目存在合理例外时，声明豁免并记录理由（无理由豁免会提示）
python shared/scripts/check_quality_redlines.py architecture/index.json \
  --exempt "功能树.导出数据" --exempt-reason "内部工具，权限由上层统一管控"

# 人工/LLM：独立审计问卷（10 问语义质量，由第二个会话填写，可留痕归档）
python shared/scripts/audit_architecture.py generate architecture/index.json --output audit-report.json
python shared/scripts/audit_architecture.py report audit-report.json
# q1..q10 各一次；yes/no 需非空字符串证据；na 需证据或不适用原因。
# 生成模板成功不代表审计通过；任一 no 返回 1。
```

原则：**质量红线拦截明显坏，独立审计记录质量判断，最终权威永远是人的工程判断。验证全绿 ≠ 架构正确。**

#### 5.4.8 架构可视化（单向渲染，只读不写）

把架构真相源渲染成人类可读产物——依赖图、功能树、进度、模块摘要、数据拓扑、质量标注：

```bash
# Mermaid Markdown 报告（GitHub 原生渲染，可直接贴 PR/README/审计报告）
python shared/scripts/render_architecture.py architecture/index.json

# 单文件零依赖交互版（浏览器打开：SVG 依赖图/可折叠功能树/模块详情面板）
python shared/scripts/render_architecture.py architecture/index.json --format html --output arch.html

# 结构化 JSON（供其他工具消费）
python shared/scripts/render_architecture.py architecture/index.json --format json --output arch.json

# 大项目截断保护
python shared/scripts/render_architecture.py architecture/index.json --max-nodes 40
```

**铁律（单向渲染）**：`architecture/index.json` + 切片是唯一真相源；可视化产物是**派生视图**，随时可重新生成，**禁止反向编辑 JSON**。任何架构修改仍走命令链（/修改架构 → JSON → 校验）。

#### 5.4.9 专业能力的规划、读取与核验

在调用方项目中，先根据实际需求创建本次语境，再由 `resolve_tool.py` 解析以下工具的完整路径。语境与计划保存在调用方的 `architecture/capabilities/`；默认 catalog 会选择适用的最小资料。

```text
python "<plan_capabilities_path>" --project "<项目根>" --context "<项目根>/architecture/capabilities/context.json" --output "<项目根>/architecture/capabilities/plan.json"
# 宿主实际读取 plan 中的 read_files，执行所选专业任务，并回写架构与使用记录。
python "<check_capability_usage_path>" "<项目根>" --plan architecture/capabilities/plan.json --usage architecture/capabilities/usage.json --context architecture/capabilities/context.json --json
python "<check_subskill_sources_path>" "<能力包根>" --json
```

阶段或输入变化时使用 `--previous "<旧计划.json>"` 显示选择变化，并保留未解决的必需能力与风险。已核验完成的能力可在新语境中登记到 `resolved_capabilities`（或 `已完成能力`）；这项声明只更新规划约束，实际退出依据仍须核验。不要覆盖旧失败或 unknown 记录。

规划成功表示资料可按计划读取；使用核验检查当前记录、作用域与回写对账；来源核验检查本地版本锁、文件和目录绑定。它们分别报告各自范围，完整实现交付继续遵循 [通用质量协议](shared/references/universal-quality.md) 和 `gate_check --quality-required`。语境示例、实际使用模板和输入条件见 [专业能力索引](shared/references/capability-index.md) 与 [编程子技能说明](shared/references/programming-subskills.md)。

#### 5.4.10 子技能接入验证记录（2026-10-04）

以下记录对应本次接入快照；当前测试规模仍由 §4.5 的对账工具动态盘点。

- 完整回归运行 682 项：680 项通过，2 项因 Windows 符号链接权限跳过；能力体系检查无错误、无警告。
- 本地来源核验覆盖十二项新能力、72 次文件检查；接入时检查的 424 个相对路径引用均有效。
- 独立配额工具演练实际读取七份 GUIDE：设计三项、规划一项、验证三项；14 个固定业务场景与两组补充检查通过。
- 真实浏览器完成八项操作观察，覆盖键盘提交、处理中状态、幂等、冲突、输入错误、超额、取消与焦点恢复；控制台无警告或错误。未覆盖读屏、窄视口、其他浏览器和原生桌面 UI。
- 故意改坏取消逻辑、产物回写值及缺失使用记录的负例分别被失败或 unknown 拦截，原始预期与失败证据保留。实际全局安装的使用检查器对最终记录通过 36 条检查。

这些结果分别验证当前包、选定案例和当前安装的检查范围；骨架、使用记录或文件哈希通过不证明架构最优、全部业务语义正确或所有语言运行工具可用。浏览器观察按宿主操作与 review 证据记录，真实命令执行另附 execution 收据。

### 5.5 平台适配说明

技能通过 `shared/adapters/` 屏蔽平台差异：

| 平台 | 适配文件 | 关键差异 |
|------|----------|----------|
| Claude Code | `shared/adapters/claude.md` | 工具调用格式、Skill 触发 |
| Codex | `shared/adapters/codex.md` | 插件模型、沙箱 |
| Trae | `shared/adapters/trae.md` | 远程工作流、上下文 |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | 标准 stdin/stdout 协议 |

**适配原则**：所有平台读同一份 `shared/references/`，平台差异只写在 `adapters/`，**禁止维护分叉规则**。

### 5.6 共享资源定位

共享文件按**优先级**解析：

```text
1. 当前项目根目录的 skills/ 或 shared/  ← 最高优先级
2. 全局技能安装目录的 skills/ 和 shared/  ← 回退
3. 本技能仓库的 shared/legacy/  ← 仅历史参考
```

**注意**：
- 不得把项目状态、恢复点、变更记录写入**全局**技能目录
- 子能力层中的 `../../shared/` 路径按同一规则解析

### 5.7 典型工作流示例

#### 5.7.1 新建项目并初始化

```text
用户："使用任务架构做一个 TODO 应用"
```

执行流程：
1. 先经 LAYER 锁定范围，`project-depth-core` 展开本次目标成立所需的功能簇；提醒、分类、同步等按实际需求评估
2. `architecture-json` 生成 `architecture/` 切片目录（功能树、模块树、模块详情...）
3. 按用户已有授权进入逐块实现；只在缺少必需信息或新增范围时确认

#### 5.7.2 修改已有功能

```text
用户："用任务架构给 TODO 加个标签功能"
```

执行流程：
1. `project-depth-core` 智能关联：标签 → 模块（数据/页面/任务/搜索）→ 测试
2. `architecture-json` 更新 `architecture/features/` 和 `architecture/modules/`
3. 触发 `scan_code_drift.py` 检查一致性

#### 5.7.3 跨平台输出

```text
用户："用任务架构做 XXX，把结果导出成 Claude 能读的格式"
```

执行流程：
1. 走完前两层
2. `agent-protocol` 读取 `claude.md` 适配，输出标准契约

### 5.8 最佳实践

1. **薄入口优先**：所有需求先说"使用任务架构做 XXX"，让系统自己路由
2. **强制切片**：旧单文件 `architecture.json` 第一步必须迁移为 `architecture/`
3. **工具优先**：工具可用时优先跑工具，工具不可用时按文本规则降级
4. **平台一致**：所有 Agent 读同一份 `shared/`，平台差异只写在 `adapters/`
5. **受控主动性**：Agent 主动补全时，必须遵守"不破坏用户显式约束"
6. **完成前自检**：实现完成后必须跑 `check_regression_assertions.py` 验证

### 5.9 故障排除

| 问题 | 解决 |
|------|------|
| Agent 不识别技能 | 检查 SKILL.md 的 YAML frontmatter `name` 和 `description` |
| 工具运行报错 | 先 `python <script> --help` 看参数；工具失败可按文本规则降级 |
| 架构文件不一致 | 跑 `python shared/scripts/validate_architecture.py architecture/index.json` 看具体错误 |
| 代码和架构 drift | 跑 `python shared/scripts/scan_code_drift.py` 看具体 drift 列表 |
| 跨平台输出异常 | 读 `shared/adapters/<platform>.md` 适配说明 |
| 子能力层路径找不到 | 检查 `../../shared/` 解析：项目根目录 vs 全局目录 |

### 5.10 辅助参考链接

- 快速上手：`shared/references/quickstart.md`
- 命令速查：`shared/references/commands-cheatsheet.md`
- 命令工作流：`shared/references/commands-workflows.md`
- 21 项校验清单与硬约束门禁：`shared/references/validation-checklist.md`
- 能力索引：`shared/references/capability-index.md`
- 切片规范：`shared/references/json-sharding.md`
- 上下文恢复：`shared/references/context-recovery.md`
- 执行模板：`shared/references/execution-templates.md`
- 原理卡片：`shared/references/principles-card.md`

---

## 六、维护说明

### 6.1 修改流程

```bash
# 1. 编辑文件（在根目录）
# 2. 暂存
git add -A
# 3. 提交（建议遵循 Conventional Commits）
git commit -m "feat|fix|chore|docs: ..."
# 4. 推送
git push origin main
```

### 6.2 添加新能力

| 类型 | 位置 |
|------|------|
| 内部子能力层 | `skills/<name>/<职责文件>.md`，由现有路由按需链接，不使用新的 `SKILL.md` 魔法入口 |
| 专业能力注册 | 项目的能力索引/最小catalog；宿主已安装技能按元数据接入，不复制成内部宿主入口 |
| 参考文档 | `shared/references/<name>.md` |
| 工具脚本 | `shared/scripts/<name>.py` |
| Schema | `shared/assets/schema/<name>.schema.json` |
| 平台适配 | `shared/adapters/<platform>.md` |
| 资产模板 | `shared/assets/<name>.json` |

扩展内部层与接入已有外部技能是两种操作；保持根 `SKILL.md` 为本包唯一入口。新增能力先明确触发、作用域、输入、产出、证据与回写，按 `capability-index.md` 核验；名称、描述与社区热度不能替代实际能力验证。

### 6.3 不要做

- ✗ 在本仓库存项目业务状态（真相源在调用方）
- ✗ 把子能力层细则复制到总入口
- ✗ 让 `agent-protocol` 抢占 `project-depth-core` 入口优先级
- ✗ 维护分叉规则（所有 Agent 读同一份）

---

## 七、链接

- **Agent 入口**：`SKILL.md`（薄入口）/ `AGENT-USAGE.md`（通用入口）
- **架构真相源**：`architecture.json` → `architecture/index.json`
- **共享资源**：`shared/references/`、`shared/scripts/` + `scripts/`、`shared/adapters/`、`shared/assets/`（数量口径见 §4.5）
