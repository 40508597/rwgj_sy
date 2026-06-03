# 任务架构（rwgj）— 详细使用说明

> 本文档面向**使用者**（开发者、智能体集成者），详细说明如何在不同场景下使用本技能。

---

## 一、安装与部署

### 1.1 全局安装模式（推荐）

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

### 1.2 项目级复制模式

适用场景：项目需要隔离的能力定义，或离线/无网络环境。

```bash
# 1. 把整个目录（除 .git/）复制到项目根目录
cp -r <rwgj-源目录>/<项目根>/   # Windows: xcopy /E
# 注：复制时排除 .git/、.source.json（如果不需要追溯来源）

# 2. 告诉 Agent
#    "读取 AGENT-USAGE.md，使用任务架构处理本项目。"
```

### 1.3 两种模式对比

| 维度 | 全局安装 | 项目级复制 |
|------|----------|------------|
| 共享能力更新 | 一次更新，多项目生效 | 每个项目单独更新 |
| 项目真相源（architecture/）| 每个项目独立 | 跟随项目 |
| 适配层差异（adapters/）| 跟随全局 | 跟随项目（可定制）|
| 适合 | 标准化工作流 | 项目特化需求 |

---

## 二、用户使用方式

用户**不需要**直接调用任何子技能或脚本，只需要：

```text
使用任务架构做 XXX
```

技能会自动按需加载三层。用户的语言越具体、目标越明确，技能的效果越好。

---

## 三、三层执行顺序（核心）

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

---

## 四、工具链使用

技能自带 10 个 Python 工具，**工具不可用时按文本规则降级执行**。

### 4.1 架构验证类

```bash
# 验证 architecture.json 完整性（最常用）
python shared/scripts/validate_architecture.py architecture.json

# 验证协议语义回归
python shared/scripts/validate_protocol_semantics.py

# 验证 Agent 标准输出契约
python shared/scripts/validate_agent_output.py

# 验证整体系统（顶层入口）
python scripts/validate_task_architecture_system.py
```

### 4.2 扫描与对比类

```bash
# 扫描代码与架构的 drift（最常用）
python shared/scripts/scan_code_drift.py . --architecture architecture.json --max-items 200

# 对比两个 architecture.json 的差异
python shared/scripts/diff_architecture.py old.json new.json

# 门禁检查
python shared/scripts/gate_check.py
```

### 4.3 初始化与脚手架类

```bash
# 把单文件 architecture.json 迁移为切片目录
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .

# 初始化新的 architecture/ 目录
python shared/scripts/init_architecture.py --mode init --output .
```

### 4.4 任务姿态与回归

```bash
# 检测任务姿态（dynamic / linear / reactive）
python shared/scripts/detect_task_posture.py

# 回归断言检查
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

### 4.5 顶层 CLI 工具

```bash
# 任务架构 CLI 汇总入口
python shared/scripts/taskarch_cli.py <子命令> [参数]

# 常用子命令
python shared/scripts/taskarch_cli.py lineage --root .                # 查看版本继承
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树  # 切片查看
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md  # 文档门禁
```

---

## 五、平台适配说明

技能通过 `shared/adapters/` 屏蔽平台差异：

| 平台 | 适配文件 | 关键差异 |
|------|----------|----------|
| Claude Code | `shared/adapters/claude.md` | 工具调用格式、Skill 触发 |
| Codex | `shared/adapters/codex.md` | 插件模型、沙箱 |
| Trae | `shared/adapters/trae.md` | 远程工作流、上下文 |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | 标准 stdin/stdout 协议 |

**适配原则**：所有平台读同一份 `shared/references/`，平台差异只写在 `adapters/`，**禁止维护分叉规则**。

---

## 六、共享资源定位

共享文件按**优先级**解析：

```text
1. 当前项目根目录的 skills/ 或 shared/  ← 最高优先级
2. 全局技能安装目录的 skills/ 和 shared/  ← 回退
3. 本技能仓库的 shared/legacy/  ← 仅历史参考
```

**注意**：
- 不得把项目状态、恢复点、变更记录写入**全局**技能目录
- 子技能中的 `../../shared/` 路径按同一规则解析

---

## 七、典型工作流示例

### 7.1 新建项目并初始化

```text
用户："使用任务架构做一个 TODO 应用"
```

执行流程：
1. `project-depth-core` 展开功能簇（增删改查 + 状态 + 提醒 + 分类 + 同步...）
2. `architecture-json` 生成 `architecture/` 切片目录（功能树、模块树、模块详情...）
3. 用户确认后进入实现

### 7.2 修改已有功能

```text
用户："用任务架构给 TODO 加个标签功能"
```

执行流程：
1. `project-depth-core` 智能关联：标签 → 模块（数据/页面/任务/搜索）→ 测试
2. `architecture-json` 更新 `architecture/features/` 和 `architecture/modules/`
3. 触发 `scan_code_drift.py` 检查一致性

### 7.3 跨平台输出

```text
用户："用任务架构做 XXX，把结果导出成 Claude 能读的格式"
```

执行流程：
1. 走完前两层
2. `agent-protocol` 读取 `claude.md` 适配，输出标准契约

---

## 八、最佳实践

1. **薄入口优先**：所有需求先说"使用任务架构做 XXX"，让系统自己路由
2. **强制切片**：旧单文件 `architecture.json` 第一步必须迁移为 `architecture/`
3. **工具优先**：工具可用时优先跑工具，工具不可用时按文本规则降级
4. **平台一致**：所有 Agent 读同一份 `shared/`，平台差异只写在 `adapters/`
5. **受控主动性**：Agent 主动补全时，必须遵守"不破坏用户显式约束"
6. **完成前自检**：实现完成后必须跑 `check_regression_assertions.py` 验证

---

## 九、故障排除

| 问题 | 解决 |
|------|------|
| Agent 不识别技能 | 检查 SKILL.md 的 YAML frontmatter `name` 和 `description` |
| 工具运行报错 | 先 `python <script> --help` 看参数；工具失败可按文本规则降级 |
| architecture.json 不一致 | 跑 `python shared/scripts/validate_architecture.py architecture.json` 看具体错误 |
| 代码和架构 drift | 跑 `python shared/scripts/scan_code_drift.py` 看具体 drift 列表 |
| 跨平台输出异常 | 读 `shared/adapters/<platform>.md` 适配说明 |
| 子技能路径找不到 | 检查 `../../shared/` 解析：项目根目录 vs 全局目录 |

---

## 十、辅助参考链接

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
