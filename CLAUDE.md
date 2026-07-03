# 任务架构（rwgj）项目知识库

## 项目概述

这是一个任务架构通用智能体能力包，为 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue 等 AI Agent 提供统一的任务架构能力。

**核心特性**：
- 真相源分离：能力在本仓库，项目状态在调用方的 `architecture/` 目录
- 跨平台一致：平台差异只写在 `shared/adapters/` 中
- 薄入口设计：总入口 SKILL.md 只做路由，不承载完整规则

## 目录结构规范

```text
任务架构/
├── SKILL.md                    # 全局薄入口（给 Agent 的技能触发点）
├── AGENT-USAGE.md              # Agent 通用入口说明
├── README.md                   # 项目说明文档（给人看）
├── CONTRIBUTING.md             # 贡献指南
├── skills/                     # 4 个子能力层（单一技能入口）
│   ├── task-architecture/      # 路由层 LAYER.md
│   ├── project-depth-core/     # 主动理解内核 CORE.md
│   ├── architecture-json/      # 架构物化层 SCHEMA.md
│   └── agent-protocol/         # 外围协议层 PROTOCOL.md
├── shared/                     # 共享资源（Agent 加载）
│   ├── references/             # 21 篇参考文档
│   ├── scripts/                # 11 个工具脚本
│   ├── adapters/               # 4 个平台适配器
│   ├── assets/                 # 资产模板 + Schema
│   └── legacy/                 # 历史 SKILL 归档
├── docs/                       # 设计文档
└── scripts/                    # 顶层验证脚本
```

## 关键原则

### 1. 真相源分离
- **本仓库**：承载能力定义、规则、工具、参考文档
- **调用方项目**：承载业务状态（`architecture/` 目录）
- **禁止**：在本仓库存储项目业务状态、恢复点、变更记录

### 2. 路径解析规则
共享文件按以下优先级定位：
1. 当前项目根目录的 `skills/` 或 `shared/`（最高优先级）
2. 全局技能安装目录的 `skills/` 和 `shared/`（回退）
3. 本技能仓库的 `shared/legacy/`（仅历史参考）

子能力层中的 `../../shared/` 路径按同一规则解析。

### 3. 三层执行顺序（固定）
```text
用户需求
  ↓
[1] project-depth-core（想得深）
  • 最大主动性设计
  • 功能簇展开
  • 交互完整性
  • 多层递进设计
  ↓
[2] architecture-json（落得稳）
  • architecture/ 切片目录
  • 功能树 → 模块树 → 模块详情
  • 实现清单 / 验证责任
  ↓
[3] agent-protocol（跑得广，按需）
  • 跨平台适配
  • 硬门禁
  • 标准化输出
```

## 工具脚本使用

### 强制执行三件套（F+B+C）

**核心哲学**：从"教 LLM 该怎么做"变成"让 LLM 做不到就走不下去"

#### F. 占位符机制（让缺失可见）

```bash
# 检测架构中的占位符
python shared/scripts/check_placeholders.py architecture/index.json

# 严格模式（任何占位符都报错）
python shared/scripts/check_placeholders.py architecture/index.json --strict
```

**机制**：
- 使用 `architecture-template-with-placeholders.json` 创建架构
- 所有必填字段包含 `__待填__` 占位符
- 占位符分级：核心（阻塞）/重要（警告）/可选（提示）
- 核心占位符未清空时返回错误码 1

**强制点**：修改架构后第一步检查，完成前自检硬性要求

#### B. 进度状态文件（让进度可查）

```bash
# 初始化状态文件
python shared/scripts/manage_state.py init --project-name "项目名"

# 查看当前进度
python shared/scripts/manage_state.py show

# 更新阶段状态
python shared/scripts/manage_state.py update 功能树 in_progress
python shared/scripts/manage_state.py update 功能树 completed --note "已完成功能树展开"

# 添加阻塞项
python shared/scripts/manage_state.py add-blocker "等待用户确认XX需求"
```

**机制**：
- 标准 10 个阶段追踪
- 每个阶段：pending/in_progress/completed/skipped
- 自动计算完成度和必需阶段完成率
- 自动生成下一步行动指令

**强制点**：LAYER.md 第一动作读状态，每完成一个阶段更新

#### C. 事中验证裁判（让缺失被拦截）

```bash
# 运行事中裁判（三重检查：占位符 + 状态 + 架构）
python shared/scripts/judge_progress.py architecture/index.json

# JSON 输出
python shared/scripts/judge_progress.py architecture/index.json --json
```

**机制**：
- 综合三重检查结果
- 判定能否继续（can_proceed: true/false）
- 输出强指令式下一步行动
- 返回码：0=可继续，1=有阻塞

**强制点**：每个阶段完成后检查，裁判说不能继续时必须修复

#### 强制触发检测（让技能不被遗漏）

```bash
# 检测项目是否应该使用任务架构
python shared/scripts/detect_should_trigger.py
```

**机制**：
- 检测 architecture.json/architecture/ 目录
- 检测多模块结构、代码规模
- 给出明确的触发建议

**强制点**：LAYER.md 规定未明确提及任务架构时必须先检测

### 验证类工具
```bash
# 验证架构完整性
python shared/scripts/validate_architecture.py architecture.json

# 验证协议语义
python shared/scripts/validate_protocol_semantics.py

# 验证 Agent 输出
python shared/scripts/validate_agent_output.py

# 验证整体系统
python scripts/validate_task_architecture_system.py
```

### 扫描与对比类
```bash
# 扫描代码与架构偏移
python shared/scripts/scan_code_drift.py . --architecture architecture.json --max-items 200

# 对比架构差异
python shared/scripts/diff_architecture.py old.json new.json

# 门禁检查
python shared/scripts/gate_check.py
```

### 初始化类
```bash
# 迁移单文件到切片目录
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .

# 初始化新的 architecture/ 目录
python shared/scripts/init_architecture.py --mode init --output .
```

### 回归与姿态检测
```bash
# 任务姿态检测
python shared/scripts/detect_task_posture.py

# 回归断言检查
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

### 顶层 CLI
```bash
# 查看版本继承
python shared/scripts/taskarch_cli.py lineage --root .

# 切片查看
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树

# 文档门禁
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md
```

## 工具降级策略

**原则**：工具不可用时按文本规则降级执行，不中断流程。

降级时必须：
1. 按文本规则手动执行验证逻辑
2. 在验证证据中记录"未运行原因"
3. 告知用户工具未运行的情况

## 平台适配说明

| 平台 | 适配文件 | 关键差异 |
|------|----------|----------|
| Claude Code | `shared/adapters/claude.md` | 工具调用格式、Skill 触发 |
| Codex | `shared/adapters/codex.md` | 插件模型、沙箱 |
| Trae | `shared/adapters/trae.md` | 远程工作流、上下文 |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | stdin/stdout 协议 |

**适配原则**：所有平台读同一份 `shared/references/`，禁止维护分叉规则。

## Proma Agent 特定集成

### 安装方式
```bash
# 全局安装（推荐）
# 将本目录复制到 Proma 工作区的 skills 目录
cp -r <本目录> ~/.proma/agent-workspaces/<workspace-id>/skills/rwgj/

# 项目级安装
# 将本目录复制到项目根目录
cp -r <本目录> <项目根>/rwgj/
```

### 触发方式
在 Proma Agent 对话中：
```text
使用任务架构做 XXX
```

### 与 Proma 协作工具集成
- 可结合 `mcp__collaboration__*` 工具创建子 Agent 进行并行验证
- 可结合 `mcp__automation__*` 工具创建定期架构验证任务

## 常见问题排查

### 问题：Agent 不识别技能
**解决**：检查 SKILL.md 的 YAML frontmatter `name` 和 `description` 是否正确

### 问题：工具运行报错
**解决**：
1. 先运行 `python <script> --help` 查看参数
2. 工具失败可按文本规则降级执行

### 问题：architecture.json 不一致
**解决**：运行 `python shared/scripts/validate_architecture.py architecture.json` 查看具体错误

### 问题：代码和架构 drift
**解决**：运行 `python shared/scripts/scan_code_drift.py` 查看具体 drift 列表

### 问题：跨平台输出异常
**解决**：查阅 `shared/adapters/<platform>.md` 适配说明

## 参考文档索引

### 主动理解类（7 篇）
- `function-clusters.md` - 功能簇展开与停止规则
- `interaction-completeness.md` - 交互闭环
- `progressive-decomposition.md` - 多层递进设计
- `splitting-guide.md` - 拆分粒度与停止规则
- `association-and-priority.md` - 影响范围、关联、优先级
- `capability-index.md` - 专业能力路由
- `principles-card.md` - 原理卡片与速查

### 架构物化类（4 篇）
- `schemas.md` - JSON 字段、中文化规范、四层读取
- `commands-workflows.md` - 5 个命令、工作流
- `validation-checklist.md` - 21 项一致性校验
- `json-sharding.md` - 强制切片目录

### 协议适配类（5 篇）
- `universal-agent-protocol.md` - 跨 Agent 通用协议
- `module-agent-protocol.md` - 虚拟模块审议
- `hard-gates.md` - 硬约束门禁
- `agent-output-contract.md` - 标准化输出契约
- `dynamic-posture-context.md` - 动态姿势语境

### 工作流类（5 篇）
- `quickstart.md` - 快速上手
- `commands-cheatsheet.md` - 命令速查
- `context-recovery.md` - 上下文恢复
- `execution-templates.md` - 执行模板
- `task-posture.md` - 任务姿态

## 维护规范

### 修改流程
```bash
git add -A
git commit -m "feat|fix|chore|docs: ..."
git push origin main
```

### 添加新能力

| 类型 | 位置 |
|------|------|
| 新 Skill | `skills/<name>/SKILL.md` |
| 参考文档 | `shared/references/<name>.md` |
| 工具脚本 | `shared/scripts/<name>.py` |
| Schema | `shared/assets/schema/<name>.schema.json` |
| 平台适配 | `shared/adapters/<platform>.md` |
| 资产模板 | `shared/assets/<name>.json` |

### 禁止操作
- ✗ 在本仓库存项目业务状态
- ✗ 把子能力层细则复制到总入口
- ✗ 让 `agent-protocol` 抢占 `project-depth-core` 入口优先级
- ✗ 维护分叉规则（所有 Agent 读同一份）

## 版本演进历史

本仓库以 17 个历史版本 + 当前 rwgj 入口为时间线，形成完整演进链。

**能力继承关系**：
- **1.0 / 1.1** → 最大主动性、功能簇、交互完整性 → `project-depth-core`
- **1.1.2** → 主入口瘦身、references 分拆 → 总入口 + `shared/references/`
- **1.1.5 / 1.1.6** → 功能树、模块树、切片意识 → `architecture-json`
- **1.1.7 / 1.1.8** → validate/scan/diff/init 工具链 → `shared/scripts/`
- **1.1.9** → 受控主动性、防扁平化 → `project-depth-core` + `architecture-json`
- **1.2** → 动态任务姿态建议器 → `shared/scripts/` + 辅助参考
- **1.3** → 跨智能体协议、适配层 → `agent-protocol`

**继承原则**：
```text
1.1 做认知内核
1.2 做结构落位
1.3 做协议外壳
```

## 技术指标

- 子能力层数：4
- 参考文档数：21
- 工具脚本数：11（shared/scripts: 11 个）
- 平台适配数：4
- 设计文档数：3
- Schema 数：2
- 资产模板数：7
- 历史归档：3

## 性能与规模

- 工具脚本运行时间：通常 < 5 秒（10K 行代码内）
- 切片目录支持：单文件 1MB 以内
- 超过此规模建议：分模块使用

## 快速参考

**给人看的文档**：
- 快速上手：`shared/references/quickstart.md`
- 命令速查：`shared/references/commands-cheatsheet.md`

**给 Agent 的入口**：
- 全局入口：`SKILL.md`
- 通用入口：`AGENT-USAGE.md`

**重要链接**：
- GitHub 仓库：https://github.com/40508597/rwgj_sy
- 许可协议：MIT License
