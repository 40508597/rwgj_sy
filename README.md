# 任务架构（rwgj）

> 任务架构通用智能体能力包，全局薄入口，承载任务架构规则、能力定义与共享工具。

## 文档导航

本 README 只做**仓库总览**。详细内容请阅读：

- 📘 **[docs/USAGE.md](docs/USAGE.md)** — 详细使用说明（安装、工具链、平台适配、故障排除）
- 📊 **[docs/CAPABILITIES.md](docs/CAPABILITIES.md)** — 技能能力报告（能力地图、评估指标、适用场景）

Agent 入口：
- 🤖 **SKILL.md** — 全局薄入口
- 🤖 **AGENT-USAGE.md** — 通用智能体入口

---

## 仓库简介

- **角色**：薄入口技能包，承载任务架构规则与共享工具
- **使用方**：Codex / Claude Code / Trae / Cursor / Windsurf / Cline / Continue / CLI Agent / 自研 Agent
- **核心特性**：真相源分离（能力在仓库，项目状态在调用方 `architecture/`）、跨平台一致（差异只写在 `shared/adapters/`）
- **远程仓库**：https://github.com/405089597/rwgj_sy.git

---

## 版本演进

本仓库以 **17 个历史版本** + 当前 rwgj 入口为时间线，按目录内文件夹的 mtime 顺序**逐个 commit** 形成完整演进链。

完整 commit 历史：`git log --reverse --oneline`（共 21 个 commit，从 `33f1baa` 到 `4270e96`）

版本阶段：
- **任务架构 1.0 ~ 1.1.9**：早期演进（11 个版本）
- **任务架构 1.2 / 1.3**：动态任务姿态、跨智能体协议
- **任务架构-通用智能体版**：平台无关化变体
- **任务架构-能力体系 1.0 / 1.1.1 / 1.1.2**：能力体系化（1.1.2 = 现行入口的前身）
- **rwgj (current)**：薄入口化、组织化

> 能力继承关系详见 `docs/version-lineage.md`（在 rwgj 内部 `shared/` 路径下）

---

## 仓库结构

```text
任务架构/
├── .git/                       # git 仓库
├── .source.json                # 技能来源元数据
├── README.md                   # 本文件（仓库总览）
├── SKILL.md                    # Agent 薄入口
├── AGENT-USAGE.md              # Agent 通用入口
├── architecture.json           # 架构真相源指针
├── architecture/               # 架构切片（data/features/modules/pages/tasks/index）
├── docs/                       # 设计与人读文档
│   ├── USAGE.md                # 详细使用说明
│   ├── CAPABILITIES.md         # 技能能力报告
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

## 维护说明

### 修改流程

```bash
# 1. 编辑文件（在根目录）
# 2. 暂存
git add -A
# 3. 提交（建议遵循 Conventional Commits）
git commit -m "feat|fix|chore|docs: ..."
# 4. 推送
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

### 不要做

- ✗ 在本仓库存项目业务状态（真相源在调用方）
- ✗ 把子技能细则复制到总入口
- ✗ 让 `agent-protocol` 抢占 `project-depth-core` 入口优先级
- ✗ 维护分叉规则（所有 Agent 读同一份）

---

## 快速开始

- **Agent 用户**：说"使用任务架构做 XXX"
- **开发者**：读 [docs/USAGE.md](docs/USAGE.md)
- **评估者**：读 [docs/CAPABILITIES.md](docs/CAPABILITIES.md)
- **维护者**：读本文档的"维护说明" + 内部 `shared/references/`
