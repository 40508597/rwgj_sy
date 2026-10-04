# 专业能力索引

专业能力索引用于把智能体已有技能、外部技能或本地专业规则接入 `任务架构` 主流程。内部四层是一个技能内的规则路由；这里接入的是完成具体任务的专业能力。它不拥有项目真相源，不替代功能树、模块边界、接口契约和验证证据，也不引入中央协调智能体。

核心定位：

```
任务架构 = 主流程 + architecture/ 架构文件夹真相源 + 功能树 + 架构落位 + 校验追踪
专业能力索引 = 按功能树节点提示可用专业能力，并规定产出回写位置
智能体原生技能/外部技能 = 执行具体专业任务
```

## 使用边界

必须遵守：
- 只有功能树节点、模块设计、交互细节、测试责任或验证证据需要专业能力时，才读取或建议调用对应技能。
- 专业能力产出必须回写到 `architecture/index.json` 或相关切片的对应位置。
- 没有对应技能时，智能体按通用能力补全，不阻塞主流程。
- 外部技能只是候选能力，使用前应确认当前环境是否安装、是否可信、是否适合项目技术栈。
- 专业能力选择服从本次已确认需求、模块、风险、明确排除和环境可用性。语言或文件后缀不决定技能启用，关键词只生成候选。
- 读取预算只控制专业资料的载入量，不限制主流程的功能全景。按 `function-clusters.md` 默认充分展开相关能力；尚未裁决的衍生功能保留在全景，进入相应设计或实现阶段后再选择所需专业资料。
- 没有动态修改系统提示的宿主API时，使用宿主原生读取工具把选中技能的最小必要文件载入当前上下文；不得声称CLI已经注入提示或调用了技能。
- 缺少技能可以继续完成允许的普通工作，但本次必需证据不足仍为未验证。不得自动安装外部技能，也不得把降级记录当作检查通过。

禁止：
- 不得让专业能力索引决定项目主流程。
- 不得绕过 `architecture/` 架构文件夹直接修改代码。
- 不得每次任务强制读取所有专业技能。
- 不得让外部技能擅自扩大业务范围。
- 不得把技能列表设计成外部多智能体调度系统；模块智能体协议只按模块边界组织结构化审议，仍受 `architecture/` 架构文件夹和硬约束门禁控制。

## 简单索引与可执行注册

以下简单索引兼容原有项目，用于模型按节点查找能力。需要确定性规划与使用核验时，按本包的能力注册/使用模板提供稳定ID、来源、作用域、输入、产物及回写绑定；不能把推荐结构误称已经完成实际调用。

## 简单索引结构

```json
{
  "专业能力索引": [
    {
      "能力类型": "UI设计",
      "适用节点": ["页面", "组件", "仪表盘", "管理后台"],
      "触发信号": ["需要视觉设计", "需要交互状态", "需要响应式布局", "需要图标库", "需要截图验收"],
      "调用建议": "如当前智能体存在 UI设计系统、前端设计或图标系统技能，优先读取；不存在则按本技能规则自行补全",
      "质量要求": ["界面要有设计感", "建立或遵循设计系统", "优先使用现有图标库", "图标语义清晰且尺寸一致", "截图或浏览器检查可验证"],
      "候选技能": [
        {
          "名称": "web-design-guidelines",
          "来源": "vercel-labs/agent-skills",
          "链接": "https://skills.sh/vercel-labs/agent-skills/web-design-guidelines",
          "安装命令": "npx skills add vercel-labs/agent-skills@web-design-guidelines"
        }
      ],
      "回写位置": ["功能树", "页面拓扑", "实现清单", "完整细节", "测试责任矩阵", "验证证据"],
      "边界": "不得绕过 architecture/ 架构文件夹直接扩大页面范围或改变产品形态"
    }
  ]
}
```

字段说明：
- `能力类型`：专业能力分类，不等于具体技能名称。
- `适用节点`：功能树或架构层中的触发位置。
- `触发信号`：什么时候需要考虑该能力。
- `调用建议`：当前智能体有对应技能时如何使用；没有时如何降级。
- `候选技能`：可选参考，不作为强依赖。
- `回写位置`：专业能力产出必须进入的 `architecture/index.json` 或相关切片层级。
- `边界`：防止专业技能越权扩展业务范围。

## 根据任务姿态按需加载

1. 先按 LAYER 判定本次档位和阶段，确认当前需求涉及的能力、模块、风险和排除项。该确认由现有用户需求与项目事实完成，不要求每次让用户填写注册表。
2. 宿主已经提供的技能名称、描述、路径属于可用性元数据。先凭元数据筛选，给规划器提供本次适用的最小catalog；不要读取全部技能正文，也不要扫描用户技能目录来替代宿主清单。可按实际需要加入已安装外部技能或本地规则。
3. 姿态决定加载时机、读取范围与验证重点；专业领域和已确认能力决定选什么。关键词命中、审计员姿态或“验证”阶段本身不能证明所有专项适用。
4. 使用 `plan_capabilities.py` 生成计划；它只检查注册、适用性、路径和预算并给出 `read_files`。宿主实际读取所选文件后才记为已加载，执行相应任务后才记为已使用。
5. 阶段、范围、风险、文件或需求变化时重新规划，对照新增、保留和退出项。退休能力的未解决约束、失败和必需证据仍保留；长任务/恢复读取当前计划和使用记录再核对输入版本。

工具先按 LAYER 的 resolve_tool 规则取绝对路径，命令在调用方项目执行：

```text
python "<plan_capabilities_path>" --project "<项目根>" --context "<本次确认语境.json>" --catalog "<本次适用catalog.json>" --output "<计划.json>"
python "<check_capability_usage_path>" "<项目根>" --plan "<计划.json>" --usage "<实际使用.json>" --context "<本次确认语境.json>" --json
```

默认内置catalog可省略 `--catalog`；`--previous "<旧计划.json>"` 仅用于显示变化，当前适用性与文件指纹重新计算。具体输入字段以随包模板与工具 `--help` 为准。选定输入的哈希只绑定本次范围，不提供全项目真实性证明。

已有宿主元数据时可用 `python "<plan_capabilities_path>" --project "<项目根>" --metadata "<本次宿主元数据.json>" --catalog-output "<本次适用catalog.json>"` 转换，再按当前语境规划。catalog读取优先项目 `architecture/capabilities/catalog.json`，其次本包 `../assets/capability-catalog.json`；默认核验记录位于调用方 `architecture/capabilities/`，与全局能力文件分离。

元数据可以是技能数组，也可以是下列 `skills` 对象。`path` 使用宿主给出的已有技能绝对入口路径；`capability_type` 是模型依据当前需求和技能描述确定的专业能力，未提供时仅按技能名称精确匹配，不猜测技能职责。`refs` 相对该入口所在目录，只列本次确实需要的参考。文件读写范围取本次语境与技能声明的交集，默认不授予写业务文件权限。

```json
{
  "skills": [{
    "name": "local-rule-review",
    "path": "<宿主提供的已安装技能绝对路径>",
    "capability_type": "规则正确性审查",
    "requires": {"stages": ["验证", "验证证据"]},
    "refs": [],
    "read_scope": ["rules", "ship"],
    "write_scope": [],
    "allowed_writeback": ["/验证证据"]
  }]
}
```

对应的确认语境可包含 `当前阶段`、`专业领域`、`能力需求`、`模块范围`、`只读范围`、`可写范围` 和 `明确排除`；这些来自本次任务事实与已取得授权，不需要用户重复选择。候选简介不等于已加载，`read_files` 才是宿主实际读取的文件列表。

文件范围使用项目内相对路径：精确文件、以 `/` 结尾的目录或已存在目录、以及可移植的路径通配。`*` 和 `?` 只匹配单个路径组件，独立的 `**` 匹配任意层级；`bin/*` 不允许 `bin/child/file`，`architecture/**` 允许该目录下的多层文件，`**` 仍仅限项目内。规划器取保守交集，无法精确表示的复杂通配交集可能为空；不要因此扩大授权，改用明确文件或目录范围。

完全跳过档不创建计划或状态文件。小任务可只输出一句“阶段/选定能力/范围/未验证项”，记录与风险相称；启用机器可检查的专业调用时再保存最小计划和使用记录。无对应调用的旧索引可以 skipped，不能据此声称专项已通过。

短回执示例：`专业能力：代码语义审查；阶段=验证；已加载=semantic-code-review；范围=m_store；自动测试未运行。` 未读取正文只能说已选择；不打印整份catalog。

## 内置专业资料

| 稳定ID | 何时读取 | 资料 |
|---|---|---|
| `semantic-code-review` | 已确认需要代码正确性、状态/异常/并发/公共契约审查，且进入实现或验证 | `semantic-code-review.md` |
| `handoff-integrity` | 跨模块/跨执行者交接、部分失败合并或上下文恢复 | `handoff-integrity.md` |
| `artifact-integrity` | 架构迁移、转换、导出、专业产物回写的验证 | `artifact-integrity.md` |

这些资料是本技能的按需参考，不是新宿主SKILL入口。原UI、测试、安全、性能、部署等专业领域继续接入；平台没有对应工具时记录能力缺口。没有运行测试或转换，不因读取资料而自动获得执行结果。

## 使用、产出与验证分开

- 计划记录选定来源、文件哈希、理由、关联节点、读写范围和允许回写位置；实际使用记录记录加载与任务结果，并引用当前计划/语境和选定输入。
- `review` 表示人工或模型审查：允许零发现，说明输入、覆盖范围、结论和未验证项。报告结构可通过，不证明语义正确或自动执行通过。
- `execution` 表示实际运行：需要明确argv与当前输入的真实收据，按 `universal-quality.md` 核验。结果保留 completed、partial、failed、unknown；有失败优先报告失败，缺必需证据为unknown。
- 产物与架构回写按指定JSON Pointer独立读取并比较；不能仅写“已回写”。文件哈希或字段相等不证明业务正确。
- 完整交付继续运行 `gate_check --quality-required`；启用专业调用的计划与记录也接受 `check_capability_usage.py` 核验。未启用专项的 skipped 与本次必需专项的 unknown 分别报告。

使用模板见 `../assets/capability-usage-template.json`，结构见 `../assets/schema/capability-usage.schema.json`。其占位哈希必须替换为本次真实值，不能照抄后标记完成。调用记录包含 `plan_fingerprint`、`context_sha256`、`calls`；每项区分 `kind` 与 `status`，记录项目输入哈希、读取/修改文件、产物原始哈希和回写位置。当前自动回写对账读取JSON产物的 `artifact_pointer` 与架构 `writeback`；其他格式应先由适用工具产生可核验事实，不声称此检查器内置所有解析器。记录一致性不认证执行者身份，也不证明报告结论正确。

## 随包的 GitHub 编程子技能

已筛选的架构、规划、调试、测试、安全边界及UI能力采用固定上游版本和中文适配入口，注册在默认catalog。列表、真实场景条件、使用方式与许可见 `programming-subskills.md`。默认只加载选中GUIDE；必要上游参考须按预算登记，再重新规划。原文存档用于核对方法，不增加执行权限、不自动运行附带命令。

源版本与文件完整性通过 `check_subskill_sources.py` 核对；该检查不联网认证远端提交，不替代实际任务验证。既有宿主技能按元数据选择，避免同时加载职责相同的多个来源。项目状态与调用记录继续只写当前项目。

## 默认能力类型

| 能力类型 | 触发信号 | 回写位置 |
|------|------|------|
| UI设计 | 页面、组件、仪表盘、管理后台、响应式、设计系统、图标库、截图验收 | 功能树、页面拓扑、实现清单、完整细节、测试责任矩阵、验证证据 |
| 前端工程 | React、Next.js、Vue、组件状态、路由、客户端数据流 | 页面拓扑、接口契约、实现清单、完整细节、测试责任矩阵 |
| 后端工程 | API、服务层、领域逻辑、队列任务、CLI、后台任务、第三方集成 | 模块树、模块详情、接口契约、实现清单、完整细节、测试责任矩阵 |
| 客户端工程 | Electron、Tauri、PyQt、WPF、WinForms、移动端、浏览器插件、系统托盘、菜单栏、快捷键、本地文件权限、自动更新 | 运行形态、入口、系统集成、模块树、模块详情、实现清单、完整细节、测试责任矩阵、验证证据 |
| 数据工程 | 数据库表、索引、迁移、缓存、数据同步、数据校验 | 数据拓扑、模块详情、接口契约、实现清单、测试责任矩阵、验证证据 |
| 端到端测试 | 浏览器交互、API流程、CLI流程、后台任务、截图验收、回归链路 | 测试责任矩阵、验证证据、完整细节 |
| 后端测试 | 接口契约、异常路径、数据库故障、权限边界 | 接口契约、完整细节、测试责任矩阵、验证证据 |
| 安全 | 登录鉴权、权限、敏感数据、审计、规则配置 | 功能树、接口契约、数据拓扑、完整细节、测试责任矩阵 |
| 性能 | 慢接口、慢查询、大列表、批量任务、客户端渲染卡顿、资源加载慢 | 功能树、接口契约、实现清单、验证证据 |
| 部署运维 | 云部署、CI/CD、环境变量、健康检查、回滚、安装包发布、容器镜像、SDK发布、插件发布、自动更新 | 运行形态、入口、交付物、系统集成、实现清单、验证证据、上下文恢复点 |
| 文档 | API文档、ADR、组件文档、交付说明 | 变更记录、验证证据、实现清单 |

## 外部技能候选

以下是历史候选参考，未安装者不属于当前可用能力。使用前核对当前来源、适用范围和实际环境；不得据表自动安装或执行命令，热度不能证明工程质量。

| 能力类型 | 候选技能 | 参考链接 | 备注 |
|------|------|------|------|
| UI设计 | `vercel-labs/agent-skills@web-design-guidelines` | https://skills.sh/vercel-labs/agent-skills/web-design-guidelines | Web设计规范候选 |
| React | `vercel-labs/agent-skills@vercel-react-best-practices` | https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices | React/Next.js规范候选 |
| 端到端测试 | `anthropics/skills@webapp-testing` | https://skills.sh/anthropics/skills/webapp-testing | 浏览器交互/E2E候选 |
| Python测试 | `wshobson/agents@python-testing-patterns` | https://skills.sh/wshobson/agents/python-testing-patterns | 适合 Python 测试模式 |
| JS测试 | `wshobson/agents@javascript-testing-patterns` | https://skills.sh/wshobson/agents/javascript-testing-patterns | 适合 JavaScript 测试模式 |
| 部署 | `microsoft/azure-skills@azure-deploy` | https://skills.sh/microsoft/azure-skills/azure-deploy | Azure部署候选 |
| 部署 | `vercel-labs/agent-skills@deploy-to-vercel` | https://skills.sh/vercel-labs/agent-skills/deploy-to-vercel | 适合 Vercel 部署 |
| 前端性能 | `addyosmani/web-quality-skills@performance` | https://skills.sh/addyosmani/web-quality-skills/performance | 适合前端性能治理 |
| Python性能 | `wshobson/agents@python-performance-optimization` | https://skills.sh/wshobson/agents/python-performance-optimization | 适合 Python 性能优化 |
| 安全 | `supercent-io/skills-template@security-best-practices` | https://skills.sh/supercent-io/skills-template/security-best-practices | 通用安全最佳实践 |
| 认证安全 | `better-auth/skills@better-auth-security-best-practices` | https://skills.sh/better-auth/skills/better-auth-security-best-practices | 适合 better-auth 相关项目 |
| 文档 | `github/awesome-copilot@documentation-writer` | https://skills.sh/github/awesome-copilot/documentation-writer | 适合文档生成 |
| API文档 | `supercent-io/skills-template@api-documentation` | https://skills.sh/supercent-io/skills-template/api-documentation | 适合 API 文档 |

## UI 质量门禁

凡是功能树节点涉及页面、组件、仪表盘、管理后台、编辑器、IDE、可视化工具、移动端界面或交互流程，默认启用 UI 质量门禁。

必须做到：
- **有设计感**：界面不能只停留在可用层面；布局、间距、字体、色彩、状态和动效要形成清楚的产品气质。
- **设计系统意识**：优先识别项目已有 tokens、组件库、布局壳和交互规范；没有时，为中大型项目建立最小设计上下文。
- **图标库优先**：优先使用项目已有图标库；若已有 `lucide-react` 或 shadcn/ui，优先使用 Lucide；不要手画可被图标库覆盖的常规 SVG。
- **图标语义明确**：按钮、工具栏、导航、状态、空状态图标必须语义匹配；图标按钮要有 tooltip 或可访问标签。
- **界面状态完整**：默认、hover、active、focus、disabled、loading、empty、error、success 等状态按场景补齐。
- **响应式可用**：桌面和移动/窄屏不能只是压缩，必要时重排、折叠或改为抽屉。
- **截图验收**：项目可运行时，重要 UI 修改必须尽量通过浏览器截图或真实渲染检查验证。

根据宿主实际提供的本地技能元数据选择UI设计系统、图标/可访问性或前端设计能力；名称可以是 `ui-design-system`、`ui-icon-system`、`frontend-design` 或其他实际可用技能，不把历史名称当作必需依赖。UI专项只服务当前UI节点。

回写要求：
- 页面结构和组件关系写入 `页面拓扑`。
- 组件状态、交互事件、响应式规则、图标语义写入 `完整细节`。
- 图标库、组件库、关键 UI 文件写入 `实现清单`。
- 截图、浏览器验收、未验证视觉风险写入 `验证证据`。
- UI 质量门禁未完成时，不能在汇报中声称“UI 已完成”或“界面已优化”。

## 选择优先级

优先选择：
1. 当前智能体已经安装的本地技能。
2. 职责与本次需求、模块和风险相符，且来源与版本可核对的技能。
3. 实际具备本次所需输入、工具及证据，读写范围可以受约束的技能。
4. 产出与验收可清晰回写到对应切片，能正确报告失败与未知的技能。

谨慎选择：
- 来源不明、版本不可核对、描述泛化严重的技能；不以安装量、星标或社区完善度评判能力质量。
- 试图接管完整项目流程的总控类技能。
- 要求大范围改写项目结构但无法给出落位证据的技能。

## 调用判定流程

```
遇到功能树节点或架构任务
  → 判断是否出现专业能力触发信号
  → 检查当前智能体是否已有对应技能
  → 有则读取对应技能的最小必要部分
  → 无则按任务架构规则自行补全
  → 所有产出回写到 architecture/index.json 或相关切片
  → 校验是否出现越权扩展或绕过架构文件夹
```
