# Codex / Claude 两方开发工作流

| 字段 | 值 |
|---|---|
| 版本 | `2.0.0` |
| 状态 | `ACTIVE` |
| 计划与验收 | Codex |
| 执行与开发 | Claude |
| 事实源 | `VALIDATION.md` |
| 路线源 | `DEVELOPMENT_PLAN.md` |
| 当前交接 | `.claude/discussion.md` |
| 版本历史 | `history/README.md` |

## 1. 目的与双方关系

本工作流只定义两个开发协作者。Codex 负责计划、范围冻结、独立审查、验收和
交付；Claude 负责只读定位、实现、测试和实现证据。双方是平等协作者，没有
一般性的上下级关系，权限只绑定任务阶段。

项目运行时的 Coordinator、Alpha Analyst、Risk & Evidence Analyst 是金融业务
团队，不属于本开发工作流。定位、实现、审查也是阶段，不是额外常驻 Agent。

## 2. 当前输入

- 新任务先读本文件和 `coordination/active/<TASK-ID>.md`。
- Codex 在建立计划时读取 `AGENTS.md`、`CLAUDE.md`、`DEVELOPMENT_PLAN.md`、
  `VALIDATION.md` 和当前 discussion，把必要约束写入任务契约。
- Claude 默认只读任务、定位所需源码/测试和生成的最小上下文，不用历史聊天
  猜状态。
- `history/` 是 append-only 版本档案，只在回归、取证、版本总结或显式 history
  任务中读取；它不能解除 blocker 或提高证据等级。

## 3. 状态机与职责

`DRAFT → LOCATED → READY → IMPLEMENTED → REVIEWED → VERIFIED → CLOSED`

任一阶段可进入 `BLOCKED`。

| 状态推进 | 责任方 | 要求 |
|---|---|---|
| 建立 `DRAFT` | Codex | 目标、非目标、风险、初始范围和验收条件 |
| `LOCATED` | Claude 提交，Codex确认 | 只读位置、调用点、测试、未知项和建议白名单 |
| `READY` | Codex | 定位验收，精确白名单和完整基线已冻结 |
| `IMPLEMENTED` | Claude | 最小改动、负向测试、命令/退出码和实现工件 |
| `REVIEWED` | Codex | 独立差异审查、反例、P0-P3 和明确 verdict |
| `VERIFIED/CLOSED` | Codex | 范围、证据、测试、限制和交付条件全部核对 |

Claude 不设置 `VERIFIED/CLOSED`；Codex 不在缺实现工件时推断实现成功。

## 4. 必需工件

- `coordination/active/<TASK-ID>.md`：Git 管理的任务契约、白名单和阶段记录。
- `output/agent_handoffs/<TASK-ID>/location.json`：Claude 的只读定位结果。
- `output/agent_handoffs/<TASK-ID>/context.md`：可选的确定性最小上下文。
- `output/agent_handoffs/<TASK-ID>/baseline.json`：实现前文件和工作区基线哈希。
- `output/agent_handoffs/<TASK-ID>/implementation.json`：Claude 的改动、命令、
  退出码、结果和限制。
- `output/agent_handoffs/<TASK-ID>/review.json`：Codex 的独立 verdict、P0-P3、
  复验命令和剩余风险。
- `history/v<major>.<minor>_YYYY-MM-DD.md`：真实项目版本关闭后的完整记录；
  不是单任务工件。

`output/` 不提交。任何口头结论、聊天文字或模型多数意见都不能替代这些工件。

## 5. 标准流程

1. Codex 检查 HEAD、分支和工作树，建立任务契约。来源不明修改保持不动。
2. Claude 使用 `rg` 定位定义、直接调用点、测试和安全契约；不改源码，只写
   `location.json`。
3. Codex 验证定位，决定风险和最小写范围；运行 `freeze` 生成基线。写范围与
   其他活动任务重叠时失败关闭。
4. Claude 先补负向回归，再做最小实现；只写 `allowed_files`。
5. Claude 运行目标测试、Ruff/pycompile、`scope-check` 和 `git diff --check`，
   写 `implementation.json`。
6. Codex 在不共享 Claude 实现推理的独立审查回合中读取契约、基线差异和测试
   证据，主动构造反例并写 `review.json`。
7. 若 verdict 为 `MODIFY`，Claude 只修复已接受的问题；新增文件必须由 Codex
   先扩白名单并保留原始基线。若 `ACCEPT`，Codex复验并关闭任务。
8. 涉及生产能力时继续执行 direct/formal/E2E。Mac 无法完成的模型、网络或
   Windows 环境门必须保留为明确外部 gate。
9. 真实事实先写 `VALIDATION.md`；形成项目版本时再写 history/index；最后更新
   README 和 discussion。

## 6. 有界质疑和收敛

Codex 与 Claude 都可质疑计划、冻结范围、实现或验收。有效质疑必须给出争议
命题、证据/反例、受限替代、影响文件和状态、验收与回退。

- 待决期间现行契约继续；只暂停争议范围，无争议工作继续。
- 每方对同一争议最多两次证据交换。第二次回复后必须选择 `ACCEPT`、
  `MODIFY`、`REJECT` 或用户升级。
- 不得把措辞变化包装成新一轮，不得重复无新证据的论点，不得先改后请求授权。
- 裁决顺序：官方/用户契约 → 时间因果与数据安全 → 可复现证据 → 最小可逆
  范围 → 资源成本。
- 技术分歧由 Codex 按验收职责记录结论；这不是一般层级。Claude 提供新证据
  时可建立新版本任务。
- 产品意图、新增外部权限/权威来源或无法在现有契约内解决的重大安全边界才
  升级给用户。

## 7. 风险与停止规则

### LOW

- 不超过 3 个源码/测试文件；不改公共协议、金融时序、资金约束、RPC、Provider
  或进程生命周期；已有明确测试。

### MEDIUM

- 跨 4–8 个文件、文档/开发协议或公共接口；定位置信度低于 0.75；一次实现失败；
  或双方对根因不一致。

### HIGH

- 回测因果、embargo、收益/回撤；Agent 编排、RPC、服务端可信边界；数据源、
  证据链、fail-closed；异步/进程生命周期；提交契约；超过 8 个文件或 250 行
  有效源码修改。

停止规则：

- 相同实现失败连续 2 次停止并转为证据挑战；相同工具调用连续 3 次停止。
- 定位置信度低于 0.75、白名单不清、基线无法重建或关键工件缺失时不实施。
- `scope-check` 越界、JSON 不可解析、状态与文件不一致均为失败，不从文字补推。
- 不向模型传完整行情矩阵、历史 discussion、整个 output 或无关仓库内容。

## 8. 阶段技能

现有三个技能是两方工作流的检查表，不代表额外 Agent：

- Claude 定位阶段：`.agents/skills/local-code-scout/SKILL.md`；
- Claude 实现阶段：`.agents/skills/bounded-code-implementer/SKILL.md`；
- Codex 审查阶段：`.agents/skills/diff-contract-reviewer/SKILL.md`。

旧的模型路由和 provider profile 启动器已退出活动路径。Windows 直接在各自的
Codex 和 Claude 会话中读取当前身份与任务，不再由仓库脚本选择模型供应商。

## 9. Mac / Windows 交付

- 一项任务只在一端修改。Mac 完成并提交后，Windows 进入只读复验；Windows
  若需修正，生成 task-scoped 返回补丁，Mac 应用后再出新版本。
- 每个任务使用独立分支和提交，交付包括 `changes.patch`、Git bundle、
  `BASE_COMMIT.txt`、`HEAD_COMMIT.txt`、`FILES.txt`、验证日志、handoff 工件和
  `SHA256SUMS.txt`。
- Windows 先验 SHA、基线和白名单，再跑测试；不得把 bundle 解包或 Mac 单测
  自动视为 Windows 正式验收。
- 未经用户明确授权不 push、tag 或修改 Windows 主工作区。

## 10. 版本历史

1. 项目版本绑定真实 commit 区间和日期；任务 ID、计划版本和项目版本不混写。
2. 历史文件名固定为 `v<major>.<minor>_YYYY-MM-DD.md`，记录改动、验收、失败、
   限制和 superseded 判断。
3. 既有版本文件不可重写；新证据推翻旧结论时追加带日期 Erratum，并同步更新
   当前 `VALIDATION.md`。
4. 版本关闭顺序：真实验证 → `VALIDATION.md` → history/index → README/discussion。
