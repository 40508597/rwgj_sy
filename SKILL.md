---
name: task-architecture
description: 为新项目设计、已有代码纳管、功能变更、架构重构和一致性校验提供任务架构流程。显式要求使用任务架构，或当前项目存在 architecture.json 或 architecture/ 时，按本次任务范围启用。纯概念问答、只读查看和一次性实验走轻量路径。
---
# 任务架构

这是全局薄入口，只做定位和路由，不承载完整规则。

## 定位规则

1. 先检测当前工作项目的 `architecture.json` 或 `architecture/`。
2. 有指针时跟随到总索引；仅有目录时读取 `architecture/index.json`，缺失则报告未验证。
3. 按本次需要的具体文件定位：优先读取当前项目根目录 `skills/`、`shared/` 中的对应文件。
4. 对应文件缺失时逐项回退到本技能安装目录；仅有同名目录不代表该能力文件存在。
5. 不得把项目状态、恢复点、变更记录或架构切片写入全局技能目录。

解析器自身从已加载 SKILL.md 所在目录定位：`python "<技能安装目录>/shared/scripts/resolve_tool.py" <工具名>`；保持工作目录为调用方项目。子能力层中的 `../../shared/` 路径按同一规则解析：按所需文件逐项检查当前项目根目录的 `shared/`；对应文件缺失时回退到本技能安装目录的 `shared/`。

## 路由顺序

先读 LAYER.md 判定本次范围；下列完整链路按需进入，轻量任务遵循该层的降级规则。

```text
用户需求
→ skills/task-architecture/LAYER.md
→ skills/project-depth-core/CORE.md
→ skills/architecture-json/SCHEMA.md
→ skills/agent-protocol/PROTOCOL.md（仅在需要时）
```

多个项目共用全局能力包时，只共享规则、脚本、模板和参考文档；每个项目的 `architecture/` 目录、验证证据和恢复点互相独立。

## 可见回执

加载后必须按 `skills/task-architecture/LAYER.md` 输出主会话启动回执；禁止静默调用。

## 辅助参考

- 命令速查（给人看）：`shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`shared/references/quickstart.md`
