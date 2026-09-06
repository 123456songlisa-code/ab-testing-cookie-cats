# AB 实验全流程分析：关卡后移对玩家留存的影响

> 基于 90,189 名玩家的真实 A/B 实验数据，完整走一遍数据团队标准的实验评估流程：
> **数据校验（SRM/AA）→ 功效分析 → 假设检验 → 分层分析 → 上线决策**，并交付可交互的实验监控看板。

[![Python](https://img.shields.io/badge/Python-3.8-blue)]() [![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red)]() [![SQL](https://img.shields.io/badge/SQL-DuckDB%20%2F%20Hive--style-orange)]()

---

## 一句话结论

**不建议上线**：把第一道闸门从 30 关移到 40 关，核心指标 7 日留存显著**下降 0.82pp**（19.02% → 18.20%，p=0.0016，95% CI [-1.33, -0.31]），且负效应集中在 11~150 轮的中度玩家，没有任何子指标出现正向补偿。

| 指标 | gate_30（对照） | gate_40（实验） | 差异 | p 值 | 95% CI | 结论 |
|---|---|---|---|---|---|---|
| **7 日留存（核心）** | 19.02% | 18.20% | **-0.82pp** | 0.0016 | [-1.33, -0.31]pp | 显著·负向 |
| 1 日留存（护栏） | 44.82% | 44.23% | -0.59pp | 0.0744 | [-1.25, +0.05]pp | 不显著 |
| 游戏轮数中位数（护栏） | 17 | 16 | -1 轮 | 0.0502* | — | 未见正向补偿 |

\* Mann-Whitney U 检验（对离群点稳健；数据含玩了 49,854 轮的极端用户）。

## 业务背景

三消手游《Cookie Cats》用"等待闸门"（玩到某关卡后强制等待或内购跳过）做商业化与留存调控。产品团队提出：把第一道闸门从第 30 关后移到第 40 关，让新手玩得更久再遇到卡点，期望提升长期留存。上线前需要数据团队用 A/B 实验回答：**该不该改？**

## 分析流程

```
原始实验数据 (90,189 用户)
      │
      ▼
① 数据质量校验 ── 缺失/重复/主键检查
      │            ★ SRM 检验：分组比例 1 : 1.0177，χ²=6.90，p=0.0086 → 分流异常，结论需打折
      │            ★ AA 检验：20 次空实验 1 次显著，假阳性率 5% ≈ 设计水平，随机性可用
      ▼
② 功效分析 ────── MDE=1.5pp、α=0.05、power=0.8 时每组仅需 11,063 人
      │            实际每组 44,700 人，功效充足；最小可检出效应 ≈ 0.74pp
      ▼
③ 假设检验 ────── 双比例 z 检验 + 10,000 次 Bootstrap 置信区间
      │            7 日留存：z=3.16，p=0.0016，差值 CI 全在 0 左侧 → 负效应为真
      ▼
④ 分层分析 ────── 按活跃度分 5 层，检查辛普森悖论
      │            负效应集中在 11-50 轮（-1.21pp, p=0.0007）与 51-150 轮（-3.18pp, p=0.0001）
      │            轻度/重度玩家不受影响 → 闸门后移伤害的恰是"正在形成习惯"的人群
      ▼
⑤ 上线决策 ────── 统计显著 ≠ 业务值得；无子指标补偿、无正向分层 → 建议维持 30 关
```

## 仓库结构

```
├── data/                     # 原始实验数据（Kaggle · Cookie Cats, 90,189 行）
├── src/
│   ├── 01_data_validation.py # 数据体检：缺失/重复/SRM/AA/异常值
│   ├── 02_experiment_design.py # 功效分析：样本量计算（公式 + 三档 MDE 敏感性）
│   ├── 03_hypothesis_testing.py# z 检验 + Bootstrap + 分层 + 决策 + 出图
│   └── run_sql.py            # SQL 模块运行器
├── sql/
│   └── retention_metrics.sql # SQL 复刻核心指标（DuckDB 语法，Hive 对照注释）
├── dashboard/
│   └── app.py                # Streamlit 实验监控看板（健康度/核心指标/决策三视图）
├── results/                  # 全部中间结果（JSON/CSV）与图表，可复现可核对
└── README.md
```

## 快速复现

```bash
pip install -r requirements.txt
python src/01_data_validation.py     # 数据体检 + SRM/AA
python src/02_experiment_design.py   # 功效分析
python src/03_hypothesis_testing.py  # 检验 + 分层 + 决策 + 图表
python src/run_sql.py                # SQL 版指标计算（结果与 Python 完全一致）
streamlit run dashboard/app.py       # 启动看板 → http://localhost:8501
```

## 看板预览

**在线看板（Streamlit Cloud 已部署）**：[https://ab-testing-cookie-cats-ngcro4bktjxhsign2xbfad.streamlit.app](https://ab-testing-cookie-cats-ngcro4bktjxhsign2xbfad.streamlit.app/)

三个视图：① 实验健康度（SRM / AA / 功效核对）→ ② 核心指标（留存对比 + 置信区间）→ ③ 分层分析与上线决策。

本地运行 `streamlit run dashboard/app.py` → http://localhost:8501

| 实验健康度（SRM/AA） | 核心指标与置信区间 | 分层与决策 |
|---|---|---|
| 分流比例、空实验假阳性率、功效核对 | 留存对比 + p 值 + Bootstrap CI | 负效应定位 + 上线建议 |

静态图（分析脚本自动生成）：`results/charts/`

## 数据来源

Kaggle 公开数据集 [Mobile Games A/B Testing - Cookie Cats](https://www.kaggle.com/datasets/mursideyarkin/mobile-games-ab-testing-cookie-cats)（90,189 玩家：userid、版本分组、累计游戏轮数、1/7 日留存）。仅用于技术展示。
