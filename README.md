# 任务架构（rwgj）

> 任务架构通用智能体能力包，作为全局薄入口，承载任务架构规则、能力定义与共享工具。

## 文档导航

- 📖 **本 README**：仓库简介、版本历史、目录结构、维护说明（**人**读）
- 📘 **[docs/USAGE.md](docs/USAGE.md)**：详细使用说明（安装、工具链、平台适配、故障排除）
- 📊 **[docs/CAPABILITIES.md](docs/CAPABILITIES.md)**：技能能力报告（能力地图、评估指标、适用场景）
- 🤖 **SKILL.md**：全局薄入口（**Agent** 加载）
- 🤖 **AGENT-USAGE.md**：通用智能体入口（**Agent** 加载）

## 一、仓库简介

本仓库是一个 **git 版本化的"任务架构技能包"**，用于让 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、CLI Agent 或自研编程智能体按同一套任务架构协议工作。

- **薄入口定位**：不绑定任何插件外壳，只做规则、能力与工具的承载。
- **真相源分离**：能力文件、规则、模板、脚本都在本仓库；每个调用方项目保留自己的 `architecture/` 目录作为项目真相源。
- **跨平台一致**：所有支持的 Agent 读取同一份能力包；平台差异只写在 `shared/adapters/`。

## 二、版本演进历史

本仓库以 **17 个历史版本** + 当前 `rwgj` 入口为时间线，按目录内文件夹的 mtime 顺序**逐个 commit** 形成完整演进链：

| # | commit | 时间 | 版本 |
|---|--------|------|------|
| 1 | `33f1baa` | 2026-05-25 22:45 | 任务架构 1.0 |
| 2 | `33f1baa~1` | 2026-05-26 02:33 | 任务架构 1.1 |
| 3 | `33f1baa~2` | 2026-05-26 05:28 | 任务架构 1.1.1 |
| 4 | … | 2026-05-26 07:10 | 任务架构 1.1.2 |
| 5 | … | 2026-05-26 23:34 | 任务架构 1.1.3 |
| 6 | … | 2026-05-26 23:47 | 任务架构 1.1.4 |
| 7 | … | 2026-05-27 02:40 | 任务架构 1.1.5 |
| 8 | … | 2026-05-27 03:46 | 任务架构 1.1.6 |
| 9 | … | 2026-05-27 04:32 | 任务架构 1.1.7 |
| 10 | … | 2026-05-27 05:11 | 任务架构 1.1.8 |
| 11 | … | 2026-05-27 20:35 | 任务架构 1.1.9 |
| 12 | … | 2026-05-27 20:43 | 任务架构 1.2 |
| 13 | … | 2026-05-29 03:11 | 任务架构 1.3 |
| 14 | … | 2026-05-29 03:20 | 任务架构-通用智能体版 |
| 15 | … | 2026-05-29 08:05 | 任务架构-能力体系 1.0 |
| 16 | … | 2026-05-29 09:05 | 任务架构-能力体系 1.1.1 |
| 17 | `14284e5` | 2026-05-30 23:41 | 任务架构-能力体系 1.1.2 |
| 18 | `aa7ff1f` | 2026-06-03 22:52 | chore: remove .git-tmp backup |
| 19 | `e98c871` | 2026-06-03 22:52 | feat: add rwgj as latest |
| 20 | `ffb0b29` | 2026-06-03 23:08 | chore: flatten rwgj contents to root |

> 通过 `git log --oneline --reverse` 查看完整 20 个 commit。

## 三、仓库结构

```text
任务架构/
├── .git/
├── .source.json              # 技能来源元数据（proma 内部）
├── AGENT-USAGE.md            # 通用智能体入口说明
├── SKILL.md                  # Skill 入口（Codex/Claude 等）
├── README.md                 # 本文件
├── architecture/             # 架构 JSON 分片（data/features/modules/pages/tasks/index）
├── architecture.json         # 架构总入口
├── docs/                     # 设计文档（能力地图、版本继承、回归断言）
├── optional/                 # 可选组件（MCP 查验服务）
├── scripts/                  # 验证脚本
├── shared/                   # 共享能力（references/scripts/assets/schemas/adapters/legacy）
└── skills/                   # 三层能力与薄入口（agent-protocol/architecture-json/project-depth-core/task-architecture）
```

## 四、使用说明

### 1. 全局安装模式

把本仓库放在全局 skills 目录下（如 `~/.proma/agent-workspaces/<workspace>/skills/rwgj` 或 `.agents/skills/rwgj`），任意项目调用时都共享同一份能力文件。

### 2. 项目级复制模式

把整个目录（除 `.git/`）复制到调用方项目根目录，作为项目自己的技能包使用。每个项目保留自己独立的 `architecture/` 目录。

### 3. 路由顺序

```text
用户需求
→ skills/task-architecture/SKILL.md
→ skills/project-depth-core/SKILL.md
→ skills/architecture-json/SKILL.md
→ skills/agent-protocol/SKILL.md（仅在需要时）
```

### 4. 常用 CLI 工具

```bash
# 查看版本继承
python shared/scripts/taskarch_cli.py lineage --root .

# 切片查看
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树

# 文档门禁检查
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md

# 回归断言
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

完整命令速查：`shared/references/commands-cheatsheet.md`

## 五、维护说明

### 修改流程

1. 在根目录编辑对应文件
2. `git add -A`
3. `git commit -m "..."`（建议遵循 Conventional Commits：`feat:`/`fix:`/`chore:`/`docs:`）
4. `git push origin main`

### 添加新能力

- 新增 Skill：在 `skills/` 下创建子目录，放 `SKILL.md`
- 新增参考文档：放 `shared/references/`
- 新增脚本：放 `shared/scripts/`
- 新增 Schema：放 `shared/assets/schema/`
- 新增平台适配：放 `shared/adapters/`

### 不要做的事

- 不要把项目状态、恢复点、变更记录写入本仓库（本仓库是能力包，不是项目记录）
- 不要在 commit 中覆盖 `architecture/` 目录（那是调用方项目的真相源）
- 不要直接编辑 `shared/legacy/` 下的历史 SKILL 文件（仅作历史参考）

## 六、链接

- 远程仓库：https://github.com/405089597/rwgj_sy.git
- 内部使用：见 `AGENT-USAGE.md`
- 设计原则：见 `shared/references/principles-card.md`
