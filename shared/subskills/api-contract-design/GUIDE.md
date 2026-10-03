# 接口契约设计与演进

这是面向任务架构的中文改编指南，为当前接口补充语义、失败边界与兼容性审查。
固定上游：[wshobson/agents api-design-principles](https://github.com/wshobson/agents/tree/156b7a5e7a8b93642628a339ee4039c925b34c7f/plugins/backend-development/skills/api-design-principles)。
许可：MIT；Copyright (c) 2024 Seth Hobson；原版权与许可全文保存在 [LICENSE](../upstream/wshobson-agents/LICENSE)。
原文：[SOURCE.md](../upstream/wshobson-agents/plugins/backend-development/skills/api-design-principles/SOURCE.md)；版本固定，原文与参考文件保持原样。

## Given / Produces

Given：接口所在模块、消费者、已确认协议与技术栈、当前契约、阶段、失败及风险要求和允许读写范围。
Produces：接口范围、输入输出、错误语义、权限、幂等、分页或查询成本约束、兼容演进与验证案例。
先识别现有契约和消费者事实，字段、性能指标或外部能力不足时记录未知，不凭示例填充业务接口。

## 何时按需读取

- 模块间或外部调用需要新契约、接口变更、兼容审查、重复请求处理或接口性能治理。
- 验证阶段需要检查错误、鉴权、分页和消费者兼容；无接口的纯视觉任务不加载。
- 当前确实使用REST或GraphQL时，选择相应章节；不因为存在接口就引入新协议。
默认只读本指南；需要核对术语时按预算登记并读取对应SOURCE，已确认REST时再选择对应参考。
已确认GraphQL时按需读 `references/graphql-schema-design.md`；需示例或检查表再读 `references/details.md` 或 `assets/api-design-checklist.md`。
不默认加载全部参考或两种协议；本包未导入上游可执行模板，原文相对参考从SOURCE所在原目录解析。

## 方法与取舍

1. 明确资源或schema、操作、消费者和数据边界；接口模型不照搬持久化结构，现有公共语义优先核对。
2. 记录输入约束、空值和更新语义、正常输出、稳定错误、权限与敏感字段的访问责任。
3. 按实际需求选择分页、过滤、排序、缓存、限流、超时、重试与幂等；为批量操作定义部分成功及失败行为。
4. 比较兼容新增、废弃迁移和版本切换，记录消费者影响、过渡期、回退条件及破坏性变更验收。
5. GraphQL适用时审查空值、输入/载荷、分页、服务端权限和查询成本；批量加载按真实N+1问题选择。
6. 为成功、失败、边界、权限、重复请求与兼容路径分配验证责任，记录哪些检查适用及未验证风险。
不强制REST、GraphQL、版本URL、所有关系DataLoader、所有集合同一分页或FastAPI/Pydantic/Ariadne技术栈。
RPC、消息、CLI和本地接口按自身语义设计；不把HTTP规则照搬为它们的硬门禁，也不新增无需求的端点或字段。
旧示例并非技术事实或生产保证：Pydantic序列化与_links需核对版本，GraphQL SDL中的@include位置有误。
REST资产含mock、宽Host/CORS及错误模型不匹配；只有明确需要时作为示范读取，不自动复制或执行。

## 架构回写与证据

操作、消费者及兼容语义写调用方 `/接口契约`、`/模块详情`；状态、失败和交互约束写 `/完整细节`。
接口文件及迁移项写 `/实现清单`，验证责任写 `/测试责任矩阵`，审查和运行结果写 `/验证证据`。
以上JSON Pointer落在调用方 `architecture/index.json` 或相关切片；实际调用记录给出具体文件及Pointer。
契约变更先回写架构，再由主流程推进已授权实现；不写全局技能目录或另建独立接口真相。
`review`：记录输入、文件哈希、覆盖接口和消费者、发现、取舍、结论与未验证项；schema审阅不证明服务可运行。
`execution`：实际运行契约、schema或接口测试时记录命令argv、返回码、输入版本及证据，区分completed、partial、failed、unknown。
规划、加载、使用与验证分别记账，独立核对产物及回写值；测试未运行不得宣称接口验证通过。
本指南只服务本次接口范围，不执行上游安装命令、不创建中央协调智能体，不接管任务架构的阶段或完成裁决。
