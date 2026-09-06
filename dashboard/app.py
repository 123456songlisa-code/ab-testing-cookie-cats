# -*- coding: utf-8 -*-
"""
实验监控看板（Streamlit）
========================
定位：给"产品/运营同事"看的一页式实验报告，不是给自己看的分析脚本。
三个 tab：
  ① 实验健康度 —— 上结论之前先看数据本身可不可信（SRM / AA）
  ② 核心指标   —— 两组留存对比 + 显著性 + 置信区间
  ③ 决策建议   —— 统计结论翻译成业务结论
本地运行：streamlit run dashboard/app.py
线上部署：GitHub 仓库 → share.streamlit.io 免费部署
"""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent  # 仓库根目录（本地与云端通用）
DATA = ROOT / "data" / "cookie_cats.csv"
RESULTS = ROOT / "results"

st.set_page_config(page_title="AB 实验看板 · Cookie Cats", page_icon="🧪", layout="wide")

# ----------------------------------------------------------------------
# 数据加载（带缓存：9 万行 CSV 读一次即可）
# ----------------------------------------------------------------------
@st.cache_data
def load_data() -> pd.DataFrame:
    return pd.read_csv(DATA)


@st.cache_data
def load_results():
    with open(RESULTS / "test_results.json", encoding="utf-8") as f:
        test = json.load(f)
    with open(RESULTS / "srm_check.json", encoding="utf-8") as f:
        srm = json.load(f)
    with open(RESULTS / "sample_size.json", encoding="utf-8") as f:
        power = json.load(f)
    return test, srm, power


df = load_data()
test, srm, power = load_results()

# ----------------------------------------------------------------------
# 侧边栏：实验背景卡片
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("🧪 实验背景")
    st.markdown(
        """
        **产品改动**：三消游戏《Cookie Cats》把第一道"等待闸门"从第 **30 关**移到第 **40 关**，
        期望延长新手引导、提升长期留存。

        **分组**：
        - `gate_30` = 对照组（维持现状）
        - `gate_40` = 实验组（新策略）

        **指标体系**
        | 类型 | 指标 |
        |---|---|
        | 核心 | 7 日留存 |
        | 护栏 | 1 日留存、游戏轮数 |

        **决策门槛**：MDE = 1.5pp，α = 0.05，power = 0.8
        """
    )
    st.caption(f"样本量：{len(df):,} 用户 | 数据：Kaggle · Cookie Cats")

st.title("AB 实验监控看板 · 关卡后移对留存的影响")
st.caption("分析代码见 src/，指标口径见 sql/，全部数字可复现")

# ----------------------------------------------------------------------
# 顶部 KPI 卡片
# ----------------------------------------------------------------------
r7, r1 = test["retention_7"], test["retention_1"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("7日留存 · 对照组", f"{r7['rate_ctrl']:.2%}")
c2.metric("7日留存 · 实验组", f"{r7['rate_test']:.2%}", f"{r7['abs_diff_pp']:+.2f}pp", delta_color="inverse")
c3.metric("p 值（7日留存）", f"{r7['p_value']:.4f}", "显著" if r7["significant"] else "不显著")
c4.metric("决策建议", "不上线", "维持 30 关", delta_color="off")

tab1, tab2, tab3 = st.tabs(["① 实验健康度", "② 核心指标", "③ 决策建议"])

# ----------------------------------------------------------------------
# Tab 1：实验健康度
# ----------------------------------------------------------------------
with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("SRM 检验（分流比例）")
        counts = df["version"].value_counts()
        fig = go.Figure(go.Pie(
            labels=["gate_30（对照）", "gate_40（实验）"],
            values=[counts["gate_30"], counts["gate_40"]],
            hole=0.55, marker_colors=["#4C72B0", "#DD8452"],
        ))
        fig.update_layout(title_text=f"实际比例 1 : {srm['srm']['ratio_gate40_vs_gate30']}（承诺 1 : 1）", height=330)
        st.plotly_chart(fig, use_container_width=True)
        s = srm["srm"]
        if s["p_value"] < 0.05:
            st.error(f"χ²={s['chi2']}，p={s['p_value']} —— **SRM 显著**：比例偏离难以用随机波动解释，"
                     "需排查埋点丢失/分流哈希/机器人流量，下结论时需打折扣。")
        else:
            st.success(f"χ²={s['chi2']}，p={s['p_value']} —— 分流比例正常。")
    with col_b:
        st.subheader("AA 检验（空实验假阳性率）")
        aa = srm["aa_test"]
        st.plotly_chart(go.Figure(go.Bar(
            x=["显著次数", "不显著次数"], y=[aa["n_significant"], aa["n_sims"] - aa["n_significant"]],
            marker_color=["#C44E52", "#55A868"], text=[aa["n_significant"], aa["n_sims"] - aa["n_significant"]],
        )).update_layout(title_text=f"20 次空实验（理论假阳性率 5%），经验值 {aa['false_positive_rate']:.0%}", height=330),
            use_container_width=True)
        st.caption("解读：α=0.05 的含义就是空实验也会有约 5% 误报，1~2 次属正常。")

    st.subheader("样本量与功效")
    st.markdown(
        f"- 实际每组样本量 **{power['n_per_group_actual']:,}**"
        f"（gate_30 {srm['srm']['gate_30']:,} / gate_40 {srm['srm']['gate_40']:,}）"
        f"- MDE=1.5pp 时每组仅需 **{power['n_per_group_required'][-1]['n_per_group']:,}** 人 → 功效充足"
        f"- 当前样本量最小可检出效应 ≈ **{power['mde_detectable_pp']}pp**（小于 0.74pp 的差异探不出来）"
    )

# ----------------------------------------------------------------------
# Tab 2：核心指标
# ----------------------------------------------------------------------
with tab2:
    st.subheader("核心指标对比（误差线 = 单组 95% 置信区间）")
    metrics = [("retention_1", "1日留存（护栏）"), ("retention_7", "7日留存（核心）")]
    counts = df["version"].value_counts()

    def wald_ci(p: float, n: int, z: float = 1.96):
        """单比例的 Wald 近似 95% 置信区间：p ± 1.96·sqrt(p(1-p)/n)"""
        se = (p * (1 - p) / n) ** 0.5
        return p - z * se, p + z * se

    fig = go.Figure()
    for m, name in metrics:
        r = test[m]
        for ver, rate_key, color in [("gate_30", "rate_ctrl", "#4C72B0"),
                                     ("gate_40", "rate_test", "#DD8452")]:
            rate, n = r[rate_key], int(counts[ver])
            lo, hi = wald_ci(rate, n)
            fig.add_trace(go.Bar(
                x=[name], y=[rate * 100], name=ver, marker_color=color,
                error_y=dict(type="data", symmetric=False,
                             array=[(hi - rate) * 100], arrayminus=[(rate - lo) * 100]),
                text=[f"{rate:.2%}"], textposition="outside",
                legendgroup=ver,
            ))
    r7 = test["retention_7"]
    fig.update_layout(
        barmode="group", yaxis_title="留存率 (%)", height=430,
        title=f"7日留存组间差 {r7['abs_diff_pp']:+.2f}pp，p={r7['p_value']}，"
              f"差值 95% CI [{r7['boot_ci95_pp'][0]:+.2f}, {r7['boot_ci95_pp'][1]:+.2f}]pp（全在 0 左侧）",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("检验明细")
    detail = pd.DataFrame([
        {"指标": name, "gate_30": f"{test[m]['rate_ctrl']:.2%}", "gate_40": f"{test[m]['rate_test']:.2%}",
         "绝对差": f"{test[m]['abs_diff_pp']:+.2f}pp", "相对提升": f"{test[m]['rel_lift']:+.2%}",
         "p 值": test[m]["p_value"], "Bootstrap 95% CI": f"[{test[m]['boot_ci95_pp'][0]:+.2f}, {test[m]['boot_ci95_pp'][1]:+.2f}]pp",
         "结论": "显著(负向)" if test[m]["significant"] else "不显著"}
        for m, name in metrics
    ])
    st.dataframe(detail, use_container_width=True, hide_index=True)

    st.subheader("游戏轮数（护栏，对离群点稳健口径）")
    seg = pd.read_csv(RESULTS / "sql_q2.csv")
    st.dataframe(seg, use_container_width=True, hide_index=True)
    st.caption("中位数 17 vs 16（Mann-Whitney p=0.0502）：实验组玩家游玩深度没有正向补偿，甚至略降。")

# ----------------------------------------------------------------------
# Tab 3：分层分析 + 决策建议
# ----------------------------------------------------------------------
with tab3:
    st.subheader("分层分析：负效应来自谁？")
    strat = pd.DataFrame(test["stratified_r7"])
    fig = go.Figure()
    fig.add_trace(go.Bar(x=strat["segment"], y=strat["rate_ctrl"] * 100, name="gate_30", marker_color="#4C72B0",
                         text=[f"{v:.1f}%" for v in strat["rate_ctrl"] * 100], textposition="outside"))
    fig.add_trace(go.Bar(x=strat["segment"], y=strat["rate_test"] * 100, name="gate_40", marker_color="#DD8452",
                         text=[f"{v:.1f}%" for v in strat["rate_test"] * 100], textposition="outside"))
    fig.update_layout(barmode="group", yaxis_title="7日留存 (%)", height=430,
                      title="负效应集中在 11~150 轮的中度玩家（-1.2pp ~ -3.2pp，p<0.001）")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        "**发现**：把闸门从 30 关挪到 40 关，恰好伤的是「已经上手、正在形成习惯」的中度玩家——"
        "他们在 30 关附近被多留了 10 关的缓冲，反而推迟/削弱了继续玩的动力。"
        "轻度玩家（还没玩到闸门）和重度玩家（早已越过多道闸门）不受影响。"
    )

    st.subheader("上线决策")
    d = test["decision"]
    st.error(f"### {d['recommendation']}")
    st.markdown("**理由**")
    for x in d["reasons"]:
        st.markdown(f"- {x}")
    st.markdown("**注意事项（caveats）**")
    for x in d["caveats"]:
        st.markdown(f"- {x}")

    st.info(
        "**一句话总结**：本次实验功效充足、分层后效应方向一致，"
        "40 关方案对核心指标 7 日留存产生 0.82pp 的显著负向影响且无任何子指标补偿，"
        "建议维持现状；同时 SRM 轻微异常需回流排查分流链路，后续可结合付费指标再评估。"
    )
