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

- 比如："leader-only 限制是 `_build_quant_tools()` 函数里的一行 `if role != 'leader': return []`，
  它导致框架在给 Bull/Bear 装配工具时，跳过全部 8 个量化工具，直接返回空列表。"

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
## 为什么要去掉量化工具的 leader-only 限制

### 0. leader-only 限制本身是什么

`_build_quant_tools()` 是框架装配 Agent 工具时调用的函数。里面有一行
`if getattr(ctx, "role", "") != "leader": return []`——只有 leader 角色能拿到
8 个量化工具，Bull/Bear 等 teammate 角色拿到的都是空列表。

### 1. 改了之后的表现（重要性）

Bull 和 Bear 不再"空手"接任务：
- 改之前：Bull/Bear 各有 13 个通用工具（bash、文件、网页搜索），收到 Coordinator
  的分析请求后无法访问任何因子数据，只能浏览工作目录
- 改之后：Bull/Bear 各获得全部 8 个量化工具，Bull 能调 quant_bull_view 做动量分析，
  Bear 能调 quant_bear_view 做风控审查，输出基于真实数据的分析报告

### 2. 不改会怎样（必要性）

- 场景：Coordinator 获取数据 → 计算因子 → 广播"请 Bull/Bear 分析"
- 后果：Bull 和 Bear 没有量化工具，无法访问因子数据。它们只能基于 Coordinator
  消息中的文字描述做"分析"，输出的是 LLM 幻觉而非数据驱动判断。Coordinator
  基于空洞报告做最终决策——多 Agent 架构变成形式主义，多消耗 2/3 token 但决策
  质量反而不如单 Agent
```
