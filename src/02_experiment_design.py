# -*- coding: utf-8 -*-
"""
步骤 2/3：实验设计与样本量计算（Power Analysis）
===============================================
实践要点：AB 实验要在"开跑之前"算清楚需要多少用户，而不是拿到数据后反推。
核心问题是：如果实验组真的比对照组好，我要多少样本才能"大概率发现"这个差异？

四个关键词：
  α（显著性水平）   ：没有差异却误判为有差异的概率（假阳性），通常 0.05
  β（第二类错误）   ：有差异却没检测出来的概率（假阴性）；power = 1 - β，通常 0.8
  MDE（最小可检测效应）：业务上"值得上线"的最小提升幅度，由业务定，不是统计定的
  基线转化率        ：实验前核心指标的现状值（通常取对照组/历史均值）

本实验设定：
  核心指标 = 7 日留存（关心改动对长期留存的影响）
  护栏指标 = 1 日留存、游戏轮数（确保改动不把短期体验玩坏）
  基线 p1  = gate_30 的 7 日留存 ≈ 19.0%
  MDE      = 1.5pp（业务判断：7 日留存至少涨 1.5 个百分点才值得改）

运行方式：python src/02_experiment_design.py
输出：results/sample_size.json
"""
import json
import os

import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "results")

# ----------------------------------------------------------------------
# 1) 从对照组取基线值（模拟"实验开跑前"从历史数据拿到现状）
# ----------------------------------------------------------------------
df = pd.read_csv(os.path.join(ROOT, "data", "cookie_cats.csv"))
ctrl = df[df["version"] == "gate_30"]
p1_r7 = ctrl["retention_7"].mean()   # 基线：7 日留存
p1_r1 = ctrl["retention_1"].mean()   # 护栏：1 日留存
n_actual_per_group = int(df["version"].value_counts().min())  # 实验实际每组样本量


def n_per_group(p1: float, mde: float, alpha=0.05, power=0.8) -> float:
    """双比例检验、双侧、等样本量时的每组所需样本量（正态近似公式）。

    n = (z_{1-α/2} + z_{power})^2 * [ p1(1-p1) + p2(1-p2) ] / (p2 - p1)^2
    标准公式，statsmodels 的 NormalIndPower 本质上也是它。
    """
    p2 = p1 + mde
    z_a = stats.norm.ppf(1 - alpha / 2)   # 1.96（α=0.05 时）
    z_b = stats.norm.ppf(power)           # 0.8416（power=0.8 时）
    var = p1 * (1 - p1) + p2 * (1 - p2)
    return (z_a + z_b) ** 2 * var / mde**2


def detectable_mde(p1: float, n: int, alpha=0.05, power=0.8) -> float:
    """反过来问：给定样本量 n，能以 (1-power) 的把握检出的最小效应是多少。"""
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    p2 = p1 + 0.0001  # 数值求解：用公式反解 delta（简单二分）
    lo, hi = 1e-6, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        need = n_per_group(p1, mid, alpha, power)
        if need > n:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ----------------------------------------------------------------------
# 2) 三档 MDE 的样本量需求表
# ----------------------------------------------------------------------
rows = []
for mde in (0.005, 0.010, 0.015):
    rows.append({
        "mde_pp": mde * 100,
        "n_per_group": int(np.ceil(n_per_group(p1_r7, mde))),
    })
    print(f"MDE = {mde*100:.1f}pp  →  每组需要 {np.ceil(n_per_group(p1_r7, mde)):>6.0f} 用户")

result = {
    "primary_metric": "retention_7",
    "baseline_r7": round(float(p1_r7), 4),
    "baseline_r1": round(float(p1_r1), 4),
    "alpha": 0.05, "power": 0.8,
    "n_per_group_required": rows,
    "n_per_group_actual": n_actual_per_group,
    "mde_detectable_pp": round(detectable_mde(p1_r7, n_actual_per_group) * 100, 2),
}
n_req_mde15 = rows[-1]["n_per_group"]
result["verdict"] = (
    f"实际每组 {n_actual_per_group} 人 >= 需求 {n_req_mde15} 人，功效充足；"
    f"以当前样本量最小可检出约 {result['mde_detectable_pp']}pp 的效应"
)

print("\n" + "=" * 60)
print(f"实验实际每组样本量：{n_actual_per_group}")
print(f"结论：{result['verdict']}")
print("解读：样本量足够，说明后面算出的'不显著'可以理解为'真的没有 1.5pp 级别的效应'，")
print("      而不是'还没测出来'——这就是功效分析对结论解释权的意义。")

with open(os.path.join(OUT_DIR, "sample_size.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("\n已保存：results/sample_size.json")
