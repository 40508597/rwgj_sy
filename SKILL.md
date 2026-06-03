---
name: 任务架构
description: 任务架构能力体系全局入口。安装一次即可在多个项目中触发；自动区分项目级架构文件和全局能力文件。
---
# 任务架构

这是全局薄入口，只做定位和路由，不承载完整规则。

## 定位规则

1. 先检测当前工作项目是否存在 `architecture.json`。
2. 若存在，项目真相源只读取当前项目的 `architecture.json -> architecture/index.json`。
3. 能力文件优先从当前项目根目录的 `skills/`、`shared/` 读取。
4. 当前项目没有能力文件时，从本技能安装目录读取 `skills/`、`shared/`。
5. 不得把项目状态、恢复点、变更记录或架构切片写入全局技能目录。

子技能中的 `../../shared/` 路径按同一规则解析：先看当前项目根目录是否有 `shared/`，没有则回到本技能安装目录的 `shared/`。

## 路由顺序

```text
用户需求
→ skills/task-architecture/SKILL.md
→ skills/project-depth-core/SKILL.md
→ skills/architecture-json/SKILL.md
→ skills/agent-protocol/SKILL.md（仅在需要时）
```

多个项目共用全局能力包时，只共享规则、脚本、模板和参考文档；每个项目的 `architecture/` 目录、验证证据和恢复点互相独立。

## 辅助参考

- 命令速查（给人看）：`shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`shared/references/quickstart.md`
