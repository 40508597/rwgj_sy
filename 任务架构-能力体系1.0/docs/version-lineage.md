# 任务架构版本继承记录

本文件记录能力来源，防止后续重构时用新能力覆盖旧能力。

| 来源版本 | 保留能力 | 目标位置 |
|---|---|---|
| 1.0 / 1.1 | 最大主动性、功能簇展开、交互完整性、多层递进、分治设计、智能关联路由 | `project-depth-core` |
| 1.1.2 | 主入口瘦身、references 分拆 | 总入口与 shared 文档组织 |
| 1.1.5 / 1.1.6 | 功能树、模块树、模块详情、实现清单、切片意识 | `architecture-json` |
| 1.1.7 / 1.1.8 | validate / scan / diff / init 工具链 | `shared/scripts` |
| 1.1.9 | 受控主动性、防扁平化、注意力保护、完成前自检 | `project-depth-core` 与 `architecture-json` |
| 1.2 | 动态任务姿态建议器、三轴任务校准 | `shared/scripts` 与辅助参考 |
| 1.3 | 跨智能体协议、适配层、虚拟模块审议、硬门禁、标准输出契约 | `agent-protocol` |

继承原则：

```text
1.1 做认知内核
1.2 做结构落位
1.3 做协议外壳
```

后续任何优化不得让 `agent-protocol` 抢占 `project-depth-core` 的入口优先级。
