# 多模型开发工作流

| 字段 | 值 |
|---|---|
| 版本 | `1.0.0` |
| 状态 | `ACTIVE` |
| 事实源 | `VALIDATION.md` |
| 路线源 | `DEVELOPMENT_PLAN.md` |
| 当前交接 | `.claude/discussion.md` |

## 1. 目的

用本地模型完成代码定位、受限实现和独立审查，只在风险或失败达到阈值时调用云端强模型。模型不依靠长聊天传递状态；每项工作使用版本化任务契约和可重算机器产物。

## 2. 角色与模型解耦

| 执行角色 | 默认模型 | 权限 |
|---|---|---|
| Planner / Arbiter | Codex | 规划、风险分级、裁决、最终验收 |
| Scout | 本地 Qwen | 只读搜索源码；只写 handoff 产物 |
| Builder | Codex 或最小上下文 DeepSeek；Qwen 仅实验性后台任务 | 只修改任务白名单文件 |
| Critic | 本地 Qwen 或独立云端会话 | 只读任务、基线差异和测试证据；结论必须由工件复核 |
| Domain owner | Missed / Goone | 保留 `CLAUDE.md` 中的项目文件所有权 |

Missed/Goone 是项目职责，不绑定某个模型。多个弱模型的多数意见不能替代契约和测试。

### 新会话的身份与事实输入

- 身份只写当前角色、职责、权限边界、任务目标和停止条件。
- 事实只写当前决策所需的版本、状态、证据等级、约束和未决问题，并标明对应事实源。
- “不再”“曾经”“原先”“从 A 改为 B”等身份迁移只保留在 Git、变更记录或 archive；除非迁移本身就是当前任务，不注入新会话。
- 不用旧身份、旧结论或重复背景解释当前身份；模型重启后以任务契约和当前事实源为准。

本地 Qwen 默认承担 Scout 和非阻塞 Critic。2026-08-03 的真实 Builder 在 180 秒内只完成部分文档修改，Critic 也出现“口头声称已写工件但文件不存在”和中文 JSON 编码错误；因此 Qwen 的文本结论只是建议，状态、工件和改动必须由控制器或 Planner 复核。只有任务不阻塞主线、写范围不超过 1 个文件且失败可直接丢弃时，才把 Qwen 用作实验性 Builder。

## 3. 状态机

`DRAFT -> LOCATED -> READY -> IMPLEMENTED -> REVIEWED -> VERIFIED -> CLOSED`

任一阶段可进入 `BLOCKED`。只有 Planner 能把任务置为 `VERIFIED` 或 `CLOSED`。

## 4. 工件

- `coordination/active/<TASK-ID>.md`：Git 管理的任务契约、白名单、验收命令和阶段记录。
- `output/agent_handoffs/<TASK-ID>/location.json`：Scout 定位结果。
- `output/agent_handoffs/<TASK-ID>/context.md`：确定性生成的最小上下文。
- `output/agent_handoffs/<TASK-ID>/baseline.json`：开始实现前的文件哈希。
- `output/agent_handoffs/<TASK-ID>/implementation.json`：Builder 的命令与结果。
- `output/agent_handoffs/<TASK-ID>/review.json`：Critic 的独立结论。

`output/` 不提交。任务关闭后可删除 active 文件，历史由 Git、`VALIDATION.md` 和计划变更记录保留。

## 5. 标准流程

1. Planner 创建任务，写目标、非目标、初始读范围和验收条件。
2. Scout 使用 `rg/Glob/Read` 定位定义、调用点和测试，禁止改源码。
3. Planner 审核定位结果，设置写入白名单并冻结基线。
4. 按风险路由 Builder；Builder 先补负向测试，再做最小实现。
5. Builder 运行目标测试和 `scope-check`，记录退出码。
6. Critic 在新会话中只读任务、基线差异和测试证据，提交反例。
7. Planner 验收；涉及量化生产逻辑时继续执行 direct/formal 和 E2E。
8. 先更新 `VALIDATION.md`，再写 README 摘要和 discussion 阶段结论。

`freeze` 会检查其他处于 READY/IMPLEMENTED/REVIEWED/VERIFIED 的 active task；只要具体写入文件重叠，就失败关闭。并行任务必须先拆开文件所有权，不能依靠聊天约定避免覆盖。

角色启动入口：

```powershell
.\scripts\agent-role.cmd TASK-ID scout
.\scripts\agent-role.cmd TASK-ID builder
.\scripts\agent-role.cmd TASK-ID critic
```

启动器当前仍会把 LOW Builder 自动映射到 Qwen，但该默认值只用于后台实验，不能作为同步主线路由；阻塞主线的 LOW 修改由 Codex 执行，或显式 `--profile deepseek` 发送最小任务包。MEDIUM 默认 DeepSeek，HIGH 和 UNKNOWN 在 Builder 启动前失败并要求 Planner 裁决。`--print` 默认 180 秒硬超时；任何超时、缺工件、状态与文件不一致或乱码都按失败处理，不能从模型文字中补推成功。

角色启动器默认使用 Claude Code `--bare`，避免自动注入完整 `CLAUDE.md`、插件、历史记忆和后台预取；角色需要的项目约束由任务契约与对应 skill 显式提供。普通人工 Claude 会话仍可用 `scripts/claude-qwen.cmd` / `scripts/claude-deepseek.cmd` 加载完整项目环境。

## 6. 风险路由

### LOW：本地 Builder

- 不超过 3 个源码/测试文件；
- 不改变公共协议；
- 不涉及金融时序、资金约束、Agent RPC、数据 Provider 或并发生命周期；
- 已有明确目标测试。

### MEDIUM：DeepSeek 最小上下文实现

- 跨 4 至 8 个文件或公共接口；
- Scout 置信度低于 `0.75`；
- 本地 Builder 第一次失败；
- Builder 与 Critic 对根因不一致。

DeepSeek 只接收任务契约、`context.md`、当前差异和失败断言，不默认读取整个仓库。

### HIGH：Codex 重新规划，强模型实现或复核

- 回测因果、embargo、收益或回撤口径；
- Agent 编排、RPC、服务端缓存可信边界；
- 数据源、证据链、fail-closed；
- 异步/进程生命周期、提交契约；
- 超过 8 个文件或 250 行有效修改。

## 7. 预算和停止规则

- Scout：最多 12 次搜索/读取调用，输出不超过 1,500 tokens。
- Builder：默认上下文不超过 12,000 tokens，只开放必要工具。
- Critic：只读契约、差异和测试，输出不超过 1,000 tokens。
- 云端任务包目标不超过 20,000 tokens。
- 相同失败连续 2 次升级；相同调用连续 3 次停止。
- 不把完整日志、行情矩阵、历史 discussion 或整个 `output/` 送入模型。
- 模型写出的任务状态不自证有效：阶段推进前必须检查要求工件存在、JSON 可解析、scope-check 通过，并由 Planner 核对关键声明与文件系统一致。

## 8. discussion 使用规则

Agent 可以通过任务工件直接交接；`.claude/discussion.md` 只记录用户需要看到的阶段事件：任务建立、风险升级、实现待审、验收裁决和阻塞。不得把逐次搜索、完整日志或重复上下文写入 discussion。所有消息继续遵守 `CLAUDE.md` 的对话格式。

## 9. 多 Provider 并行

CC Switch 仍可用于交互式默认 Provider，但自动协作不读取其全局单选状态。不同 Claude Code 进程使用独立 `CLAUDE_CONFIG_DIR`：

```powershell
.\scripts\claude-qwen.ps1
.\scripts\claude-deepseek.ps1
```

两者拥有独立 settings、会话和历史，可在不同终端同时运行。密钥只存放在用户目录的 profile 中，不写入 Git。
