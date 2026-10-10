# 在 Xl-Ai-Language 技能仓库工作

此文件为本仓库维护提示，文件名不限定宿主。完整能力入口是 [SKILL](SKILL.md)，人用说明见 [README](README.md)，工具检查边界见 [ENFORCEMENT-GUIDE](ENFORCEMENT-GUIDE.md)。

## 规则与项目事实

任务架构是通用智能体能力包，规则、工具和参考在 `skills/` 与 `shared/`；调用方业务架构、状态、恢复点和证据留在调用方项目。所有宿主读同一来源，不维护宿主分叉规则。

仓库本身的工具、模板、固定来源或验证样例可被版本管理；不能把调用方项目的 `architecture.json`、`architecture/` 或业务状态误写到能力安装目录。根SKILL保持定位与路由，详细规则归对应职责层，避免复制产生相反约束。

## 入口与工具

按 [LAYER](skills/xl-ai-language/LAYER.md) 判定本次范围，完整流程先深度设计再物化，协议层按需。可见回执、阶段动作、三重校验和完成首行引用该入口，不在本文件另写模板。详细文件的项目优先/安装回退以 [SKILL定位规则](SKILL.md#定位规则) 为准；`shared/legacy/` 只作历史参考，不能作为运行时回退规则。

脚本数量、运行要求与发布入口以README为准。执行前用resolve_tool取得绝对路径；验证能力包按实际范围运行已有检查，一键入口为 `bash verify-all.sh`（需要相应shell）。工具缺失与语义限制如实说明。

schema是字段类型/重要性底线，STANDARD_STAGES是阶段枚举来源；校验器与生成器共用定义。新增工具复用 `_archlib.py` 的UTF-8、IO、结构化命令和架构加载底座，避免复制规则或静态数字。

## 新能力的归属

| 内容 | 位置 |
|---|---|
| 内部职责层 | `skills/<name>/<职责文件>.md`，根SKILL统一路由 |
| 专业方法接入 | 按 [capability-index](shared/references/capability-index.md) 用任务事实、catalog与宿主元数据选取 |
| 参考规范 | `shared/references/<name>.md`，每条规范明确一处权威说明 |
| 工具/Schema/模板 | `shared/scripts/`、`shared/assets/schema/`、`shared/assets/` |

专业能力按需加载；计划不等于读取，读取不等于实际验证。不开额外安装/审批门槛，不按角色名假定工具能力；缺必需证据为unknown。深度功能全景、14项模块语义、递归事实归属、全语言事实协议和真实验证能力应保持，行为变化配相称回归。
