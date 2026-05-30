# Trae 适配说明

Trae 或同类 AI IDE 使用本协议时，按通用编程智能体处理。

- 若支持项目规则文件，把 `SKILL.md` 加载为最高优先级工程协议。
- 若支持文件读写和终端命令，按增强单智能体模式执行。
- 若不支持稳定长期上下文，必须把恢复点和变更记录写入 `architecture/tasks/state.json`，或写入由 `architecture/index.json` 汇总的恢复点；动态姿势语境只在跨会话、长任务或高风险任务中持久化。
- 若平台提供多 Agent 或任务拆分能力，可按模块智能体协议映射，但不得让子任务越过模块边界。

Trae 适配层不得引入平台专有字段到根 `architecture.json` 指针或 `architecture/index.json` 顶层；平台差异写入适配文档或验证证据。
