# 任务架构通用能力包使用说明

本包用于任意编程智能体，例如 Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue 或自研 CLI Agent。

## 使用方式

两种方式共用同一套文件，不分叉：

```text
全局使用：把本目录安装/复制到智能体的 skills 目录，通过根 SKILL.md 触发。
项目级使用：把本目录复制到项目根目录，告诉智能体读取 AGENT-USAGE.md。
```

项目级使用时，告诉智能体：

```text
读取 AGENT-USAGE.md，使用任务架构处理本项目。
```

用户仍只需要说：

```text
使用任务架构做 XXX
```

## 三层执行顺序

```text
1. skills/project-depth-core/CORE.md
   先深度理解需求，展开功能簇，做架构归位和智能关联。

2. skills/architecture-json/SCHEMA.md
   把理解结果写入 `architecture/` 架构文件夹、模块详情、实现清单和验证责任。

3. skills/agent-protocol/PROTOCOL.md
   仅在需要跨平台适配、标准输出、硬门禁或能力降级时读取。
```

## 总路由

不要全量读取所有 reference。先按任务信号进入对应层，再读取该层底部的“详细参考路由”。

- 每个受管项目必须使用 `architecture/` 切片目录；`architecture.json` 只允许作为指向 `architecture/index.json` 的轻量指针。
- 模糊需求、新功能、功能深度、交互闭环、反扁平化：先读 `skills/project-depth-core/CORE.md`。
- 创建、修改、校验 `architecture/` 架构文件夹、`architecture/index.json` 或切片，或涉及模块、接口、数据、测试、恢复点：再读 `skills/architecture-json/SCHEMA.md`。
- 跨 Agent 使用、能力降级、虚拟模块审议、硬门禁、标准输出、动态姿势语境：按需读 `skills/agent-protocol/PROTOCOL.md`。
- 只做简单命令或概念问答时，不强制进入完整流程。

## 共享资源定位

共享文件按以下顺序定位：

1. 当前项目根目录存在 `skills/` 或 `shared/` 时，优先使用项目级能力文件。
2. 当前项目没有能力文件时，使用全局安装目录中的 `skills/` 和 `shared/`。
3. 项目真相源永远来自当前工作项目的 `architecture.json -> architecture/index.json`，不得读取或写入全局能力包自己的 `architecture/` 作为业务项目状态。
4. 子能力层中的 `../../shared/` 路径按同一规则解析：先解析为当前项目根目录的 `shared/`，不存在时再解析为全局技能安装目录的 `shared/`。

共享资源目录：

```text
shared/references/
shared/scripts/
shared/assets/
shared/adapters/
```

不要让不同平台维护多份分叉规则。Codex、Claude Code、Trae、Cursor、Windsurf、Cline 和自研 Agent 都读取同一套能力来源。

## MCP/CLI 边界

MCP/CLI 只做查验，不做认知判断。功能簇展开、架构归位和模块详情设计仍由技能文本完成。

## 工具可用时

优先运行：

```text
python shared/scripts/validate_architecture.py architecture.json
python shared/scripts/scan_code_drift.py . --architecture architecture.json --max-items 200
python shared/scripts/taskarch_cli.py lineage --root .
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

工具不可用时，按文本规则降级执行，并记录未运行原因。

## 辅助参考

- 命令速查（给人看）：`shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`shared/references/quickstart.md`
