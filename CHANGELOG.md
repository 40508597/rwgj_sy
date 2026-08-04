# Changelog

本仓库以「17 个历史版本 + 当前 rwgj 入口」为时间线；完整提交历史见 `git log --reverse --oneline`。
本文件只记录影响使用方的里程碑变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。

## [Unreleased]

### Added

- 文档引用完整性自动检查（check_doc_counts.py 扩展：全仓库 .md 相对路径引用对账）
- 端到端演示脚本 `scripts/demo_project.py`（临时受管项目跑通完整验证链）
- 决策记录 `docs/adr/`（真相源分离 / FBC 强制机制 / 薄入口 / schema 驱动分级）
- Issue/PR 模板（.github/ISSUE_TEMPLATE + PULL_REQUEST_TEMPLATE）
- CI 支持 Python 3.9/3.10/3.11 版本矩阵

### Fixed

- `scan_code_drift.py`：切片模式下 `architecture.json` 指针被误报为「存在但未登记」漂移
- `check_doc_counts.py`：引用检查误报规则描述路径（`../../shared/`）与示例 JSON 虚构文件（tests/）

## [1.1.0] - 2026-08-04

> v1.0.0 tag 已发布于旧提交（GitHub 徽章），本次正式里程碑以 v1.1.0 承接。
> 标志 rwgj 薄入口化与 F+B+C 强制执行机制成熟。

### 里程碑

- **薄入口化**：SKILL.md 只做定位与路由，四层能力（task-architecture / project-depth-core / architecture-json / agent-protocol）按需加载
- **F+B+C 强制执行机制**：占位符（F）+ 状态文件（B）+ 事中裁判（C），把 LLM 的概率性服从变成可阻塞的检查点
- **主会话可见回执**：加载即输出入口链路/触发原因/任务判定，禁止静默调用
- **触发开关**：`TASK_ARCH_AUTO_TRIGGER=off` 可关闭自动检测提醒（返回码 2）
- **工具路径解析规则**：所有相对路径执行前必须先解析（项目根 `shared/` 优先，其次技能安装目录）
- **数字口径统一**：参考文档 21 / 工具脚本 18 / 必需阶段 9 / 平台适配 4 / Schema 2，由 `check_doc_counts.py` 自动对账防漂移
- **质量工程**：verify-all.sh 自检 18 项、49 个单元测试、GitHub Actions CI、回执模板单源化

### 破坏性变更

- 单文件 `architecture.json` 已废弃，受管项目必须使用 `architecture/` 切片目录
- 子能力层文件由 `SKILL.md` 更名为 `LAYER.md` / `CORE.md` / `SCHEMA.md` / `PROTOCOL.md`
- `detect_should_trigger.py` 新增返回码 2（关闭自动检测），返回码契约：0=建议触发，1=不触发，2=已关闭
