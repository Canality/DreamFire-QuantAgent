---
name: submission-conventions
description: Every time a version is completed or deliverables are produced, automatically apply these naming, directory, and submission conventions without being reminded.
trigger: completing a code version, generating deliverables, creating zip files, or finishing a round of fixes
---

# Submission Conventions Skill

当完成一个版本的代码修改或生成交付物时，自动执行以下规范，不需要 Canaan 提醒。

---

## 一、Zip 命名规范

```
Dream Fire_【MMDD日期】-【当天第几次提交】.zip
```

- 例: `Dream Fire_0716-第2次提交.zip`
- 日期用 4 位数字 (MMDD)，不含年份
- 第几次提交用中文 "第X次"
- 团队名 "Dream Fire" 中英文之间有空格

## 二、版本产物规范

每次版本迭代完成后，必须在 `策略实验/` 下创建版本目录：

### 目录命名

```
策略实验/v{major}.{minor}_{MMDD日期}-{简短描述}/
```

- 例: `策略实验/v2.1_0717-多源数据与Bug修复/`

### 每个版本必须包含

| 文件 | 内容 |
|------|------|
| `评分.json` | 自评估得分详情 (total_score + 各维度分解) |
| `投资组合.json` | 最终选股与仓位 (stock_code → weight) |
| `投资报告.md` | 完整量化分析报告 (选股逻辑+仓位决策+分析过程+风险评估+组合明细) |
| `变更说明.md` | 本版本相对上一版本的改动 |
| `资源消耗.md` | Token 统计 + 运行时 + CPU/内存 |
| `框架优化.md` | 框架修改说明 (如有) |

### 策略实验目录 README

维护 `策略实验/README.md`，包含版本历史表：

| 版本 | 日期 | 总分 | 核心变化 |
|------|------|------|----------|

## 三、竞赛交付物清单

### 6 项必须提交的内容

1. **Agent 完整代码** — 所有业务代码 + 配置 + requirements.txt
2. **量化投资报告** — 选股逻辑、仓位决策、分析过程、风险评估、投资组合明细
3. **投资组合结果** — `Portfolio.json`，格式 `{"股票代码": 权重, ...}`
4. **资源消耗日志** — Token 用量、端到端运行时、CPU/GPU峰值利用率
5. **可复现说明文档** — README: 环境配置、执行步骤、参数释义、常见问题
6. **框架优化说明** — 对 openJiuwen 框架的修改及效果对比 (如有)

### 交付物位置

```
output/submission/
├── Portfolio.json
├── 量化投资报告.md
├── 资源消耗日志.md
├── 框架优化说明.md
└── (README.md 在项目根目录)
```

## 四、Git 提交规范

- 提交 message 用英文，描述本版本的核心变化
- 每完成一轮修改立即提交并推送到 `https://github.com/Canality/DreamFire-QuantAgent`（私有仓库）
- **不要提交** `.venv/`、`__pycache__/`、`*.pyc`、`output/*`（submission 除外）、API key 明文

## 五、版本完成检查清单

每完成一个版本，确认以下全部完成：

- [ ] 评分.py 已运行，最新分数已保存
- [ ] `策略实验/vX.Y_MMDD-描述/` 目录已创建
- [ ] 评分.json、投资组合.json、投资报告.md、变更说明.md 已填充
- [ ] Zip 包已打包 (按命名规范)
- [ ] Git 已提交并推送到 GitHub
- [ ] `策略实验/README.md` 版本表已更新
