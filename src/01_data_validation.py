# -*- coding: utf-8 -*-
"""
步骤 1/3：数据质量校验（Data Validation）
=========================================
实践要点：拿到实验数据不要直接算 p 值。
真实工作中，约 10%~20% 的实验数据本身就有问题（埋点缺失、分流 bug、爬虫流量），
用有问题的数据做检验，结论一定是错的。所以第一步永远是"体检"，体检项目包括：

  1) 基础检查：行数、缺失值、主键重复（一个用户必须只有一行记录）
  2) SRM 检验（Sample Ratio Mismatch，样本比例不匹配）：
     分流平台承诺 50/50，如果实际比例显著偏离 1:1，说明分流或埋点出了问题，
     此时任何组间差异都可能是"分流不均"造成的，检验结果不可信。
  3) AA 检验：把两组数据混在一起随机重新拆成两半，跑一遍检验。
     "空实验"理论上不该显著；重复 20 次，显著次数应约等于 5%（α 水平）。
  4) 异常值检查：离群点（如本数据中玩了 49854 轮的玩家）会污染均值类指标。

运行方式：python src/01_data_validation.py
输出：控制台报告 + results/srm_check.json + results/charts/game_rounds_dist.png
"""
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 无界面环境也能出图
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "cookie_cats.csv")
OUT_DIR = os.path.join(ROOT, "results")
CHART_DIR = os.path.join(OUT_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)

df = pd.read_csv(DATA_PATH)
report = {}

# ----------------------------------------------------------------------
# 1) 基础质量检查
# ----------------------------------------------------------------------
print("=" * 60)
print("步骤 1：基础质量检查")
print("=" * 60)
report["n_rows"] = int(df.shape[0])
report["n_nulls"] = int(df.isnull().sum().sum())
report["n_dup_userid"] = int(df["userid"].duplicated().sum())
print(f"总行数          : {report['n_rows']}")
print(f"缺失值总数      : {report['n_nulls']}  （要求 = 0）")
print(f"userid 重复数   : {report['n_dup_userid']}  （要求 = 0，否则'用户'这个分析单元不成立）")

# ----------------------------------------------------------------------
# 2) SRM 检验 —— 本项目最重要的一个体检项
# ----------------------------------------------------------------------
print("\n" + "=" * 60)
print("步骤 2：SRM 检验（样本比例是否显著偏离 1:1）")
print("=" * 60)
group_counts = df["version"].value_counts()
n30, n40 = int(group_counts["gate_30"]), int(group_counts["gate_40"])
n_total = n30 + n40

# 原假设 H0：两组比例 = 1:1（分流平台承诺的比例）
# 用卡方拟合优度检验，观察值 [n30, n40]，期望值 [n/2, n/2]
chi2, p_srm = stats.chisquare(f_obs=[n30, n40], f_exp=[n_total / 2, n_total / 2])
ratio = n40 / n30

report["srm"] = {
    "gate_30": n30, "gate_40": n40,
    "ratio_gate40_vs_gate30": round(ratio, 4),
    "chi2": round(float(chi2), 2), "p_value": round(float(p_srm), 4),
    "conclusion": "SRM 显著，分流存在异常，结论需谨慎" if p_srm < 0.05 else "分流正常",
}
print(f"gate_30 = {n30}，gate_40 = {n40}，实际比例 = 1 : {ratio:.4f}")
print(f"卡方 = {chi2:.2f}，p 值 = {p_srm:.4f}")
print(f"结论   : {report['srm']['conclusion']}")
print("解读   : p<0.05 说明'比例偏离 1:1'很难用随机波动解释，")
print("         通常怀疑：埋点丢失、重定向失败、分流哈希错位、机器人流量。")
print("         这正是真实实验和教科书数据的区别——必须先归因再下结论。")

# ----------------------------------------------------------------------
# 3) AA 检验（空实验检验）
# ----------------------------------------------------------------------
print("\n" + "=" * 60)
print("步骤 3：AA 检验（重复 20 次空实验，观察假阳性率）")
print("=" * 60)
rng = np.random.default_rng(42)
n_sims, alpha = 20, 0.05
sig_count = 0
p_values = []
pooled = df["retention_7"].to_numpy()  # 用 7 日留存做空实验
for _ in range(n_sims):
    idx = rng.permutation(len(pooled))
    half = len(pooled) // 2
    succ = [int(pooled[idx[:half]].sum()), int(pooled[idx[half:]].sum())]
    cnt = [half, len(pooled) - half]
    _, p = proportions_ztest(succ, cnt)
    p_values.append(p)
    if p < alpha:
        sig_count += 1

report["aa_test"] = {
    "n_sims": n_sims, "n_significant": sig_count,
    "false_positive_rate": round(sig_count / n_sims, 3),
    "interpretation": "接近 5% 的设计水平，分流随机性可用" if sig_count / n_sims <= 0.15 else "假阳性率偏高，分流可能有问题",
}
print(f"20 次空实验中显著（p<{alpha}）的次数：{sig_count} 次，经验假阳性率 = {sig_count / n_sims:.0%}")
print("解读   : α=0.05 的含义就是'即使没有差异，也有 5% 概率误报'，")
print("         所以空实验显著 1~2 次属于正常，显著 10 次才说明分流真有问题。")

# ----------------------------------------------------------------------
# 4) 异常值检查：sum_gamerounds
# ----------------------------------------------------------------------
print("\n" + "=" * 60)
print("步骤 4：异常值检查（sum_gamerounds 累计游戏轮数）")
print("=" * 60)
r = df["sum_gamerounds"].describe(percentiles=[0.5, 0.99, 0.999])
report["game_rounds"] = {
    "median": float(r["50%"]), "p99": float(r["99%"]), "p999": float(r["99.9%"]),
    "max": float(r["max"]),
}
print(r[["50%", "99%", "99.9%", "max"]].round(1))
print(f"解读   : 中位数只有 {r['50%']:.0f} 轮，但最大值高达 {r['max']:.0f} 轮，")
print("         极端离群点会把均值拉爆，所以游戏轮数用'中位数/分位数'描述更稳健，")
print("         假设检验也改用对离群点稳健的 Mann-Whitney U 检验（见步骤 3 脚本）。")

# 极端值截断后的分布图（只用于展示，检验在 03 脚本中另做）
plt.figure(figsize=(8, 4.5))
clip = int(r["99.9%"])
for v, c in [("gate_30", "#4C72B0"), ("gate_40", "#DD8452")]:
    vals = df.loc[df["version"] == v, "sum_gamerounds"].clip(upper=clip)
    plt.hist(vals, bins=50, alpha=0.55, label=v, color=c, density=True)
plt.axvline(df["sum_gamerounds"].median(), color="red", ls="--", lw=1, label="overall median")
plt.title("Distribution of game rounds (clipped at P99.9) by group")
plt.xlabel("sum_gamerounds (clipped)")
plt.ylabel("density")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(CHART_DIR, "game_rounds_dist.png"), dpi=150)
plt.close()

with open(os.path.join(OUT_DIR, "srm_check.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\n已保存：results/srm_check.json、results/charts/game_rounds_dist.png")
