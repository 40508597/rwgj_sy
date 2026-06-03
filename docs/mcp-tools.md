# MCP 工具边界

MCP 是查验层，不是认知层。它只读取、校验和返回结构化结果，不展开功能簇，不做项目应该是什么的判断。

## 已暴露工具

- `get_architecture_slice`：读取根指针后，从 `architecture/index.json` 和相关切片返回指定路径或模块详情。
- `check_write_gate`：检查目标文件是否登记到 `实现清单`。
- `scan_drift`：调用共享脚本扫描代码漂移。
- `validate_architecture`：调用共享脚本校验架构 JSON。
- `load_recovery_point`：读取 `上下文恢复点`。
- `record_change`：返回变更记录建议，不直接写文件。

## 明确不做

- 不提供 `expand_function_cluster`。
- 不替代 `project-depth-core` 的主动理解。
- 不替代 `architecture-json` 的模块详情设计。
- 不引入中央协调智能体。
