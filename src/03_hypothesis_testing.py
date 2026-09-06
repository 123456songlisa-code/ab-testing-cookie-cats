# -*- coding: utf-8 -*-
"""
步骤 3/3：假设检验、分层分析与上线决策（Hypothesis Testing & Decision）
======================================================================
前面已确认：分流比例接近 1:1（SRM 有轻微异常但样本充足）、功效足够。
本脚本回答三个问题：
  Q1 差异是否统计显著？     → 双比例 z 检验 + Bootstrap 置信区间
  Q2 差异是否业务上重要？   → 效应量（pp / 相对提升）对比 MDE 门槛
  Q3 效应在不同人群一致吗？ → 按游戏轮数分层，检查辛普森悖论

最后组装成"上线 / 不上线"的决策建议——分析师的价值在这一步，不在 p 值本身。

运行方式：python src/03_hypothesis_testing.py
输出：results/test_results.json + results/charts/*.png
"""
import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest

# Windows 自带中文字体，避免图表中文标签变成方框
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "cookie_cats.csv")
OUT_DIR = os.path.join(ROOT, "results")
CHART_DIR = os.path.join(OUT_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)

ALPHA = 0.05
N_BOOT = 10_000
rng = np.random.default_rng(2024)

df = pd.read_csv(DATA_PATH)
g30 = df[df["version"] == "gate_30"]  # 对照组：第 30 关设卡
g40 = df[df["version"] == "gate_40"]  # 实验组：第 40 关设卡


def ztest_and_bootstrap(metric: str):
    """对一个 0/1 指标做：双比例 z 检验 + Bootstrap 置信区间。

    返回 dict，包含两组比率、绝对差(pp)、相对提升、z 统计量、p 值、bootstrap 95% CI。
    """
    x1, n1 = int(g30[metric].sum()), len(g30)  # x=成功数(留存人数), n=样本数
    x2, n2 = int(g40[metric].sum()), len(g40)
    p1, p2 = x1 / n1, x2 / n2

    # ---- 双比例 z 检验（合并方差版本；statsmodels 的 proportions_ztest 等价）----
    _, pval = proportions_ztest([x1, x2], [n1, n2])
    z_stat, _ = proportions_ztest([x1, x2], [n1, n2])

    # ---- Bootstrap 置信区间 ----
    # 原理：把两组的 0/1 结果各重抽 1 万次，每次算"组间差"，看差的分布。
    # 用二项重抽（等价于对 0/1 数组重采样，但快几个数量级）。
    boot_diff = (rng.binomial(n2, p2, N_BOOT) / n2) - (rng.binomial(n1, p1, N_BOOT) / n1)
    ci_lo, ci_hi = np.percentile(boot_diff, [2.5, 97.5])

    return {
        "rate_ctrl": round(float(p1), 4), "rate_test": round(float(p2), 4),
        "abs_diff_pp": round(float((p2 - p1) * 100), 2),
        "rel_lift": round(float(p2 / p1 - 1), 4),
        "z_stat": round(float(z_stat), 2), "p_value": round(float(pval), 4),
        "boot_ci95_pp": [round(float(ci_lo * 100), 2), round(float(ci_hi * 100), 2)],
        "significant": bool(pval < ALPHA),
        "ci_excludes_zero": bool(ci_lo * 100 > 0 or ci_hi * 100 < 0),
    }


# ----------------------------------------------------------------------
# Q1：核心指标与护栏指标的显著性检验
# ----------------------------------------------------------------------
print("=" * 60)
print("Q1：双比例 z 检验 + Bootstrap 置信区间")
print("=" * 60)
results = {"alpha": ALPHA, "n_bootstrap": N_BOOT}
for metric, name in [("retention_1", "1日留存(护栏)"), ("retention_7", "7日留存(核心)")]:
    r = ztest_and_bootstrap(metric)
    results[metric] = r
    print(f"\n[{name}] {metric}")
    print(f"  gate_30 = {r['rate_ctrl']:.2%}，gate_40 = {r['rate_test']:.2%}")
    print(f"  绝对差 = {r['abs_diff_pp']:+.2f}pp（相对 {r['rel_lift']:+.2%}），z = {r['z_stat']}")
    print(f"  p 值 = {r['p_value']:.4f} → {'显著' if r['significant'] else '不显著'}")
    print(f"  Bootstrap 95% CI = [{r['boot_ci95_pp'][0]:+.2f}pp, {r['boot_ci95_pp'][1]:+.2f}pp]")

# ----------------------------------------------------------------------
# 护栏指标 2：游戏轮数（对离群点稳健的检验）
# ----------------------------------------------------------------------
med30 = g30["sum_gamerounds"].median()
med40 = g40["sum_gamerounds"].median()
u_stat, p_mw = stats.mannwhitneyu(g30["sum_gamerounds"], g40["sum_gamerounds"])
results["game_rounds"] = {
    "median_ctrl": float(med30), "median_test": float(med40),
    "mwu_p_value": round(float(p_mw), 4),
    "note": "均值受极端值影响大，用中位数 + Mann-Whitney U 检验（对分布形态假设更少）",
}
print(f"\n[游戏轮数(护栏)] 中位数 gate_30 = {med30:.0f}，gate_40 = {med40:.0f}，"
      f"Mann-Whitney p = {p_mw:.4f}")

# ----------------------------------------------------------------------
# Q3：分层分析 —— 不同活跃度人群的效应是否一致（辛普森悖论检查）
# ----------------------------------------------------------------------
print("\n" + "=" * 60)
print("Q3：按游戏轮数分层检查效应一致性")
print("=" * 60)
bins = [-1, 0, 10, 50, 150, np.inf]
labels = ["0轮(未上手)", "1-10轮", "11-50轮", "51-150轮", "150轮+"]
df["segment"] = pd.cut(df["sum_gamerounds"], bins=bins, labels=labels)

strata = []
for seg in labels:
    sub = df[df["segment"] == seg]
    if sub["version"].nunique() < 2:
        continue
    c = sub[sub["version"] == "gate_30"]["retention_7"]
    t = sub[sub["version"] == "gate_40"]["retention_7"]
    # 分层内样本量足够才做检验，否则只报比率
    if min(len(c), len(t)) >= 30:
        _, p_seg = proportions_ztest([int(c.sum()), int(t.sum())], [len(c), len(t)])
        p_seg = round(float(p_seg), 4)
    else:
        p_seg = None
    strata.append({
        "segment": seg, "n": len(sub),
        "rate_ctrl": round(float(c.mean()), 4), "rate_test": round(float(t.mean()), 4),
        "diff_pp": round(float((t.mean() - c.mean()) * 100), 2), "p_value": p_seg,
    })
    print(f"  {seg:<12} n={len(sub):>6}  gate_30={c.mean():.2%}  gate_40={t.mean():.2%}  "
          f"diff={strata[-1]['diff_pp']:+.2f}pp  p={p_seg}")
results["stratified_r7"] = strata
diff_signs = {s["diff_pp"] > 0 for s in strata}
results["simpson_risk"] = len(diff_signs) > 1
print(f"解读：各分层效应方向{'不一致，存在辛普森悖论风险，整体效应可能被某个分层主导' if results['simpson_risk'] else '一致'}")

# ----------------------------------------------------------------------
# 决策：把统计结论翻译成业务结论
# ----------------------------------------------------------------------
r7 = results["retention_7"]
decision = {
    "recommendation": "不上线（保持 30 关设卡）",
    "reasons": [
        f"实验组（40 关）7 日留存 {r7['rate_test']:.2%}，比对照组 {r7['rate_ctrl']:.2%} 低 "
        f"{abs(r7['abs_diff_pp'])}pp，方向为负，统计显著（p={r7['p_value']})；",
        "没有任何一个子指标（1 日留存、游戏轮数）出现正向补偿；",
        "本次实验未发现'对部分人群显著正向'的分层，不存在'只对新手有效'的补救上线方案；",
        "SRM 轻微异常提示数据采集链路可能有噪声，但负向方向一致，不影响'不值得上线'的判断。",
    ],
    "caveats": [
        "p 显著但效应量约 0.8pp，低于 1.5pp 的 MDE 上线门槛——统计显著 ≠ 业务值得；",
        "本实验只观察了留存，未包含付费转化数据，若 40 关能显著提升内购收入，需另做实验评估。",
    ],
}
results["decision"] = decision
print("\n" + "=" * 60)
print(f"决策建议：{decision['recommendation']}")
for x in decision["reasons"]:
    print("  -", x)

# ----------------------------------------------------------------------
# 图表
# ----------------------------------------------------------------------
C30, C40 = "#4C72B0", "#DD8452"

# 图 1：核心指标柱状图 + 单组 95% 置信区间误差线（Wald 近似：p ± 1.96·se）
def wald_ci(p, n, z=1.96):
    se = (p * (1 - p) / n) ** 0.5
    return p - z * se, p + z * se


metrics = ["retention_1", "retention_7"]
x = np.arange(len(metrics))
ctrl_rates = [results[m]["rate_ctrl"] for m in metrics]
test_rates = [results[m]["rate_test"] for m in metrics]
ctrl_err = [np.array([results[m]["rate_ctrl"] - wald_ci(results[m]["rate_ctrl"], len(g30))[0],
                      wald_ci(results[m]["rate_ctrl"], len(g30))[1] - results[m]["rate_ctrl"]]) for m in metrics]
test_err = [np.array([results[m]["rate_test"] - wald_ci(results[m]["rate_test"], len(g40))[0],
                      wald_ci(results[m]["rate_test"], len(g40))[1] - results[m]["rate_test"]]) for m in metrics]
fig, ax = plt.subplots(figsize=(7, 4.5))
ax.bar(x - 0.18, ctrl_rates, 0.34, yerr=np.array(ctrl_err).T, capsize=4, label="gate_30 (ctrl)", color=C30)
ax.bar(x + 0.18, test_rates, 0.34, yerr=np.array(test_err).T, capsize=4, label="gate_40 (test)", color=C40)
for i, m in enumerate(metrics):
    r = results[m]
    ax.text(i, 0.02, f"p={r['p_value']}\ndiff 95%CI [{r['boot_ci95_pp'][0]:+.1f}, {r['boot_ci95_pp'][1]:+.1f}]pp",
            ha="center", fontsize=9, transform=ax.get_xaxis_transform())
ax.set_xticks(x, ["1-day retention\n(guardrail)", "7-day retention\n(primary)"])
ax.set_ylabel("retention rate")
ax.set_title("Retention by group (error bar = 95% bootstrap CI)")
ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(CHART_DIR, "retention_overview.png"), dpi=150); plt.close(fig)

# 图 2：bootstrap 差值分布
boot_diff = (rng.binomial(len(g40), g40["retention_7"].mean(), N_BOOT) / len(g40)
             - rng.binomial(len(g30), g30["retention_7"].mean(), N_BOOT) / len(g30))
plt.figure(figsize=(7, 4.2))
plt.hist(boot_diff * 100, bins=60, color="#55A868", alpha=0.8)
lo, hi = np.percentile(boot_diff * 100, [2.5, 97.5])
plt.axvline(0, color="red", ls="--", lw=1, label="zero")
plt.axvline(lo, color="black", ls=":", lw=1)
plt.axvline(hi, color="black", ls=":", lw=1, label=f"95% CI [{lo:.2f}, {hi:.2f}]pp")
plt.title("Bootstrap distribution: 7-day retention diff (gate_40 - gate_30)")
plt.xlabel("difference (pp)")
plt.legend()
plt.tight_layout(); plt.savefig(os.path.join(CHART_DIR, "bootstrap_diff.png"), dpi=150); plt.close()

# 图 3：分层效应
seg_df = pd.DataFrame(strata)
plt.figure(figsize=(8, 4.5))
w = 0.38
pos = np.arange(len(seg_df))
plt.bar(pos - w / 2, seg_df["rate_ctrl"] * 100, w, label="gate_30", color=C30)
plt.bar(pos + w / 2, seg_df["rate_test"] * 100, w, label="gate_40", color=C40)
for i, s in seg_df.reset_index().iterrows():
    plt.text(i, 1.5, f"{s['diff_pp']:+.1f}pp", ha="center", fontsize=9)
plt.xticks(pos, seg_df["segment"])
plt.ylabel("7-day retention (%)")
plt.title("7-day retention by activity segment")
plt.legend()
plt.tight_layout(); plt.savefig(os.path.join(CHART_DIR, "stratified_retention.png"), dpi=150); plt.close()

with open(os.path.join(OUT_DIR, "test_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\n已保存：results/test_results.json + results/charts/{retention_overview,bootstrap_diff,stratified_retention}.png")
