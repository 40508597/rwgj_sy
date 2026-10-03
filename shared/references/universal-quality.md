# 通用架构决策、实现质量与验证

## 适用与边界

用于架构选择、跨模块修改、质量检查和完整交付。只读、小任务按 LAYER 的范围降级；不强迫所有任务生成完整质量报告。

核心不设项目语言、文件后缀、框架或 IDE 白名单；易语言、专用工程、二进制工程单元、无后缀文件和混合项目都能接入。Python 是随包工具的运行时，不是被检查项目的语言要求。核心处理统一事实与规则，不声称直接解析任意工程格式。按能取得的事实选择源码解析、工程导出、已有工具结果或运行测试；不能采集时记录 unknown。

## 架构决策

影响模块边界、数据归属、关键依赖、运行形态或重大质量目标时，记录：问题与驱动、硬约束、可观察的质量场景、至少两个合理候选（含保持现状，如适用）、各自收益/代价、选择理由、接受的负面后果、验证方式和重新评估条件。不要编造规模、SLO、法规、预算或团队能力。没有合理替代方案时说明原因并人工审查，不编造第二个选项凑数。

把可执行的决策转换成项目规则，例如禁止依赖、允许关系、可接受指标范围和验收命令。自动工具只验证记录完整性、结构一致性和可执行规则；选择是否适合项目仍需基于实际约束的审查。

## 事实协议

策略和事实保存在调用方项目的质量目录；默认路径是 architecture/quality/policy.json 与 architecture/quality/facts.json，也可向检查 CLI 显式传入项目内其他路径。不要写入全局能力包。模板位于 `../assets/quality-policy-example.json` 和 `../assets/quality-facts-template.json`，必须按当前任务范围调整，模板本身不是已验证证据。

事实根包含 schema_version=1、sources、modules、dependencies、metrics、decisions。标识符是项目自定义字符串；实现单元不要求是传统源码函数。检查不会按语言猜测输入格式。

facts、policy 和执行 receipt 的 JSON 读取拒绝任何层级的重复键及 NaN/Infinity，防止后出现的值静默覆盖 origin、required 或 returncode；歧义输入返回 unknown。

每个 source 包含：

- id：唯一标识。
- origin：observed 或 declared。人工声明、AI 推断使用 declared，不能充当代码观察。
- tool：name、version；说明实际采集工具或导出流程。
- capabilities：如 dependencies:import、metric、crap、decision。
- scope：本次成功采集的模块/实现单元/决策 ID。
- complete：只有预定范围已完整取得时才为 true。
- errors、excluded：显式数组；有失败、排除或缺省时无法证明完整性。
- input_hashes：非空映射，项目相对文件路径 → SHA256。绑定工程文件、导出输入、必要配置等选定输入；不自动代表全项目。

modules 是唯一模块 ID 列表。dependencies 的每条记录为 from、to、kind、source，可补充 location。导入、调用、构建、数据访问、运行时通信分别使用不同 kind，不混合判定。

metrics 的每条记录为 unit、name、value、method、source；覆盖率额外使用 scale=percent。保留位置和外部原始报告便于追查。指标输入必须来自同一源快照及选定实现单元，不能用全项目数字替代函数数字。

外部采集器承担事实提取责任。input_hashes、工具身份和 complete 能帮助核对范围与新鲜度，不能认证采集器诚实、证明导出无遗漏或防止一致伪造。声明与观察必须分开；采集失败不填空数组冒充“无问题”。

## 确定性检查

运行 `../scripts/check_project_quality.py`，参数为 PROJECT、可选 --facts/--policy、--json。公开函数 evaluate_project(project, facts, policy) 方便调用；同一事实、规则及输入文件内容，得到稳定的规则结果。

policy 根是 schema_version=1、rules（唯一 id）。每个规则显式提供 check、required 布尔值、severity。required 决定是否阻断，severity 是显示优先级；required=false 的失败或未知仍在报告中，不能从覆盖统计删除。

先用 resolve_tool 定位工具绝对路径，再在调用方项目运行，例如：

```text
python "<check_project_quality_path>" "<项目根>" --facts architecture/quality/facts.json --policy architecture/quality/policy.json --json
python "<run_verification_path>" "<项目根>" --output architecture/quality/test-receipt.json --input "<选定工程文件>" --timeout 60 -- "<已有验证程序>" "<参数>"
python "<gate_check_path>" "<项目根>" --quality-required --json
```

需要直接调用检查函数时，把实际导出的事实与项目策略作为对象传入 `evaluate_project(Path(项目根), facts, policy)`，读取返回值的 status、code、checks 和 coverage。该函数不执行工程代码；它检查已采集事实及文件绑定。已有工程工具也可直接产出同样的 JSON 协议，无需改用 Python 编写业务项目。

| check | 必需参数 | 实际检查范围 |
|---|---|---|
| dependency | source、scope、kind、allow（模块 ID 二元组），可选 forbid | 检查选定模块的指定关系，默认只允许明确列出的边 |
| acyclic | source、scope、kind | 检查指定关系、选定模块内的循环，含自环 |
| metric | source、scope、metric、method、min 或 max | 每个选定单元必须有唯一、同口径的实测值 |
| crap | source、scope、coverage_method、min 或 max | 由指定单元的实测复杂度和覆盖率计算风险指标 |
| execution | receipt、inputs、command（精确 argv） | 复核实际执行收据、必需输入及当前文件快照；绝不执行收据中的命令 |
| decision | source、scope（决策 ID） | 核对决策记录的候选、取舍、理由和验证字段，不能判断方案最优 |

decision 记录包含 id、source、drivers、constraints、options、selected、reason、negative_consequences、validation、revisit；每个 option 有 id、benefits、costs。无硬约束也应写明“无额外硬约束”并说明依据。

只有一个合理候选时，options 保留真实的一项，另提供 `single_option_exception`：`{"reason":"没有合理替代的具体原因","review":{"status":"approved","reviewer":"实际审查者或项目已有审查记录标识","evidence":["实际审查记录的唯一引用"]}}`。reason、reviewer 必须是非空字符串，evidence 必须是非空且不重复的字符串引用数组。缺少例外仍为 fail，格式错误为 unknown；review.status 为 pending 时 unknown，为 rejected 时 fail，approved 且其余决策字段齐全才结构 pass。零候选不能豁免。使用已有授权项目审查记录即可，不要求每次向用户重新确认，也不能编造人工审查。审查记录引用不认证人的身份，不证明方案最优；合理替代是否确实不存在仍需工程审查。既有 source 的 observed 与快照哈希绑定约定继续适用。

CRAP 使用连续公式 c² × (1 − coverage_percent/100)³ + c；c 来自 method=cyclomatic 的正整数 complexity，coverage 来自明确的 coverage_method、scale=percent 的 [0,100] 实测值。缺值、重复值、布尔/非有限值、不同单元或错误单位都不能算作通过。阈值由项目选定，不能跨工具口径排名。此实现不采用覆盖率 ≥95% 时的截断捷径，可能与采用该捷径的外部工具有差异。公式核对来源：[php-code-coverage CrapIndex](https://github.com/sebastianbergmann/php-code-coverage/blob/main/src/Node/CrapIndex.php)；输入意义见 [PHPUnit 代码覆盖率文档](https://docs.phpunit.de/en/12.5/code-coverage.html)。

## 真实执行证据

`../scripts/run_verification.py` 的用法是 PROJECT --output RECEIPT --input RELPATH（可重复）--timeout SECONDS -- COMMAND ARGS。仅执行已获任务授权的显式命令，shell=False；不拼接 shell 字符串。构建、测试、分析器或项目自己的验证程序均可接入，不指定项目语言。

收据记录选定输入前后哈希、命令、项目目录、工具版本、时间、返回码、完整 stdout/stderr 及原始字节。命令成功且输入未变为 pass；命令非零为 fail；缺输入、启动失败、超时或输入改变为 unknown。完整执行结果不能证明测试覆盖充分；GUI 手检仍记录实际证据和未验证项，不伪造命令收据。

收据不是签名；不能证明环境、外部服务或运行中修改后恢复的输入未变。timeout 约束顶层命令等待，不承诺停止所有后代进程；调用项目自己的可清理测试命令，出现残留进程时记录并处理。输出不可覆盖选定输入。

## 故意制造问题验收检查器

`../scripts/run_quality_probes.py` 读取项目内 suite，逐例复制 baseline 和 mutant 到项目外的新 workspace，按预先固定的精确字节替换引入问题，实际运行显式检查命令。任意扩展名、文本或二进制输入均可接入；不是自动理解任意语言的语法变异器，也不是操作系统安全沙箱。

suite 包含 schema_version=1、唯一 cases；每例提供 id、input、old_base64、new_base64、check_id、command（argv，支持 {project} 指向隔离副本）和可选 timeout。旧字节必须只出现一次，新旧不同；原项目不修改。仅使用已授权、能在隔离副本执行的命令，不运行有外部生产副作用的程序。

命中要求：正常基线成功且目标 check 通过；变异真实改变输入；变异后工具正常返回失败并准确指出目标 check。检查器崩溃、超时、无关检查失败、基线已失败都不算检出。报告固定 cases_total，并逐例保留 detected/missed/invalid/unknown；不删除不利样例。编译类坏样例只能证明编译检查，不证明业务测试有效性；业务样例应能正常构建而行为错误。

## 收尾门禁

完整实现交付运行 `../scripts/gate_check.py` PROJECT --quality-required --json。项目存在 policy 或 facts 时，即使不带该参数也自动加入通用质量检查；缺另一个文件为 unknown。已知必需失败优先返回 1；否则任一必需未知返回 2；全部必需通过返回 0。

兼容旧项目时不带参数且没有质量配置的旧门禁只覆盖旧架构检查，输出明确提示，不能据此声明通用质量已通过。旧阶段/证据格式检查、依赖规则、实际运行证据是不同结论。

通用质量启用后，漂移扫描采用 --all-files；所有声明文件一直核查存在性，不按后缀过滤。一键项目验证也实际运行 --all-files --json，保留原始扫描输出，并只按声明文件缺失阻断；输入、范围或返回码与清单矛盾返回 unknown。未登记文件仍是提示，因为生成物、日志、文档可能不属于业务实现；对必须登记的实现单元使用显式清单与项目规则，不把所有磁盘文件自动判为业务代码。报告分别说明已检规则结果、未知规则和范围，不把未检查范围算成高分。
