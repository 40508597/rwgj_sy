# 五个命令速查卡

给人看的快速路由卡。每个命令的详细流程、边界与安全修改模式见 [命令工作流](commands-workflows.md)，本文不重复步骤清单。

## 未写命令时

用户只说"使用 Xl-Ai-Language""按这个技能""按架构来"，但没有写具体命令时，必须自动判定：

| 场景 | 自动选择 |
|------|------|
| 检查一致性、找漂移、评估现状 | `/校验架构` |
| 已有代码纳入管理 | `/分析架构` |
| 新项目从零开始 | `/创建架构` |
| 新增独立功能/模块职责 | `/追加架构`；已有模块职责内新增页面、文件或导出用 `/修改架构` |
| 修改已有功能、修 Bug、删 UI、改字段、优化已有模块 | `/修改架构` |

第一段汇报写明"自动判定命令"，不得因为用户没写命令就跳过架构文件夹。

## 五个命令一句话

| 命令 | 输入 → 输出 | 适用 |
|------|-------------|------|
| `/分析架构` | 已有项目目录 → 根总架构 + 真实模块目录内的架构文件 | 已有项目想纳入架构管理（先现状画像，再治理建议） |
| `/创建架构` | 需求描述 → 根总架构 + 模块路由 + 各模块架构 | 新项目从零开始（功能簇 → 功能树 → 模块树 → 逐块设计） |
| `/修改架构` | 变更需求 + 架构文件夹 → 更新后的相关模块架构或集中切片 | 需求变化，已有模块接口或文件需调整（先影响范围分析） |
| `/追加架构` | 新模块需求 + 架构文件夹 → 新增模块目录、架构文件与父路由 | 新增架构文件夹中不存在的功能/模块 |
| `/校验架构` | 架构文件夹 + 项目代码 → 一致性报告 | 检查漂移、架构过期、契约不一致、测试缺失 |

## 模块工具（按需）

新项目创建、逐层阅读、源码路由、候选查询、依赖影响与带哈希的局部更新，见 [递归模块架构](recursive-modules.md)。每个工具先通过 `resolve_tool.py` 定位；局部查询成功不代表架构设计或真实验证通过。

## 可视化阅读（按需）

需要架构图、完整项目画布或可视化评审时读 [项目架构可视化](architecture-visualization.md)。`render_architecture.py --format html` 生成渐进展开的完整项目画布；`--html-view report` 可选专题报告，具体输入、路径解析与输出位置见该指南。

## 完成前

按 [LAYER 的完成契约](../../skills/xl-ai-language/LAYER.md#工具与完成契约) 说明本次验证结果与边界；完整实现交付核对一致性、真实证据及剩余风险。实际变化写入唯一权威记录，恢复点保持准确，不重复未变化内容；示例见 [执行记录](execution-templates.md)。

## 统一项目工具链（按需）

长程项目需要结构化变更、协作或恢复时选用以下操作，不要求简单任务走完整链路。按 LAYER 先解析 `taskarch.py` 的绝对路径，命令保持调用方项目工作目录。

```bash
python "<taskarch_path>" --project "<项目根>" query search --query "功能目标"
python "<taskarch_path>" --project "<项目根>" query context --selector "<模块编号>"
python "<taskarch_path>" --project "<项目根>" change begin --input "<请求.json>"
python "<taskarch_path>" --project "<项目根>" change stage --input "<暂存请求.json>"
python "<taskarch_path>" --project "<项目根>" change preview --id "<change-id>"
python "<taskarch_path>" --project "<项目根>" change apply --input "<应用请求.json>"
python "<taskarch_path>" --project "<项目根>" change verify --input "<验证请求.json>"
python "<taskarch_path>" --project "<项目根>" change accept --input "<接受请求.json>"
python "<taskarch_path>" --project "<项目根>" timeline show --after 0 --limit 100
```

完整操作契约、租约、交接、暂停点和检查点见 [项目工具链](./project-toolchain.md)，维护清单由 `check_toolchain_inventory.py` 动态盘点。
