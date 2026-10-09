# GitHub 编程专业子技能

这些能力服务当前任务架构流程。根据已确认需求、阶段、模块、风险与真实环境选择，内部四层与根入口保持不变。适配指南不是新的宿主SKILL入口，默认只读取选中的最小GUIDE。

| 稳定ID | 能力与适用任务 | 默认入口 |
|---|---|---|
| architecture-patterns | 模块边界、依赖方向、端口与领域一致性设计 | [架构模式](../subskills/architecture-patterns/GUIDE.md) |
| architecture-decisions | 重大技术取舍、代价、验证与替代记录 | [架构决策](../subskills/architecture-decisions/GUIDE.md) |
| api-contract-design | 接口语义、兼容、错误、幂等与分页 | [接口契约](../subskills/api-contract-design/GUIDE.md) |
| implementation-planning | 按依赖拆任务，保留输入输出与验收责任 | [实现规划](../subskills/implementation-planning/GUIDE.md) |
| systematic-debugging | 已有异常的复现、证据追踪和最小修复 | [系统调试](../subskills/systematic-debugging/GUIDE.md) |
| behavior-test-design | 独立预期、真实行为与有效回归断言 | [行为测试](../subskills/behavior-test-design/GUIDE.md) |
| property-testing | 属性、不变量、生成域与最小反例 | [属性测试](../subskills/property-testing/GUIDE.md) |
| api-misuse-review | 默认值、配置组合、误用与静默失败 | [接口误用](../subskills/api-misuse-review/GUIDE.md) |
| defect-variant-review | 从已知缺陷寻找其他模块的同根因漏修 | [同类缺陷](../subskills/defect-variant-review/GUIDE.md) |
| frontend-visual-design | 实际界面的视觉语言、组件与状态 | [UI设计](../subskills/frontend-visual-design/GUIDE.md) |
| web-ui-review | 实际Web界面的交互与可访问性 | [Web UI审查](../subskills/web-ui-review/GUIDE.md) |
| browser-acceptance | 可运行Web应用的真实浏览器验收 | [浏览器验收](../subskills/browser-acceptance/GUIDE.md) |

原有代码语义审查、交接完整性与产物完整性继续可用。出现“验证”或“审计”不自动启用整张表。

## 真实场景与可用性

宿主从已知任务事实填入本次context，不要求用户手工写注册表。`confirmed_capabilities` 可使用稳定ID或中文能力类型；`professional_domains` 与风险也可触发对应方法。明确排除仍优先，必需能力不可用或未实际使用时保留unknown。

以下可用性条件使用JSON布尔值，不能用数字1、字符串true或关键词假装事实：

- UI设计：`facts.has_ui=true`，当前任务实际存在界面。
- Web UI审查：`facts.web_ui=true`，项目实际包含Web界面。
- 浏览器验收：再确认 `facts.browser_tool_available=true`，宿主或项目有实际可用浏览器工具。
- 同类缺陷排查：`facts.known_defect=true`，已有确认的缺陷实例/坏模式。

例：当前任务是“设计桌面规则编辑器”，可记录UI事实并选择UI设计；仅Web专用的审查与浏览器能力保持未选。纯API任务按接口需求选择；语言、文件扩展名与社区热度不决定启用。

```json
{
  "当前阶段": "模块详情",
  "专业领域": ["架构设计", "接口设计"],
  "能力需求": ["实现任务规划"],
  "模块范围": ["m_rules"],
  "只读范围": ["rules", "architecture"],
  "可写范围": ["architecture"],
  "facts": {"has_ui": false, "web_ui": false, "browser_tool_available": false, "known_defect": false}
}
```

接入流程沿用 `capability-index.md`：计划→宿主实际读取→专业任务→产物/架构回写→使用核验。默认catalog见 `../assets/capability-catalog.json`。宿主已有frontend-design、ui-ux-pro-max、ui-styling或design-system时，优先核对职责与可用性，选择一项合适来源；别重复载入同一方法。特定框架技能可在确认实际技术栈后通过宿主元数据登记。

## 统一适配契约

GUIDE提供领域方法与回写责任，不另设阶段、宿主执行器、安装或审批流程。需求、授权、模块归属、阶段与完成裁决沿用LAYER及当前项目事实；已有授权可继续适用工作，未知能力不当作已具备。

专业产出写拥有相应事实的根或模块 `architecture.json`，既有集中布局写登记切片；实际调用给出具体文件与JSON Pointer。公共接口的名称、签名、错误和消费者由所属模块 `接口契约` 权威维护，计划和测试引用；局部算法/任务验收约束可放细节或测试记录，不另建独立接口真相。

证据协议统一见 [能力索引](capability-index.md) 与 [通用质量](universal-quality.md)：规划、实际加载、模型review与真实execution区分；只有实际运行才记录对应命令/操作、当前输入和结果，保留partial、failed、unknown。详细产物唯一维护，证据、变更与恢复记录引用，不重复复制全文。小任务使用相称记录，GUIDE特有工具与适用边界仍按各指南核对。

## 版本、许可与适配

来源锁 `../assets/github-subskills.lock.json` 保存固定commit、原目录、文件哈希、许可与修改说明。包内原SKILL以SOURCE.md存档，不注册成独立入口。默认不读取全部上游正文，不复制其安装、自动提交、流程接管或额外批准要求。

- wshobson/agents、obra/superpowers、Vercel Web Interface Guidelines 的对应来源使用MIT。
- Anthropic frontend-design与webapp-testing各保留Apache-2.0许可。
- Trail of Bits的三项适配及原文按CC-BY-SA-4.0单独声明，保留作者、许可与改编说明；不重标为本项目MIT。

分项许可见 `../../THIRD-PARTY-NOTICES.md`。上游语言、框架、库版本和旧示例只作为方法对照；实际技术事实使用时核对项目和官方资料。本包没有导入上游可执行脚本、模板代码、插件钩子或外部调度器。

先按resolve_tool规则定位，再运行 `python "<check_subskill_sources_path>" "<能力包根>" --json` 核对本地锁与catalog。哈希一致只能证明与记录一致，不能认证同时被改写的锁、远端commit或执行者身份。
