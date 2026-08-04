# ADR-0004：Schema 驱动的字段分级（x-importance 单一真相源）

- 状态：已采纳（rwgj v1.1）
- 日期：2026-08-04（记录）

## 背景

`check_placeholders.py` / `validate_architecture.py` 早期在代码里硬编码"哪些字段是核心必填"，
规则散落多处：改 schema 忘了改脚本、改脚本忘了改文档，分级口径多次漂移。

## 决策

- `shared/assets/schema/architecture.schema.json` 用自定义 keyword `x-importance` 标注每个字段的 core / important / optional 分级，并声明 `x-required-subfields`（模块详情 14 项底线子字段）。
- 工具脚本从 schema 派生分级（`resolve_importance_map`），schema 缺失时仅回退到兜底常量（保证无 schema 环境仍可落地校验）。
- 必需阶段数同理：`manage_state.py` 的 `STANDARD_STAGES` 是唯一真相源，文档只引用不重复定义。

## 后果

- ✅ 分级规则只有一份真相源，改 schema 即全局生效，文档/脚本不再各自维护数字。
- ✅ 兜底常量保证工具在残缺环境仍能工作（降级不失败）。
- ⚠️ schema 的 `x-importance` 是私有 keyword，标准 JSON Schema 工具不识别——本仓库工具链自成一体，文档需说明。
- ⚠️ 兜底常量与 schema 可能漂移——已通过单元测试（schema 可用路径 + 回退路径）与 verify-all 锚点约束。
