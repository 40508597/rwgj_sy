# Trae 适配说明

Trae 或同类 AI IDE 使用本协议时，按通用编程智能体处理。

- 若支持项目规则文件，把 `SKILL.md` 加载为最高优先级工程协议。
- 若支持文件读写和终端命令，按增强单智能体模式执行。
- 若不支持稳定长期上下文，必须把恢复点和变更记录写入 `architecture/tasks/state.json`，或写入由 `architecture/index.json` 汇总的恢复点；动态姿势语境只在跨会话、长任务或高风险任务中持久化。
- 若平台提供多 Agent 或任务拆分能力，可按模块智能体协议映射，但不得让子任务越过模块边界。
- 完整实现交付按 `../references/universal-quality.md` 配置本次事实与必需规则，运行 `python "<gate_check_path>" "<项目根>" --quality-required --json`；缺失或未验证时不得声明完成。启动、查看等局部任务继续按范围降级，只汇报本次结果。

`<gate_check_path>` 是 resolve_tool.py 对 gate_check 返回的 JSON.path，表示完整脚本绝对路径，不再追加脚本名。

Trae 适配层不得引入平台专有字段到根 `architecture.json` 指针或 `architecture/index.json` 顶层；平台差异写入适配文档或验证证据。

专业子能力按 `../references/capability-index.md` 从当前需求、模块、风险、姿态和宿主可用元数据选择。能运行工具则生成计划，能读文件则实际读取选中的正文；规划CLI不声称修改系统提示。宿主不提供技能清单时只使用已知可用资料，不自动扫描或安装外部技能；缺必需证据仍为未验证。
