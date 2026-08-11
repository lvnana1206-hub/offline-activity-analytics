"""月报推送模块：代理商版 + 内部版。

每月生成经营月报，突出表现差的代理商，驱动下月改进。
周期：自然月（1日至月末）。
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

import numpy as np
import pandas as pd

from .analysis.common import safe_num
from .config import COMPLETED_STATUSES
from .report_templates import _fmt_num, _fmt_pct, _fmt_wan, _dealer_short

LARK_CLI = "lark-cli"
DEFAULT_CHAT_ID = "YOUR_FEISHU_CHAT_ID"

_CLI_ENV = {
    "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
    "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
    "PATH": os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin",
    "HOME": os.environ.get("HOME", ""),
}


def _get_month_range(year: int | None = None, month: int | None = None) -> tuple[str, str, str, int, int]:
    """获取自然月范围。返回 (start, end, label, year, month)。"""
    if year is None or month is None:
        now = datetime.now()
        if now.day == 1:
            prev = now.replace(day=1) - pd.Timedelta(days=1)
            year, month = prev.year, prev.month
        else:
            year, month = now.year, now.month
    start = pd.Timestamp(year=year, month=month, day=1)
    if month == 12:
        end = pd.Timestamp(year=year + 1, month=1, day=1)
    else:
        end = pd.Timestamp(year=year, month=month + 1, day=1)
    label = f"{year}年{month}月"
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), label, year, month


def generate_monthly_report(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame,
    dim_dealer: pd.DataFrame,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    """生成月度经营数据。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = safe_num(df["sales_clean"])
    df["participants"] = safe_num(df["participants"])
    df["wechat"] = safe_num(df["wechat_adds"])
    df["hosts"] = safe_num(df["converted_hosts"])
    dealer_col = "dealer_final" if "dealer_final" in df.columns else "dealer"
    df["dealer"] = df[dealer_col]

    m_start, m_end, label, yr, mo = _get_month_range(year, month)
    ms = pd.Timestamp(m_start)
    me = pd.Timestamp(m_end)

    mask = (df["activity_date"] >= ms) & (df["activity_date"] < me)
    month_df = df[mask].copy()

    # 上月数据
    prev_start = ms - pd.DateOffset(months=1)
    prev_end = ms
    prev_df = df[(df["activity_date"] >= prev_start) & (df["activity_date"] < prev_end)].copy()

    # 按代理商聚合
    def _dealer_agg(d: pd.DataFrame) -> pd.DataFrame:
        if len(d) == 0:
            return pd.DataFrame()
        d = d.copy()
        d["wechat_rate"] = np.where(d["participants"] > 0, d["wechat"] / d["participants"], 0)
        d["conv_rate"] = np.where(d["participants"] > 0, d["hosts"] / d["participants"], 0)
        d["is_valid"] = (d["wechat_rate"] > 0.05) | (d["hosts"] > 0)
        g = d.groupby("dealer").agg(
            activity_count=("record_id", "count"),
            total_sales=("sales", "sum"),
            total_participants=("participants", "sum"),
            total_wechat=("wechat", "sum"),
            total_hosts=("hosts", "sum"),
            stores_covered=("store_name", "nunique"),
            valid_count=("is_valid", "sum"),
            zero_conv_count=("hosts", lambda x: (x == 0).sum()),
            low_wechat_count=("wechat_rate", lambda x: (x < 0.02).sum()),
        ).reset_index()
        g["health_score"] = (g["valid_count"] / g["activity_count"] * 100).round(1)
        g["conv_rate"] = np.where(g["total_participants"] > 0, g["total_hosts"] / g["total_participants"], 0)
        g["wechat_rate"] = np.where(g["total_participants"] > 0, g["total_wechat"] / g["total_participants"], 0)
        return g

    curr_g = _dealer_agg(month_df)
    prev_g = _dealer_agg(prev_df)

    # 关联门店总数
    if len(curr_g) > 0:
        curr_g = curr_g.merge(
            dim_dealer[["dealer", "store_count"]], on="dealer", how="left"
        )
        curr_g["store_count"] = curr_g["store_count"].fillna(0).astype(int)
        curr_g["coverage_rate"] = (curr_g["stores_covered"] / curr_g["store_count"]).round(3)
        curr_g = curr_g.sort_values("activity_count", ascending=False)

    # 零活动代理商
    all_dealers = set(dim_dealer["dealer"].unique())
    active_dealers = set(month_df["dealer"].unique()) if len(month_df) > 0 else set()
    zero_dealers = sorted(all_dealers - active_dealers)
    zero_dealer_info = []
    for d in zero_dealers:
        row = dim_dealer[dim_dealer["dealer"] == d].iloc[0]
        zero_dealer_info.append({
            "dealer": d,
            "store_count": int(row.get("store_count", 0)),
        })

    # 活动量不足代理商（有活动但低于场均50%）
    low_activity_dealers = []
    if len(curr_g) > 0:
        avg_act = curr_g["activity_count"].mean()
        threshold = avg_act * 0.5
        low_act = curr_g[curr_g["activity_count"] < threshold]
        for _, r in low_act.iterrows():
            low_activity_dealers.append({
                "dealer": r["dealer"],
                "activity_count": int(r["activity_count"]),
                "store_count": int(r.get("store_count", 0)),
            })

    # 低转化代理商
    low_conv_dealers = []
    if len(curr_g) > 0:
        low_c = curr_g[curr_g["conv_rate"] < 0.02].sort_values("conv_rate")
        for _, r in low_c.iterrows():
            low_conv_dealers.append({
                "dealer": r["dealer"],
                "activity_count": int(r["activity_count"]),
                "conv_rate": float(r["conv_rate"]),
                "total_hosts": int(r["total_hosts"]),
                "total_participants": int(r["total_participants"]),
            })

    # 低企微蓄水代理商
    low_wechat_dealers = []
    if len(curr_g) > 0:
        low_w = curr_g[curr_g["wechat_rate"] < 0.05].sort_values("wechat_rate")
        for _, r in low_w.iterrows():
            low_wechat_dealers.append({
                "dealer": r["dealer"],
                "activity_count": int(r["activity_count"]),
                "wechat_rate": float(r["wechat_rate"]),
                "total_wechat": int(r["total_wechat"]),
                "total_participants": int(r["total_participants"]),
            })

    # 低转化活动（0成交）
    zero_conv_activities = []
    if len(month_df) > 0:
        zc = month_df[month_df["hosts"] == 0]
        zc = zc.nsmallest(10, "participants")[
            ["dealer", "activity_desc", "store_name", "participants", "hosts"]
        ]
        zero_conv_activities = [_clean(r) for r in zc.to_dict("records")]

    # 低企微蓄水活动
    low_wechat_activities = []
    if len(month_df) > 0:
        wd = month_df.copy()
        wd["wr"] = np.where(wd["participants"] > 0, wd["wechat"] / wd["participants"], 0)
        low_w = wd.nsmallest(10, "wr")[
            ["dealer", "activity_desc", "store_name", "wr", "wechat", "participants"]
        ]
        low_wechat_activities = [_clean(r) for r in low_w.to_dict("records")]

    # 零活动门店
    all_stores = set(dim_store["store_name"].unique())
    active_stores = set(month_df["store_name"].unique()) if len(month_df) > 0 else set()
    zero_stores = [s for s in sorted(all_dealers - active_stores) if s and isinstance(s, str)]

    # 产品表现
    product_perf = []
    products = [("luna", "Luna"), ("x_series", "X系列"), ("go_series", "Go"),
                ("ace_series", "Ace"), ("drone", "无人机")]
    for p, n in products:
        if p in month_df.columns:
            total = float(month_df[p].sum())
            if total > 0:
                product_perf.append({"product": n, "total_sales": total,
                                     "activity_count": int(len(month_df[month_df[p] > 0]))})
    product_perf.sort(key=lambda x: x["total_sales"], reverse=True)

    # 门店排名
    store_ranking = []
    if len(month_df) > 0:
        sr = month_df.groupby("store_name").agg(
            activity_count=("record_id", "count"),
            total_sales=("sales", "sum"),
            total_participants=("participants", "sum"),
            total_wechat=("wechat", "sum"),
            total_hosts=("hosts", "sum"),
        ).reset_index().sort_values("total_sales", ascending=False).head(20)
        store_ranking = sr.to_dict("records")

    # 汇总
    total_stores = len(all_stores)
    total_dealers = len(all_dealers)
    cov_rate = len(active_stores) / total_stores if total_stores else 0
    diff = len(month_df) - len(prev_df)

    return {
        "label": label,
        "month_start": m_start,
        "month_end": (me - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "year": yr,
        "month": mo,
        "summary": {
            "total_activities": int(len(month_df)),
            "prev_activities": int(len(prev_df)),
            "activity_diff": diff,
            "total_dealers_active": int(len(active_dealers)),
            "total_dealers": int(total_dealers),
            "total_stores_active": int(len(active_stores)),
            "total_stores": int(total_stores),
            "total_sales": float(month_df["sales"].sum()),
            "total_participants": int(month_df["participants"].sum()),
            "total_wechat": int(month_df["wechat"].sum()),
            "total_hosts": int(month_df["hosts"].sum()),
            "zero_dealer_count": len(zero_dealers),
            "zero_store_count": len(zero_stores),
            "coverage_rate": cov_rate,
            "avg_dealer_activity": len(month_df) / total_dealers if total_dealers else 0,
        },
        "dealer_ranking": _clean_df(curr_g) if len(curr_g) > 0 else [],
        "zero_dealers": zero_dealer_info,
        "low_activity_dealers": low_activity_dealers,
        "low_conv_dealers": low_conv_dealers,
        "low_wechat_dealers": low_wechat_dealers,
        "zero_conv_activities": zero_conv_activities,
        "low_wechat_activities": low_wechat_activities,
        "store_ranking": _clean_list(store_ranking),
        "product_perf": product_perf,
        "prev_stats": {
            "activities": int(len(prev_df)),
            "sales": float(prev_df["sales"].sum()),
            "participants": int(prev_df["participants"].sum()),
            "wechat": int(prev_df["wechat"].sum()),
            "hosts": int(prev_df["hosts"].sum()),
        },
    }


def _clean(record: dict) -> dict:
    for k, v in record.items():
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            record[k] = 0
        elif isinstance(v, (np.integer,)):
            record[k] = int(v)
        elif isinstance(v, (np.floating,)):
            record[k] = round(float(v), 4) if v == v else 0
    return record


def _clean_list(records: list) -> list:
    return [_clean(r) for r in records]


def _clean_df(df: pd.DataFrame) -> list:
    return [_clean(r) for r in df.to_dict("records")]


def format_dealer_monthly(report: dict) -> str:
    """代理商月报版：对标+改进驱动。不含销售额。突出差的。"""
    s = report["summary"]
    label = report["label"]
    ranking = report.get("dealer_ranking", [])
    zero_d = report.get("zero_dealers", [])
    low_act = report.get("low_activity_dealers", [])
    low_conv_d = report.get("low_conv_dealers", [])
    low_w_d = report.get("low_wechat_dealers", [])
    zero_conv_acts = report.get("zero_conv_activities", [])
    low_w_acts = report.get("low_wechat_activities", [])

    diff = s["activity_diff"]
    avg_act = s["avg_dealer_activity"]

    L: list[str] = []
    L.append(f"**\U0001f4ca 全国线下活动经营月报（{label}）**\n")
    L.append(f"**统计周期：{report['month_start']} ~ {report['month_end']}**\n---\n")

    # 一、本月概况
    L.append("## 一、本月概况\n")
    if diff > 0:
        L.append(f"- 活动总场次：**{s['total_activities']} 场**（环比 **+{diff}**）\n")
    elif diff < 0:
        L.append(f"- 活动总场次：**{s['total_activities']} 场**（环比 **{diff}**）\n")
    else:
        L.append(f"- 活动总场次：**{s['total_activities']} 场**\n")
    L.append(f"- 活跃代理商：**{s['total_dealers_active']} / {s['total_dealers']}**\n")
    L.append(f"- 活跃门店：**{s['total_stores_active']} / {s['total_stores']}**\n")
    L.append(f"- 参与人数：**{_fmt_num(s['total_participants'])}**\n")
    L.append(f"- 企微新增：**{_fmt_num(s['total_wechat'])}**\n")
    L.append(f"- 转化主机：**{_fmt_num(s['total_hosts'])}**\n")

    # 二、全国参考值
    L.append("\n## 二、全国参考值\n")
    L.append(f"- 代理商场均活动：**{avg_act:.1f} 场**\n")
    L.append(f"- 门店覆盖率：**{_fmt_pct(s['coverage_rate'])}**\n")

    # 三、本月标杆
    L.append("\n## 三、本月标杆\n")
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    for i, r in enumerate(ranking[:3]):
        L.append(
            f"{medals[i]} {_dealer_short(r['dealer'], 8)}"
            f"｜{int(r['activity_count'])} 场"
            f"｜覆盖率 {_fmt_pct(r.get('coverage_rate'))}"
            f"｜健康度 {r.get('health_score', 0):.0f}\n"
        )
    L.append("\n**参考点：**活动节奏稳定、门店覆盖较高、执行质量持续保持。\n")

    # 四、重点改进（突出差的）
    L.append("\n## 四、重点改进\n")

    if zero_d:
        L.append(f"**零活动代理商（{len(zero_d)} 家）**\n")
        names = "、".join(_dealer_short(d["dealer"], 6) for d in zero_d)
        L.append(names + "。\n")

    if low_act:
        L.append(f"\n**活动量不足（低于场均50%）**\n")
        for r in low_act[:5]:
            L.append(
                f"- {_dealer_short(r['dealer'], 6)}"
                f"｜{r['activity_count']} 场"
                f"｜{r.get('store_count', 0)} 家门店\n"
            )

    if zero_conv_acts:
        L.append("\n**低转化活动（0 成交）**\n")
        for r in zero_conv_acts[:5]:
            L.append(
                f"- {_dealer_short(r.get('dealer', ''), 6)}"
                f"｜{str(r.get('store_name', ''))[:10]}"
                f"｜参与 {int(r.get('participants', 0))} 人\n"
            )

    if low_w_acts:
        L.append("\n**低企微蓄水活动**\n")
        for r in low_w_acts[:5]:
            wr = r.get("wr", 0)
            L.append(
                f"- {_dealer_short(r.get('dealer', ''), 6)}"
                f"｜{str(r.get('store_name', ''))[:10]}"
                f"｜{_fmt_pct(wr)}\n"
            )

    # 五、下月提醒
    L.append("\n## 五、下月提醒\n")
    L.append("- 零活动代理商须完成下月活动规划并落地首场活动。\n")
    L.append("- 活动量不足代理商对标全国场均，提升活动频次。\n")
    L.append("- 低转化活动需完成复盘，优化转化环节。\n")
    L.append("- 低企微蓄水活动需加强现场引流和社群运营。\n")
    target_cov = min(s["coverage_rate"] * 100 + 5, 35)
    L.append(f"- 下月目标：**全国门店覆盖率提升至 {target_cov:.0f}%+。**\n")

    L.append("\n**数据来源：飞书多维表格（实时同步）｜统计周期：自然月1日至月末**")
    return "\n".join(L)


def format_internal_monthly(report: dict, analysis: dict | None = None) -> str:
    """内部月报版：六段结构，管理驱动。"""
    s = report["summary"]
    label = report["label"]
    ranking = report.get("dealer_ranking", [])
    zero_d = report.get("zero_dealers", [])
    low_act = report.get("low_activity_dealers", [])
    low_conv_d = report.get("low_conv_dealers", [])
    low_w_d = report.get("low_wechat_dealers", [])
    zero_conv_acts = report.get("zero_conv_activities", [])
    low_w_acts = report.get("low_wechat_activities", [])
    products = report.get("product_perf", [])
    store_top = report.get("store_ranking", [])
    prev = report.get("prev_stats", {})

    diff = s["activity_diff"]
    cov_rate = s["coverage_rate"]
    avg_act = s["avg_dealer_activity"]

    L: list[str] = []
    L.append(f"**\U0001f4ca 全国线下活动经营月报（{label}）**\n")
    L.append(f"周期：{report['month_start']} ~ {report['month_end']}\n---\n")

    # ① 本月经营结论
    L.append("**① 本月经营结论**\n")
    arrow = "增加" if diff > 0 else "减少" if diff < 0 else "持平"
    top3 = ranking[:3]
    top3_count = sum(int(r["activity_count"]) for r in top3) if top3 else 0
    share = top3_count / s["total_activities"] * 100 if s["total_activities"] else 0
    L.append(f"> 本月共{s['total_activities']}场活动，环比{arrow}{abs(diff)}场，销售额¥{_fmt_num(s['total_sales'])}。")
    if share > 35 and len(top3) >= 2:
        names = "、".join(_dealer_short(r["dealer"], 4) for r in top3[:2])
        L.append(f"> 增长集中于{names}等头部代理商，全国门店覆盖率仅{_fmt_pct(cov_rate)}。")
    else:
        L.append(f"> 全国门店覆盖率{_fmt_pct(cov_rate)}，零活动门店{s['zero_store_count']}家。")
    if s["zero_dealer_count"] > 5:
        L.append(f"> {s['zero_dealer_count']}家代理商全月零活动，下月须推动首场落地。\n")
    else:
        L.append("> 下月持续扩大门店覆盖及提升活动质量。\n")

    # ② 经营亮点
    L.append("\n**② 经营亮点**\n")
    L.append(f"- **活动规模**：{s['total_activities']}场（环比{('↑'+str(diff)) if diff>0 else ('↓'+str(abs(diff))) if diff<0 else '→'}），"
             f"活跃代理商{s['total_dealers_active']}/{s['total_dealers']}\n")
    if ranking:
        r = ranking[0]
        L.append(f"- **优秀代理商**：{_dealer_short(r['dealer'], 8)}"
                 f"（{int(r['activity_count'])}场，健康度{r.get('health_score', 0):.0f}）\n")
    if store_top:
        ts = store_top[0]
        L.append(f"- **门店冠军**：{str(ts.get('store_name', ''))[:10]}"
                 f"（{int(ts.get('activity_count', 0))}场，转化{int(ts.get('total_hosts', 0))}台）\n")
    if products:
        tp = products[0]
        L.append(f"- **明星产品**：{tp['product']}（{int(tp['total_sales'])}台）\n")

    # ③ 风险预警
    L.append("\n**③ 风险预警**\n")
    risks = []
    if zero_d:
        risks.append(("\U0001f6a8", f"{len(zero_d)}家代理商全月零活动", "覆盖缺失", "区域运营跟进"))
    if low_act:
        risks.append(("\U0001f6a8", f"{len(low_act)}家代理商活动量不足", "低于场均50%", "对标提升"))
    if zero_conv_acts:
        risks.append(("\U000026a0\ufe0f", f"{len(zero_conv_acts)}场零成交", "转化失效", "完成复盘"))
    if low_w_acts:
        risks.append(("\U000026a0\ufe0f", f"{len(low_w_acts)}场企微蓄水率<2%", "引流不足", "加强蓄水"))
    for i, (emoji, desc, impact, action) in enumerate(risks[:3], 1):
        L.append(f"{emoji} {desc}\n> 影响：{impact}｜建议：{action}\n")
    if not risks:
        L.append("本月无明显经营风险。\n")

    # ④ 本月督办
    L.append("\n**④ 本月督办**\n")
    L.append("| 事项 | 对象 | 原因 | 完成时间 |")
    L.append("|:---|:---|:---|:---|")
    actions = []
    if zero_d:
        actions.append(("零活动代理商跟进", "区域运营", f"{len(zero_d)}家零活动", "下月首周"))
    if low_act:
        actions.append(("活动量提升", "区域运营", f"{len(low_act)}家不足", "下月"))
    if zero_conv_acts:
        conv_d = set(_dealer_short(r.get("dealer", ""), 6) for r in zero_conv_acts)
        actions.append(("活动复盘", "区域运营", f"{len(conv_d)}家零成交", "次周"))
    if low_w_acts:
        w_d = set(_dealer_short(r.get("dealer", ""), 6) for r in low_w_acts)
        actions.append(("企微整改", "区域运营", f"{len(w_d)}家企微低", "次周"))
    low_hs = [r for r in ranking if r.get("health_score", 100) < 60]
    if low_hs:
        actions.append(("质量复盘", "区域运营", f"{len(low_hs)}家健康度低", "次周"))
    for a in actions[:5]:
        L.append(f"| {a[0]} | {a[1]} | {a[2]} | {a[3]} |")
    if not actions:
        L.append("| 暂无重点督办 | - | - | - |")
    L.append("")

    # ⑤ 数据摘要
    L.append("\n**⑤ 数据摘要**\n")
    L.append("*代理商排行 TOP10：*\n")
    L.append("| 排名 | 代理商 | 活动数 | 覆盖率 | 健康度 | 转化率 |")
    L.append("|:---:|:---|---:|---:|---:|---:|")
    for i, r in enumerate(ranking[:10], 1):
        L.append(f"| {i} | {_dealer_short(r['dealer'], 10)} | "
                 f"{int(r['activity_count'])} | {_fmt_pct(r.get('coverage_rate'))} | "
                 f"{r.get('health_score', 0):.0f} | {_fmt_pct(r.get('conv_rate', 0))} |")
    L.append("")

    if zero_d:
        L.append(f"\n*零活动代理商（{len(zero_d)}家）：*\n")
        names = "、".join(f"{_dealer_short(d['dealer'], 6)}（{d.get('store_count', 0)}店）" for d in zero_d)
        L.append(names + "\n")

    if low_conv_d:
        L.append(f"\n*低转化代理商（转化率<2%）：*\n")
        for r in low_conv_d[:5]:
            L.append(f"- {_dealer_short(r['dealer'], 6)}｜{r['activity_count']}场｜转化率{_fmt_pct(r['conv_rate'])}｜{r['total_hosts']}台/{r['total_participants']}人")
        L.append("")

    if low_w_d:
        L.append(f"\n*低企微蓄水代理商（蓄水率<5%）：*\n")
        for r in low_w_d[:5]:
            L.append(f"- {_dealer_short(r['dealer'], 6)}｜{r['activity_count']}场｜蓄水率{_fmt_pct(r['wechat_rate'])}｜{r['total_wechat']}人/{r['total_participants']}人")
        L.append("")

    # ⑥ 下月目标
    L.append("\n**⑥ 下月目标**\n")
    L.append("```")
    dealer_cov = s["total_dealers_active"] / s["total_dealers"] * 100 if s["total_dealers"] else 0
    L.append(f"目标1  代理商活动覆盖率  {dealer_cov:.0f}%  ->  85%")
    L.append(f"目标2  门店覆盖率        {_fmt_pct(cov_rate)}  ->  {min(cov_rate*100+5, 35):.0f}%")
    L.append(f"目标3  零活动代理商      {len(zero_d)}  ->  {max(len(zero_d)-3, 0)}")
    L.append(f"目标4  零活动门店        {s['zero_store_count']}  ->  {max(s['zero_store_count']-50, 0)}")
    avg_hs = sum(r.get("health_score", 0) for r in ranking) / len(ranking) if ranking else 0
    L.append(f"目标5  活动健康度        {avg_hs:.0f}  ->  {min(avg_hs+5, 100):.0f}")
    L.append("```")
    L.append(f"\n> 下月重点推进门店覆盖率提升及零活动代理商整改。\n")

    L.append("\n---\n*内部使用 | 周期：自然月 | 数据来源：飞书多维表格*")
    return "\n".join(L)


def push_to_feishu(
    markdown: str,
    chat_id: str = DEFAULT_CHAT_ID,
    dry_run: bool = False,
) -> dict:
    """通过 lark-cli 发送 markdown 消息到飞书群聊。"""
    chat_id = chat_id or DEFAULT_CHAT_ID
    cmd = [
        LARK_CLI, "im", "+messages-send",
        "--chat-id", chat_id,
        "--as", "bot",
        "--markdown", markdown,
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd, capture_output=True, text=True, env=_CLI_ENV, timeout=60
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr or result.stdout}

    try:
        resp = json.loads(result.stdout)
        return {"ok": resp.get("ok", False), "data": resp.get("data", {})}
    except json.JSONDecodeError:
        return {"ok": True, "raw": result.stdout[:500]}


def run_monthly_push(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame,
    dim_dealer: pd.DataFrame,
    template: str = "dealer",
    year: int | None = None,
    month: int | None = None,
    chat_id: str = "",
    dry_run: bool = False,
) -> dict:
    """完整执行：生成月报 -> 格式化 -> 推送飞书。"""
    report = generate_monthly_report(merged, dim_store, dim_dealer, year, month)
    if template == "internal":
        md = format_internal_monthly(report)
    else:
        md = format_dealer_monthly(report)
    push_result = push_to_feishu(md, chat_id or None, dry_run)
    return {
        "report": report,
        "markdown": md,
        "push": push_result,
    }
