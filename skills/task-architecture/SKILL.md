---
name: task-architecture
description: 任务架构总入口。只做路由：先深度理解，再架构落位，最后协议执行。不要把子技能细则复制到这里。
---
# 任务架构总入口

这是薄入口，不是能力全集。

执行顺序固定：

```text
用户需求
→ project-depth-core
→ architecture-json
→ agent-protocol（仅在需要门禁、跨平台输出或适配时）
```

路由规则：

- 任何需求先进入 `project-depth-core`，除非用户只是询问概念或运行简单命令。
- 需要创建、修改、校验 `architecture/` 架构文件夹、`architecture/index.json` 或架构切片时进入 `architecture-json`。
- 需要跨智能体、标准输出、硬门禁、能力降级或适配说明时进入 `agent-protocol`。
- 不得从本入口直接写代码、直接展开业务细节、直接判断完成。

用户只需要说“使用任务架构做 XXX”。内部三层自动按需加载。

## 辅助参考

- 命令速查（给人看）：`../../shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`../../shared/references/quickstart.md`
