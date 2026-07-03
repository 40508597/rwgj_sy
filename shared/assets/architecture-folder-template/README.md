# architecture-folder-template 说明

本目录是 **切片目录结构的参考样张**，不是运行时的初始模板入口。

## 用途

- 展示一份完整的 `architecture/` 切片目录骨架长什么样：根 `architecture.json` 仅作
  指针，`architecture/index.json` 是轻量总索引，`features/modules/data/pages/tasks/`
  五类切片各放哪个字段。
- 供 `shared/references/json-sharding.md` 等文档作为结构范例引用。
- 供 `scripts/validate_task_architecture_system.py` 做存在性校验（确保仓库自带样张）。

## 不要直接复制本目录作为新架构

实际生成新架构请走：

```bash
python shared/scripts/init_architecture.py --mode init --output <项目根>
```

init 默认使用 `../architecture-template-with-placeholders.json`（带占位符的单文件模板），
在内存中拆分为切片写盘，并自动剥离模板的 `__` 开头元数据/示例 key——保证产物干净。
本目录的切片用的是空值风格（`""` / `[]` / `{}`），与 init 实际生成的"带占位符"风格不同，
因此直接复制本目录会让占位符机制（F）失效。

## 文件清单

```
architecture-folder-template/
├── architecture.json              # 轻量指针样张：{"指向": "architecture/index.json", ...}
└── architecture/
    ├── index.json                 # 轻量总索引样张：项目 + 索引摘要 + 架构切片
    ├── features/core.json         # 运行形态/功能树/专业能力索引/入口
    ├── modules/structure.json     # 模块拓扑/模块树/模块详情/接口契约/实现清单/完整细节/测试责任矩阵
    ├── pages/delivery.json        # 页面拓扑/交付物/系统集成
    ├── data/data.json             # 数据拓扑
    └── tasks/state.json           # 验证证据/上下文恢复点/未决问题/变更记录
```