---
name: architecture-json
description: 将 project-depth-core 的理解结果物化为 architecture/ 架构文件夹，继承 1.2 的功能树、模块树、模块详情、实现清单、验证证据和工具链。
---
# Architecture JSON

本技能负责“落得稳”。

`architecture/` 架构文件夹是项目唯一真相源。根 `architecture.json` 只允许作为轻量指针，指向 `architecture/index.json`；不得再把完整项目真相写成单文件。

## 固定落位顺序

```text
需求理解
→ 功能树
→ 模块树
→ 模块详情
→ 入口 / 接口 / 数据 / 页面 / 任务 / 交付物
→ 实现清单
→ 测试责任矩阵
→ 验证证据
→ 变更记录 / 上下文恢复点
```

## 强制切片目录

每个受管项目必须具备：

```text
architecture.json              # 轻量指针，只指向 architecture/index.json
architecture/
  index.json                   # 当前项目真相源总索引
  features/
  modules/
  data/
  pages/
  tasks/
```

单文件 `architecture.json` 已废弃。若项目只有单文件，第一步必须迁移为 `architecture/` 切片目录，再继续实现。

## 单文件迁移

若项目仅有旧版完整单文件 `architecture.json`，先迁移再继续实现：

```text
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .
python shared/scripts/validate_architecture.py architecture.json
```

迁移会把旧单文件归档到 `architecture/archive/`，并生成根指针、`architecture/index.json` 和标准物理切片。

## 模块详情底线

每个实现模块必须有：

- 职责与非职责。
- 所属功能树节点。
- 上游依赖和下游消费者。
- 内部结构。
- 状态机或“不适用”。
- 数据读写责任。
- 错误边界。
- 配置、安全、日志审计、性能和测试责任。

没有模块详情，不得实现。

## 工具链

可用时优先运行共享脚本：

```text
../../shared/scripts/validate_architecture.py
../../shared/scripts/scan_code_drift.py
../../shared/scripts/diff_architecture.py
../../shared/scripts/init_architecture.py
```

工具只做校验、扫描、对比和骨架生成，不替代需求理解。

## 详细参考路由

按触发信号读取，不要全量加载：

- JSON 字段、中文化规范、四层读取策略、schema 底线：`../../shared/references/schemas.md`
- 五个命令、创建/分析/修改/追加/校验工作流：`../../shared/references/commands-workflows.md`
- 21 项一致性校验、禁止事项、完成前自检：`../../shared/references/validation-checklist.md`
- 强制切片目录、架构文件夹、多人/多会话协作：`../../shared/references/json-sharding.md`
- 上下文压缩、中断续跑、恢复点：`../../shared/references/context-recovery.md`
- 任务前置输出、架构变更对比、失败恢复：`../../shared/references/execution-templates.md`
- 新建架构骨架：`../../shared/assets/architecture-folder-template/`
- 需要确定性校验时优先运行：`../../shared/scripts/validate_architecture.py`、`../../shared/scripts/scan_code_drift.py`、`../../shared/scripts/diff_architecture.py`
