# 任务架构通用能力包

这是任务架构的通用化组织形态，不绑定 Codex 插件外壳，也不覆盖历史版本。

目标：

```text
用 1.1 做认知内核
用 1.2 做结构落位
用 1.3 做协议外壳
```

目录：

- `SKILL.md`：Codex/Claude 等支持 Skill 的全局薄入口。
- `AGENT-USAGE.md`：任意编程智能体和项目级复制使用的通用入口。
- `skills/`：三层能力与薄入口。
- `shared/`：共享 references、scripts、assets、schemas、adapters。
- `docs/`：版本继承、能力地图和回归断言。
- `optional/mcp/`：可选 MCP 查验工具。

外部使用只暴露一个入口：`任务架构`。支持全局安装和项目级复制两种模式；全局模式只共享能力文件，每个项目仍使用自己的 `architecture/` 目录作为真相源。

Codex、Claude Code、Trae、Cursor、Windsurf、Cline 和自研 Agent 都读取同一套通用能力包；平台差异只写在 `shared/adapters/`。

常用确定性工具：

```text
python shared/scripts/taskarch_cli.py lineage --root .
python shared/scripts/taskarch_cli.py slice --architecture architecture.json --path 功能树
python shared/scripts/taskarch_cli.py gate-file --architecture architecture.json --file README.md
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

MCP 只暴露查验工具，不负责功能簇展开或架构判断。工具清单见 `docs/mcp-tools.md`。
