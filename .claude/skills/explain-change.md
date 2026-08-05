---
name: explain-change
description: When proposing any fix, optimization, or refactor, explain WHAT was changed and WHY — in three sections: what the thing is, what improves (importance), what breaks if skipped (necessity).
trigger: proposing code changes, fixes, optimizations, refactors, or architecture improvements
---

# Explain-Change Skill

当 Claude 提出任何代码修改时，必须用以下三段式结构向 Canaan 解释：

## 输出格式（必须严格遵守）

```
## 为什么要 <修改概述>

### 0. <被改的东西>本身是什么

<用一两句话解释被修改/删除/新增的机制是什么，让读者有一个基础概念。>

- 比如："角色工具过滤是 `_build_quant_tools()` 按成员名保留专属 RPC 的逻辑；
  它保证 Alpha 只能看到 `quant_alpha_view`，Risk & Evidence 只能看到
  `quant_risk_evidence_view`。"

### 1. 改了之后的表现（重要性）

<改完后用户/系统能看到什么具体变化？用数据或可观测行为描述。>

- 改之前：<具体数字或行为>
- 改之后：<具体数字或行为>

### 2. 不改会怎样（必要性）

<不改的情况下会出现什么具体问题？用场景说明，不是抽象的风险描述。>

- 场景：<在什么条件下触发>
- 后果：<用户看到什么/数据出什么问题>
```

## 规则

- **三段缺一不可**。如果某个修改没必要（比如纯格式化），跳过此 skill，直接说"纯格式化，无需解释"。
- **第 0 段要短**：一两句话说清楚"改的那个东西是什么"。不要展开，不要评价，只是定义。
- **用具体数字**。不说"性能提升"，说"从 50s 降到 0.7s"。
- **用场景化语言**。不说"可能导致数据不一致"，说"当网络中断时，Agent 会陷入死循环，每 2 秒重复调用同一工具"。
- **中文输出**。

## 示例

```
## 为什么要收紧分析师的量化工具权限

### 0. 角色工具过滤本身是什么

`_build_quant_tools()` 是框架装配 Agent 工具时调用的函数。它根据成员名从固定
8 个量化 RPC 中筛选权限：Coordinator 获得确定性流水线工具，Alpha 与
Risk & Evidence 各自只获得一个视角工具。

### 1. 改了之后的表现（重要性）

两位分析师能访问真实因子，同时不能越过职责边界：

- 改之前：任意 teammate 可能继承全部 8 个量化工具，可以绕过 Coordinator
  直接触发选股、配仓、回测或报告。
- 改之后：Alpha 只获得 `quant_alpha_view`，Risk & Evidence 只获得
  `quant_risk_evidence_view`；正式流水线仍由 Coordinator 独占 6 个确定性阶段。

### 2. 不改会怎样（必要性）

- 场景：Coordinator 完成因子计算后并行委派两个分析师。
- 后果：若没有角色工具过滤，分析师既可能读不到专属因子，也可能自行调用
  `quant_select_stocks` 或 `quant_allocate_positions`。这会让消息参数覆盖服务端缓存，
  破坏角色归属和确定性数据流，使形式上的 8/8 RPC 不能证明正式路径有效。
```
