# Architecture JSON

项目语言与工程格式不限制架构物化。质量规则、观察事实、执行收据按 `../../shared/references/universal-quality.md` 管理，保存在当前项目；区分声明与观察、记录预定范围与未知项，不能把旧证据字段非空等同于质量已通过。

本技能负责”落得稳”。

`architecture/` 架构文件夹是项目唯一真相源。根 `architecture.json` 只允许作为轻量指针，指向 `architecture/index.json`；不得再把完整项目真相写成单文件。

## 进入本层前必做：读取进度状态

进入本层时，**第一步必须读取并显示进度状态**：

```bash
python ../../shared/scripts/manage_state.py show --state-path architecture/_state.json
```

若状态文件不存在，**必须先创建**：

```bash
python ../../shared/scripts/manage_state.py init --project-name “项目名” --state-path architecture/_state.json
```

状态文件会追踪以下阶段的完成情况，确保不遗漏：
- 需求理解 / 功能树 / 模块树 / 模块详情 / 入口定义 / 数据拓扑 / 实现清单 / 测试责任 / 验证证据（9 个必需）
- 接口契约（可选，跨模块调用业务才需要）

真相源：`shared/scripts/manage_state.py` 的 STANDARD_STAGES（required=True 共 9 项）。

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
  index.json                   # 当前项目真相源总索引（必须使用带占位符的模板）
  _state.json                  # 进度状态文件（由 manage_state.py 生成）
  features/
  modules/
  data/
  pages/
  tasks/
```

### 创建新架构时必须使用带占位符的模板

```bash
# 工具生成根指针、标准切片及占位符（路径执行前按 LAYER 解析）
python ../../shared/scripts/init_architecture.py --mode init --output .
python ../../shared/scripts/manage_state.py init --project-name "项目名称"
```

**占位符机制**：
- 所有必填字段包含 `__待填__` 占位符
- 可选字段包含 `__待选填__` 占位符
- 自动生成字段（如时间戳）使用 `__自动生成__`，由工具填充
- 容器内说明性 key 使用 `__注释__`，完成后必须删除
- 模块详情/接口契约/实现清单的示例 key 使用 `__示例模块名__` / `__示例接口名__`，使用前必须替换为真实名称
- 填写时逐步替换占位符为实际内容
- 完成前必须运行 `check_placeholders.py`：
  - 检测所有 `__待` 开头的 value 占位符，按 schema `x-importance` 分级报 critical/important/optional
  - 检测所有 `__示例*__` / `__注释__` / `__占位符说明__` 残留 key 一律判 critical（防止生成「假模块」）
  - 检测 schema 标 core 的顶层字段是否整段缺失
  - 检测每个模块详情对象是否含 14 项底线子字段
- `init_architecture.py` 写盘前自动剥离模板所有 `__` 开头 key，因此 init 后模块详情/接口契约/实现清单容器是空 `{}`，由用户填入真实模块名再补子字段

单文件 `architecture.json` 已废弃。若项目只有单文件，第一步必须迁移为 `architecture/` 切片目录，再继续实现。

## 单文件迁移

若项目仅有旧版完整单文件 `architecture.json`，先迁移再继续实现：

```text
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .
python shared/scripts/validate_architecture.py architecture/index.json
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

> 相对路径执行前按 LAYER.md「工具执行前置」规则解析：先项目根 `shared/`，再回退技能安装目录。

### 变更批次后的校验与状态推进

```bash
# 1. 查找尚未填完的核心项；未完成项禁止声明对应设计完成，不阻止继续补齐设计
python ../../shared/scripts/check_placeholders.py architecture/index.json

# 2. 设计进行中检查结构底线；最终完成时另跑完整门禁
python ../../shared/scripts/validate_architecture.py architecture/index.json --stage skeleton

# 3. 仅标记真实完成的阶段
python ../../shared/scripts/manage_state.py update <阶段名> completed --note "完成说明"

# 完成交付前：统一收尾判定
python ../../shared/scripts/gate_check.py . --quality-required --json
```

### 传统验证工具（可用时优先运行）

```bash
python ../../shared/scripts/validate_architecture.py architecture/index.json
python ../../shared/scripts/scan_code_drift.py . --architecture architecture/index.json
python ../../shared/scripts/diff_architecture.py old.json new.json
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
- 查看目录布局样张（不是直接复制初始化）：`../../shared/assets/architecture-folder-template/`
- 需要确定性校验时优先运行：`../../shared/scripts/validate_architecture.py`、`../../shared/scripts/scan_code_drift.py`、`../../shared/scripts/diff_architecture.py`
