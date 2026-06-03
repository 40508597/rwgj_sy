# 任务架构（rwgj）

> 任务架构通用智能体能力包，全局薄入口，承载任务架构规则、能力定义与共享工具。
> 让 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、CLI Agent 与自研 Agent 按同一套任务架构协议工作。

---

## 一、仓库简介

- **角色**：薄入口技能包，承载任务架构规则与共享工具
- **使用方**：Codex / Claude Code / Trae / Cursor / Windsurf / Cline / Continue / CLI Agent / 自研 Agent
- **核心特性**：真相源分离（能力在仓库，项目状态在调用方 `architecture/`）、跨平台一致（差异只写在 `shared/adapters/`）
- **远程仓库**：https://github.com/405089597/rwgj_sy.git

---

## 二、版本演进

本仓库以 **17 个历史版本** + 当前 rwgj 入口为时间线，按目录内文件夹的 mtime 顺序**逐个 commit** 形成完整演进链。

完整 commit 历史：`git log --reverse --oneline`（共 22 个 commit）

**版本阶段**：
- **任务架构 1.0 ~ 1.1.9**（11 个版本）：早期演进
- **任务架构 1.2 / 1.3**：动态任务姿态、跨智能体协议
- **任务架构-通用智能体版**：平台无关化变体
- **任务架构-能力体系 1.0 / 1.1.1 / 1.1.2**：能力体系化（1.1.2 = 现行入口的前身）
- **rwgj (current)**：薄入口化、组织化

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
├── .source.json                # 技能来源元数据
├── README.md                   # 本文件（仓库门面 + 完整能力 + 详细使用）
├── SKILL.md                    # Agent 薄入口
├── AGENT-USAGE.md              # Agent 通用入口
├── architecture.json           # 架构真相源指针
├── architecture/               # 架构切片（data/features/modules/pages/tasks/index）
├── docs/                       # 设计文档
│   ├── capability-map.md       # 能力地图
│   ├── mcp-tools.md            # MCP 工具清单
│   ├── regression-assertions.md
│   └── version-lineage.md
├── optional/                   # 可选组件（MCP 服务）
├── scripts/                    # 顶层验证脚本
├── shared/                     # 共享资源（Agent 加载）
│   ├── adapters/               # 平台适配（4 个）
│   ├── assets/                 # 资产模板 + Schema
│   ├── legacy/                 # 历史 SKILL 归档
│   ├── references/             # 参考文档（21 篇）
│   └── scripts/                # 工具脚本（10 个）
└── skills/                     # 子技能（4 个）
    ├── task-architecture/      # 总入口
    ├── project-depth-core/     # 主动理解内核
    ├── architecture-json/      # 架构物化层
    └── agent-protocol/         # 外围协议层
```

---

## 四、技能能力

### 4.1 能力地图（5 大类）

#### 4.1.1 注意力保护区（核心能力 3 项）

| 能力 | 子技能 | 目标 |
|------|--------|------|
| 主动理解 | `project-depth-core` | 想得深 |
| 物化架构 | `architecture-json` | 落得稳 |
| 外围协议 | `agent-protocol` | 跑得广 |

#### 4.1.2 共享资源（6 类）

| 资源类型 | 数量 | 路径 |
|----------|------|------|
| 参考文档 | 21 篇 | `shared/references/` |
| 脚本工具 | 10 个 | `shared/scripts/` + `scripts/` |
| 资产模板 | 7 个 | `shared/assets/` |
| 平台适配 | 4 个 | `shared/adapters/` |
| 历史档案 | 3 个 | `shared/legacy/` |
| Schema | 2 个 | `shared/assets/schema/` |

#### 4.1.3 工具能力（10 个 CLI）

| 工具 | 类型 | 主要功能 |
|------|------|----------|
| `validate_architecture.py` | 验证 | 校验 architecture.json 完整性 |
| `validate_protocol_semantics.py` | 验证 | 协议层语义回归 |
| `validate_agent_output.py` | 验证 | Agent 输出契约一致性 |
| `validate_task_architecture_system.py` | 验证 | 整体系统（顶层入口） |
| `scan_code_drift.py` | 扫描 | 代码与架构 drift 检测 |
| `diff_architecture.py` | 对比 | 两个 architecture.json 差异 |
| `gate_check.py` | 门禁 | 硬门禁规则检查 |
| `init_architecture.py` | 初始化 | 单文件迁移 / 新建切片 |
| `detect_task_posture.py` | 姿态 | 任务姿态分类（dynamic/linear/reactive） |
| `check_regression_assertions.py` | 回归 | 21 项回归断言 |
| `taskarch_cli.py` | 聚合 | 顶层 CLI（lineage/slice/gate-file 等） |

#### 4.1.4 平台适配（4 个）

| 平台 | 适配文件 | 状态 |
|------|----------|------|
| Claude Code | `shared/adapters/claude.md` | ✓ |
| Codex | `shared/adapters/codex.md` | ✓ |
| Trae | `shared/adapters/trae.md` | ✓ |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | ✓ |

> 适配层**只写差异**，**不复制规则**。

### 4.2 子技能详细说明

#### 4.2.1 `task-architecture` — 总入口

- **职责**：薄路由，不承载完整规则
- **加载时机**：所有用户需求的第一站
- **关键能力**：决定是否进入完整三层流程
- **不做**：不直接写代码、不展开业务细节

#### 4.2.2 `project-depth-core` — 主动理解内核

- **职责**：把模糊需求变成清晰架构
- **核心机制**（5 大）：
  1. **最大主动性设计**：主动补全安全、日志、错误处理、测试、部署
  2. **功能簇展开**：菜单栏不只是横条，导出不只是按钮
  3. **交互完整性**：操作必须有"请求/处理中/成功/失败/异常恢复"
  4. **多层递进设计**：全景 → 骨架 → 逐块 → 集成
  5. **分治设计法**：大功能拆小块，每块让不熟悉项目的人也能独立实现
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

### 4.3 参考文档矩阵（21 篇）

按主题分组：

| 类别 | 文档 | 内容 |
|------|------|------|
| 主动理解 | `function-clusters.md` | 功能簇展开与停止规则 |
| 主动理解 | `interaction-completeness.md` | 交互闭环 |
| 主动理解 | `progressive-decomposition.md` | 多层递进设计 |
| 主动理解 | `splitting-guide.md` | 拆分粒度与停止规则 |
| 主动理解 | `association-and-priority.md` | 影响范围、关联、优先级 |
| 主动理解 | `capability-index.md` | 专业能力路由（UI/测试/安全/性能/部署/文档）|
| 主动理解 | `principles-card.md` | 原理卡片与速查 |
| 架构物化 | `schemas.md` | JSON 字段、中文化规范、四层读取 |
| 架构物化 | `commands-workflows.md` | 5 个命令、创建/分析/修改/追加/校验 |
| 架构物化 | `validation-checklist.md` | 21 项一致性校验 |
| 架构物化 | `json-sharding.md` | 强制切片目录 |
| 协议适配 | `universal-agent-protocol.md` | 跨 Agent 通用协议 |
| 协议适配 | `module-agent-protocol.md` | 虚拟模块审议 |
| 协议适配 | `hard-gates.md` | 硬约束门禁 |
| 协议适配 | `agent-output-contract.md` | 标准化输出契约 |
| 协议适配 | `dynamic-posture-context.md` | 动态姿势语境 |
| 工作流 | `quickstart.md` | 快速上手 |
| 工作流 | `commands-cheatsheet.md` | 命令速查 |
| 工作流 | `context-recovery.md` | 上下文恢复 |
| 工作流 | `execution-templates.md` | 执行模板 |
| 工作流 | `task-posture.md` | 任务姿态 |

### 4.4 能力边界

**明确不做的**：
- ✗ **不**做代码实现的"中央调度"
- ✗ **不**在技能目录持久化项目业务状态
- ✗ **不**复制子技能细则到总入口
- ✗ **不**让 `agent-protocol` 抢占 `project-depth-core` 入口
- ✗ **不**做功能簇展开的"中央判断"（这是认知层职责）
- ✗ **不**维护分叉规则（所有 Agent 读同一份）

**工具降级策略**：工具不可用时按文本规则降级执行，并在验证证据中记录"未运行原因"。

**性能与规模**：
- 工具脚本运行时间通常 < 5 秒（10K 行代码内）
- 切片目录支持单文件 1MB 以内
- 超过此规模建议分模块使用

### 4.5 技术指标

| 指标 | 数值 |
|------|------|
| 子技能数 | 4 |
| 参考文档数 | 21 |
| 工具脚本数 | 10 |
| 平台适配数 | 4 |
| 设计文档数 | 4 |
| Schema 数 | 2 |
| 资产模板数 | 7 |
| 历史归档 | 3 |
| 顶层入口文件 | 3（SKILL.md / AGENT-USAGE.md / architecture.json） |
| 总文件数 | ~80 |

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
| 一致性 | 人工 review | 工具自动验证（21 项） |
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
# 1. 把整个目录（除 .git/）复制到项目根目录
cp -r <rwgj-源目录>/<项目根>/   # Windows: xcopy /E
# 注：复制时排除 .git/、.source.json（如果不需要追溯来源）

# 2. 告诉 Agent
#    "读取 AGENT-USAGE.md，使用任务架构处理本项目。"
```

#### 两种模式对比

| 维度 | 全局安装 | 项目级复制 |
|------|----------|------------|
| 共享能力更新 | 一次更新，多项目生效 | 每个项目单独更新 |
| 项目真相源（architecture/）| 每个项目独立 | 跟随项目 |
| 适配层差异（adapters/）| 跟随全局 | 跟随项目（可定制）|
| 适合 | 标准化工作流 | 项目特化需求 |

### 5.2 用户使用方式

用户**不需要**直接调用任何子技能或脚本，只需要：

```text
使用任务架构做 XXX
```

技能会自动按需加载三层。用户的语言越具体、目标越明确，技能的效果越好。

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
| 简单命令、概念问答 | **不进入**完整流程 |

### 5.4 工具链使用

技能自带 10 个 Python 工具，**工具不可用时按文本规则降级执行**。

#### 5.4.1 架构验证类

```bash
python shared/scripts/validate_architecture.py architecture.json
python shared/scripts/validate_protocol_semantics.py
python shared/scripts/validate_agent_output.py
python scripts/validate_task_architecture_system.py
```

#### 5.4.2 扫描与对比类

```bash
python shared/scripts/scan_code_drift.py . --architecture architecture.json --max-items 200
python shared/scripts/diff_architecture.py old.json new.json
python shared/scripts/gate_check.py
```

#### 5.4.3 初始化与脚手架类

```bash
# 把单文件 architecture.json 迁移为切片目录
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .
# 初始化新的 architecture/ 目录
python shared/scripts/init_architecture.py --mode init --output .
```

#### 5.4.4 任务姿态与回归

```bash
python shared/scripts/detect_task_posture.py
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

#### 5.4.5 顶层 CLI 工具

```bash
python shared/scripts/taskarch_cli.py <子命令> [参数]
# 常用子命令
python shared/scripts/taskarch_cli.py lineage --root .                # 查看版本继承
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树  # 切片查看
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md  # 文档门禁
```

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
- 子技能中的 `../../shared/` 路径按同一规则解析

### 5.7 典型工作流示例

#### 5.7.1 新建项目并初始化

```text
用户："使用任务架构做一个 TODO 应用"
```

执行流程：
1. `project-depth-core` 展开功能簇（增删改查 + 状态 + 提醒 + 分类 + 同步...）
2. `architecture-json` 生成 `architecture/` 切片目录（功能树、模块树、模块详情...）
3. 用户确认后进入实现

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
| architecture.json 不一致 | 跑 `python shared/scripts/validate_architecture.py architecture.json` 看具体错误 |
| 代码和架构 drift | 跑 `python shared/scripts/scan_code_drift.py` 看具体 drift 列表 |
| 跨平台输出异常 | 读 `shared/adapters/<platform>.md` 适配说明 |
| 子技能路径找不到 | 检查 `../../shared/` 解析：项目根目录 vs 全局目录 |

### 5.10 辅助参考链接

- 快速上手：`shared/references/quickstart.md`
- 命令速查：`shared/references/commands-cheatsheet.md`
- 命令工作流：`shared/references/commands-workflows.md`
- 21 项校验清单：`shared/references/validation-checklist.md`
- 能力索引：`shared/references/capability-index.md`
- 切片规范：`shared/references/json-sharding.md`
- 硬门禁：`shared/references/hard-gates.md`
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
| 新 Skill | `skills/<name>/SKILL.md` |
| 参考文档 | `shared/references/<name>.md` |
| 工具脚本 | `shared/scripts/<name>.py` |
| Schema | `shared/assets/schema/<name>.schema.json` |
| 平台适配 | `shared/adapters/<platform>.md` |
| 资产模板 | `shared/assets/<name>.json` |

### 6.3 不要做

- ✗ 在本仓库存项目业务状态（真相源在调用方）
- ✗ 把子技能细则复制到总入口
- ✗ 让 `agent-protocol` 抢占 `project-depth-core` 入口优先级
- ✗ 维护分叉规则（所有 Agent 读同一份）

---

## 七、链接

- **远程仓库**：https://github.com/405089597/rwgj_sy.git
- **Agent 入口**：`SKILL.md`（薄入口）/ `AGENT-USAGE.md`（通用入口）
- **架构真相源**：`architecture.json` → `architecture/index.json`
- **共享资源**：`shared/references/`（21 篇）、`shared/scripts/`（10 个）、`shared/adapters/`（4 个）
