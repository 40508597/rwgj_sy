---
name: task-architecture
description: 为新项目设计、已有代码纳管、功能变更、架构重构和一致性校验提供任务架构流程。显式要求使用任务架构，或当前项目存在 architecture.json 或 architecture/ 时，按本次任务范围启用。纯概念问答、只读查看和一次性实验走轻量路径。
metadata:
  version: "1.3.0"
---
# 任务架构

这是全局薄入口，只做定位和路由，不承载完整规则。

本技能指导 AI 组织项目、充分设计、逐层定位、修改实现与真实验证，并提供通用工程规则和外围工具；技能加载、命令调用和自动化集成由具体宿主负责。

## 定位规则

1. 先检测当前工作项目的 `architecture.json` 或 `architecture/`。
2. 根 `architecture.json` 含 `模块路由` 时，它就是项目总架构，沿相关子模块入口逐层读取；有 `指向` 时跟随既有总索引。仅有 `architecture/` 时检查实际索引；只有辅助文件则按创建/分析流程建立入口，既有入口失效则报告未验证并先修复。
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

新项目默认把代码按真实模块目录组织，每个受管模块有本目录的 `architecture.json`，根文件保留全局目标、约束和总体路由。模块可递归包含子模块，任何一层可有自己的源码与测试；不把所有文件夹变成模块，不为层数而拆分。创建时先充分理解与设计再落目录，实现修改时从根沿相关分支取得契约、源码、测试与影响依据。详细协议按需读 [递归模块架构](shared/references/recursive-modules.md)。既有集中切片布局继续按已登记入口读取，不为形式迁移源码。

多个项目共用全局能力包时，只共享规则、脚本、模板和参考文档；每个项目的模块架构、任务状态、验证证据和恢复点互相独立。

## 可见回执

加载后必须按 `skills/task-architecture/LAYER.md` 输出主会话启动回执；禁止静默调用。

## 辅助参考

- 长程项目的查询、结构化变更、验证、协作、交接和操作恢复：按需读 [项目工具链](shared/references/project-toolchain.md)，使用 `taskarch.py`。现有深度设计与质量能力继续适用。

- 命令速查（给人看）：`shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`shared/references/quickstart.md`
- 专业子能力按已确认任务与姿态按需读取：`shared/references/capability-index.md`；规划不等于实际加载或验证。
