"""经营复盘引擎 (Business Review Engine)。

支持两类复盘：
  1. 季度经营复盘 (Quarterly Review) - 按季度汇总分析
  2. 新品上市复盘 (Product Launch Review) - 上市前后对比

全部计算在 Python 端完成，前端只负责渲染。
"""

from __future__ import annotations

import pandas as pd
from .config import COMPLETED_STATUSES
import numpy as np
from datetime import datetime


def _safe(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


# ═══════════════════════════════════════════════════════════
# 季度经营复盘
# ═══════════════════════════════════════════════════════════

def quarterly_review(merged: pd.DataFrame, year: int = 2026, quarter: int = 2) -> dict:
    """生成季度经营复盘数据。

    Args:
        merged: merged_activity_store 宽表
        year: 年份
        quarter: 季度 (1-4)

    Returns: 包含 10 个分析模块的字典
    """
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    df["wechat"] = _safe(df["wechat_adds"])
    df["hosts"] = _safe(df["converted_hosts"])

    # 季度日期范围
    q_start = pd.Timestamp(year=year, month=(quarter-1)*3+1, day=1)
    q_end = q_start + pd.DateOffset(months=3)

    q_df = df[(df["activity_date"] >= q_start) & (df["activity_date"] < q_end)].copy()
    q_label = f"{year} Q{quarter}"

    if len(q_df) == 0:
        return {"error": f"{q_label} 无活动数据"}

    print(f"季度复盘 {q_label}: {len(q_df)} 场活动")

    # 筛选有效数据（排除异常日期）
    q_df = q_df[q_df["activity_date"] <= pd.Timestamp.now()]

    result = {
        "label": q_label,
        "quarter": quarter,
        "year": year,
        "section_1_overview": _q_overview(q_df, q_label),
        "section_2_trend": _q_trend(q_df),
        "section_3_funnel": _q_funnel(q_df),
        "section_4_type": _q_type_analysis(q_df),
        "section_5_products": _q_products(q_df),
        "section_6_dealers": _q_dealers(q_df),
        "section_7_stores": _q_stores(q_df),
        "section_8_regions": _q_regions(q_df),
        "section_9_comparisons": _q_comparisons(q_df),
        "section_10_conclusion": _q_conclusion(q_df),
        }
    return result


def _q_overview(df: pd.DataFrame, label: str) -> dict:
    """一、经营总览。"""
    total = len(df)
    completed = (df["activity_status"].isin(COMPLETED_STATUSES)).sum()
    effective = df[(df["activity_status"].isin(COMPLETED_STATUSES)) & ((df["participants"] > 0) | (df["sales"] > 0))]
    effective_count = len(effective)
    total_sales = float(df["sales"].sum())
    total_participants = int(df["participants"].sum())
    total_wechat = int(df["wechat"].sum())
    total_hosts = int(df["hosts"].sum())
    stores = int(df["store_name"].nunique())
    dealers = int(df["dealer"].nunique())
    cities = int(df["city"].nunique())
    review_rate = completed / total if total else 0
    closure_rate = effective_count / total if total else 0

    # 自动总结
    top_region = df["province"].value_counts().index[0] if df["province"].notna().any() else "未知"
    top_type = df["activity_type"].value_counts().index[0]
    monthly = df.groupby(df["activity_date"].dt.month).size()
    if len(monthly) >= 2:
        trend_desc = "逐月增长" if monthly.iloc[-1] > monthly.iloc[0] else "逐月下降"
    else:
        trend_desc = "数据不足"

    summary = (f"{label}共举办 {total} 场活动，覆盖 {stores} 家门店、{dealers} 家代理商、{cities} 个城市。"
               f"活动销售额 {total_sales/10000:.1f} 万元，参与 {total_participants:,} 人次。"
               f"活动主要类型为{top_type}，活动数量{trend_desc}，"
               f"活动复盘率 {review_rate:.0%}，闭环率 {closure_rate:.0%}。")

    return {
        "kpis": {
            "total_activities": total,
            "effective_activities": effective_count,
            "completed": int(completed),
            "stores_covered": stores,
            "dealers_covered": dealers,
            "cities_covered": cities,
            "total_sales": total_sales,
            "total_hosts": total_hosts,
            "total_participants": total_participants,
            "total_wechat": total_wechat,
            "review_rate": round(review_rate, 4),
            "closure_rate": round(closure_rate, 4),
            "avg_sales_per_activity": round(total_sales / completed, 2) if completed else 0,
        },
        "summary": summary,
    }


def _q_trend(df: pd.DataFrame) -> dict:
    """二、经营趋势。"""
    df = df.copy()
    df["month"] = df["activity_date"].dt.month
    df["month_name"] = df["activity_date"].dt.month.astype(str) + "月"

    monthly = df.groupby(["month", "month_name"]).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        effective_activities=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        drone_activities=("drone_display", lambda x: (x.astype(str).str.contains("是|yes|true|1", case=False, na=False)).sum()) if "drone_display" in df.columns else (0),
        completed=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
    ).reset_index().sort_values("month")

    # 活动类型变化
    type_by_month = df.groupby(["month", "activity_type"]).size().reset_index(name="count")
    type_pivot = type_by_month.pivot(index="month", columns="activity_type", values="count").fillna(0)

    # 文字分析
    analyses = []
    for _, row in monthly.iterrows():
        m = int(row["month"])
        if len(monthly) >= 2:
            prev = monthly[monthly["month"] < m]
            if len(prev) > 0:
                prev_count = prev.iloc[-1]["activity_count"]
                change = (row["activity_count"] - prev_count) / prev_count if prev_count else 0
                if change > 0.2:
                    analyses.append(f"{row["month_name"]}活动快速增长至 {int(row['activity_count'])} 场（环比+{change:.0%}），"
                                   f"销售额 {row['total_sales']/10000:.1f} 万元。")
                elif change < -0.2:
                    analyses.append(f"{row["month_name"]}活动下降至 {int(row['activity_count'])} 场（环比{change:.0%}）。")
                else:
                    analyses.append(f"{row["month_name"]}活动 {int(row['activity_count'])} 场，"
                                   f"销售额 {row['total_sales']/10000:.1f} 万元，表现平稳。")
            else:
                analyses.append(f"{row["month_name"]}活动 {int(row['activity_count'])} 场，"
                               f"销售额 {row['total_sales']/10000:.1f} 万元。")

    # 活动类型变化分析
    if len(type_pivot) >= 2:
        growing_types = []
        for col in type_pivot.columns:
            first = type_pivot[col].iloc[0]
            last = type_pivot[col].iloc[-1]
            if last > first and first > 0:
                growing_types.append(f"{col}(+{(last-first)/first*100:.0f}%)")
        if growing_types:
            analyses.append(f"活动类型变化：{', '.join(growing_types[:3])} 增长显著。")

    return {
        "monthly_data": monthly.to_dict("records"),
        "type_trend": type_pivot.reset_index().to_dict("records"),
        "analysis": analyses,
    }


def _q_quality(df: pd.DataFrame) -> dict:
    """三、活动质量分析。"""
    completed = df[df["activity_status"].isin(COMPLETED_STATUSES)].copy()

    # Top 活动
    top_sales = completed.nlargest(10, "sales")[["activity_desc", "activity_type", "store_name",
        "sales", "participants", "wechat", "activity_date"]].head(10)
    top_participants = completed.nlargest(10, "participants")[["activity_desc", "activity_type",
        "store_name", "participants", "sales", "activity_date"]].head(10)

    # 优秀活动共同特点
    top_20 = completed.nlargest(20, "sales")
    common_types = top_20["activity_type"].value_counts().head(3)
    avg_sales_top = float(top_20["sales"].mean())
    avg_participants_top = float(top_20["participants"].mean())
    avg_wechat_top = float(top_20["wechat"].mean())

    # 文字总结
    analyses = []
    if len(top_20) > 0:
        analyses.append(f"Top20 优秀活动场均销售 {avg_sales_top:,.0f} 元，场均参与 {avg_participants_top:.0f} 人，场均企微 {avg_wechat_top:.1f} 人。")
        analyses.append(f"优秀活动主要集中在：{', '.join([f'{t}({c}场)' for t, c in common_types.items()])}。")
        # 分析特点
        if avg_participants_top > 30:
            analyses.append("优秀活动的共同特点：参与人数多，注重现场体验和互动。")
        if avg_wechat_top > 5:
            analyses.append("优秀活动普遍重视私域沉淀，企微添加表现突出。")
        type_ratios = common_types / len(top_20)
        if type_ratios.iloc[0] > 0.4:
            analyses.append(f"{common_types.index[0]} 是高产活动的主力类型，建议标准化推广。")

    return {
        "top_sales": top_sales.to_dict("records"),
        "top_participants": top_participants.to_dict("records"),
        "top20_avg_sales": avg_sales_top,
        "top20_avg_participants": avg_participants_top,
        "top20_avg_wechat": avg_wechat_top,
        "common_types": common_types.to_dict(),
        "analysis": analyses,
    }


def _q_stores(df: pd.DataFrame) -> dict:
    """四、门店经营分析。"""
    store_stats = df.groupby("store_name").agg(
        activity_count=("record_id", "count"),
        completed=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        dealer=("dealer", "first"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()
    region_col_s = "province_unit_final" if "province_unit_final" in df.columns else "province"
    store_region = df.groupby("store_name")[region_col_s].first()
    store_stats["province_unit"] = store_stats["store_name"].map(store_region)
    store_stats["completion_rate"] = store_stats["completed"] / store_stats["activity_count"]

    top_stores = store_stats.nlargest(20, "activity_count")
    top_sales_stores = store_stats.nlargest(10, "total_sales")
    # 成长最快：活动量逐月增长（用首末月对比）
    df_copy = df.copy()
    df_copy["month"] = df_copy["activity_date"].dt.month
    store_monthly = df_copy.groupby(["store_name", "month"]).size().reset_index(name="count")
    first_month = store_monthly.groupby("store_name")["month"].min()
    last_month = store_monthly.groupby("store_name")["month"].max()
    growth_stores = []
    for store in store_stats["store_name"]:
        sm = store_monthly[store_monthly["store_name"] == store]
        if len(sm) >= 2:
            first_c = sm.iloc[0]["count"]
            last_c = sm.iloc[-1]["count"]
            if first_c > 0 and last_c > first_c:
                growth_stores.append({"store_name": store, "growth": (last_c - first_c) / first_c,
                                     "first": int(first_c), "last": int(last_c)})
    growth_stores = sorted(growth_stores, key=lambda x: x["growth"], reverse=True)[:5]

    # 无活动门店
    active = set(df["store_name"].dropna().unique())

    # 文字分析
    analyses = []
    if len(top_stores) > 0:
        analyses.append(f"Top10 活跃门店平均举办 {top_stores['activity_count'].mean():.0f} 场活动。")
        analyses.append(f"Top10 销售门店平均销售额 {top_sales_stores['total_sales'].mean()/10000:.1f} 万元。")
        if len(growth_stores) > 0:
            analyses.append(f"成长最快门店：{growth_stores[0]['store_name']}（活动量增长 {growth_stores[0]['growth']:.0%}）。")
        # 共同特点
        high_activity = store_stats[store_stats["activity_count"] >= 10]
        if len(high_activity) > 0:
            avg_types = high_activity["activity_types"].mean()
            analyses.append(f"活跃门店（≥10场活动）平均覆盖 {avg_types:.1f} 种活动类型，活动多样性是门店活跃的关键因素。")

    return {
        "top_stores": top_stores.to_dict("records"),
        "top_sales_stores": top_sales_stores.to_dict("records"),
        "growth_stores": growth_stores,
        "store_count": len(store_stats),
        "analysis": analyses,
    }


def _q_dealers(df: pd.DataFrame) -> dict:
    """五、代理商经营分析。"""
    dealer_stats = df.groupby("dealer").agg(
        activity_count=("record_id", "count"),
        completed=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        active_stores=("store_name", "nunique"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()
    dealer_stats["effective"] = dealer_stats["completed"]
    dealer_stats["effective_rate"] = (dealer_stats["effective"] / dealer_stats["activity_count"]).round(4)
    dealer_stats["completion_rate"] = dealer_stats["completed"] / dealer_stats["activity_count"]
    dealer_stats["avg_sales"] = dealer_stats["total_sales"] / dealer_stats["activity_count"]
    region_col_d = "province_unit_final" if "province_unit_final" in df.columns else "province"
    dealer_region = df.groupby("dealer")[region_col_d].first()
    dealer_stats["province_unit"] = dealer_stats["dealer"].map(dealer_region)

    top_dealers = dealer_stats.nlargest(20, "activity_count")
    # 需要辅导：活动量低或完成率低
    need_help = dealer_stats[(dealer_stats["activity_count"] < 10) | (dealer_stats["completion_rate"] < 0.05)]

    analyses = []
    if len(top_dealers) > 0:
        analyses.append(f"Top10 代理商平均举办 {top_dealers['activity_count'].mean():.0f} 场活动，"
                       f"平均销售额 {top_dealers['total_sales'].mean()/10000:.1f} 万元。")
        best = top_dealers.iloc[0]
        analyses.append(f"代理商 {best['dealer']} 活动量最高（{best['activity_count']}场），覆盖 {best['active_stores']} 家门店。")
        if len(need_help) > 0:
            analyses.append(f"{len(need_help)} 家代理商活动量不足或完成率低，需要运营辅导。")
        # 画像
        high_perf = dealer_stats[dealer_stats["total_sales"] > dealer_stats["total_sales"].median()]
        analyses.append(f"高绩效代理商（销售额高于中位数）共 {len(high_perf)} 家，"
                       f"平均活动类型 {high_perf['activity_types'].mean():.1f} 种，活动多样性更高。")

    return {
        "top_dealers": top_dealers.to_dict("records"),
        "need_help": need_help.to_dict("records"),
        "dealer_count": len(dealer_stats),
        "analysis": analyses,
    }


def _q_products(df: pd.DataFrame) -> dict:
    """六、产品经营分析。"""
    products = {
        "Luna": "luna_sales",
        "X系列": "x_series_sales",
        "Ace系列": "ace_series_sales",
        "Go系列": "go_series_sales",
        "无人机": "drone_sales",
    }

    results = []
    for name, col in products.items():
        if col not in df.columns:
            continue
        sales = _safe(df[col])
        active = (sales > 0).sum()
        total = float(sales.sum())
        avg = float(sales[sales > 0].mean()) if active > 0 else 0
        # 推荐活动类型
        prod_df = df[sales > 0]
        if len(prod_df) > 0:
            top_type = prod_df["activity_type"].value_counts().index[0]
        else:
            top_type = "-"
        results.append({
            "product": name,
            "activity_count": int(active),
            "total_sales": total,
            "avg_sales": avg,
            "recommended_type": top_type,
        })

    analyses = []
    if results:
        top_product = max(results, key=lambda x: x["total_sales"])
        analyses.append(f"产品活动中，{top_product['product']} 销量最高（{top_product['total_sales']:.0f} 台），"
                       f"出现在 {top_product['activity_count']} 场活动中。")
        for p in results:
            if p["activity_count"] > 0:
                analyses.append(f"{p['product']}：{p['activity_count']}场活动，{p['total_sales']:.0f}台，"
                               f"推荐活动类型：{p['recommended_type']}。")

    # product x month trend
    df_pm = df.copy()
    df_pm["month"] = df_pm["activity_date"].dt.month
    product_cols_map = {
        "Luna": "luna_sales",
        "X系列": "x_series_sales",
        "Go系列": "go_series_sales",
        "Ace系列": "ace_series_sales",
    }
    pm_rows = []
    for pname, pcol in product_cols_map.items():
        if pcol not in df_pm.columns:
            continue
        for month, grp in df_pm.groupby("month"):
            pm_rows.append({"product": pname, "month": int(month), "sales_qty": int(_safe(grp[pcol]).sum())})

    # product x type cross
    ptc_rows = []
    for atype, grp in df.groupby("activity_type"):
        for pname, pcol in product_cols_map.items():
            if pcol in grp.columns:
                ptc_rows.append({"activity_type": atype, "product": pname, "sales_qty": int(_safe(grp[pcol]).sum())})

    return {"products": results, "product_month": pm_rows, "product_type_cross": ptc_rows, "analysis": analyses}


def _q_regions(df: pd.DataFrame) -> dict:
    """七、区域经营分析。"""
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"
    region_stats = df.groupby(region_col).agg(
        activity_count=("record_id", "count"),
        completed=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        active_stores=("store_name", "nunique"),
        dealers=("dealer", "nunique"),
    ).reset_index().rename(columns={region_col: "region"})
    region_stats = region_stats[region_stats["region"].notna()].sort_values("activity_count", ascending=False)
    region_stats["completion_rate"] = region_stats["completed"] / region_stats["activity_count"]
    region_stats["sales_per_store"] = region_stats["total_sales"] / region_stats["active_stores"]

    analyses = []
    if len(region_stats) > 0:
        top = region_stats.iloc[0]
        analyses.append(f"{top['region']} 活动量最高（{top['activity_count']}场），覆盖 {top['active_stores']} 家门店。")
        # 成熟区域：活动量高 + 覆盖广
        mature = region_stats[region_stats["activity_count"] >= 50]
        if len(mature) > 0:
            analyses.append(f"成熟区域（≥50场活动）：{', '.join(mature['region'].tolist()[:5])}，活动体系完善。")
        # 机会区域：活动量低但门店多
        opportunity = region_stats[(region_stats["activity_count"] < 20) & (region_stats["active_stores"] >= 3)]
        if len(opportunity) > 0:
            analyses.append(f"机会区域（活动量低但有门店基础）：{', '.join(opportunity['region'].tolist()[:5])}，"
                           f"有增长空间。")
        # 差异分析
        if len(region_stats) >= 2:
            max_min_ratio = region_stats["activity_count"].iloc[0] / max(region_stats["activity_count"].iloc[-1], 1)
            if max_min_ratio > 5:
                analyses.append(f"区域间执行差异大，最高与最低活动量相差 {max_min_ratio:.0f} 倍。")

    region_stats = region_stats.rename(columns={"region": "province_unit"})
    return {
        "province_units": region_stats.to_dict("records"),
        "analysis": analyses,
    }


def _q_cases(df: pd.DataFrame) -> dict:
    """八、优秀案例。"""
    completed = df[df["activity_status"].isin(COMPLETED_STATUSES)].copy()
    if len(completed) == 0:
        return {"cases": [], "analysis": []}

    # 综合评分：销售(40%) + 参与人数(30%) + 企微(20%) + 活动类型多样性(10%)
    completed = completed.copy()
    sales_rank = completed["sales"].rank(pct=True)
    participant_rank = completed["participants"].rank(pct=True)
    wechat_rank = completed["wechat"].rank(pct=True)
    completed["composite_score"] = (sales_rank * 0.4 + participant_rank * 0.3 +
                                    wechat_rank * 0.3).round(3)
    top10 = completed.nlargest(10, "composite_score")

    cases = top10[["activity_desc", "activity_type", "store_name", "dealer",
                   "sales", "participants", "wechat", "composite_score",
                   "activity_date", "province"]].to_dict("records")

    analyses = []
    if cases:
        top = cases[0]
        analyses.append(f"综合最优活动：{str(top['activity_desc'])[:30]}...，"
                       f"销售 ¥{top['sales']:,.0f}，参与 {top['participants']:.0f} 人。")
        type_dist = top10["activity_type"].value_counts()
        analyses.append(f"Top10案例活动类型分布：{', '.join([f'{t}({c})' for t, c in type_dist.items()])}。")
        analyses.append("优秀案例的共同特点：销售转化强、参与人数多、重视企微蓄水。")

    return {"cases": cases, "analysis": analyses}


def _q_diagnosis(df: pd.DataFrame) -> dict:
    """九、经营诊断。"""
    findings = []

    total = len(df)
    completed = (df["activity_status"].isin(COMPLETED_STATUSES)).sum()
    rate = completed / total if total else 0
    if rate < 0.15:
        findings.append({
            "finding": f"活动复盘率仅 {rate:.0%}，{total - completed} 场活动未完成闭环",
            "cause": "活动后缺乏跟踪复盘机制，状态更新不及时",
            "impact": "无法评估活动效果，经验无法沉淀",
            "action": "建立活动 7 天闭环制度，活动后强制复盘",
        })

    # 区域集中度
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"
    region_dist = df[region_col].value_counts()
    if len(region_dist) > 0 and region_dist.iloc[0] / total > 0.3:
        findings.append({
            "finding": f"活动集中于 {region_dist.index[0]}（占比 {region_dist.iloc[0]/total:.0%}）",
            "cause": "新品推广资源向头部区域倾斜",
            "impact": "其他区域覆盖不足，增长机会流失",
            "action": f"复制 {region_dist.index[0]} 活动模式至低活动量区域",
        })

    # 销售转化
    comp_df = df[df["activity_status"].isin(COMPLETED_STATUSES)]
    if len(comp_df) > 0:
        low_sales = (comp_df["sales"] < 500).sum()
        if low_sales / len(comp_df) > 0.5:
            findings.append({
                "finding": f"{low_sales}/{len(comp_df)} 场已完成活动销售低于 500 元",
                "cause": "活动以品牌曝光为主，缺乏销售转化设计",
                "impact": "活动投入产出比低",
                "action": "增加现场成交环节，配置销售激励",
            })

    # 活动类型集中
    type_dist = df["activity_type"].value_counts()
    if type_dist.iloc[0] / total > 0.25:
        findings.append({
            "finding": f"活动类型集中，{type_dist.index[0]} 占比 {type_dist.iloc[0]/total:.0%}",
            "cause": "活动策划模板化，缺乏多样性",
            "impact": "客群触达面窄",
            "action": "增加外拍活动、workshop课堂等体验型活动",
        })

    # 门店覆盖
    active_stores = df["store_name"].nunique()
    findings.append({
        "finding": f"覆盖 {active_stores} 家门店，仍有部分门店无活动",
        "cause": "部分门店活动意识弱或资源不足",
        "impact": "品牌覆盖不完整",
        "action": "优先推动高等级无活动门店首场活动",
    })

    return {"findings": findings}


def _q_recommendations(df: pd.DataFrame) -> dict:
    """十、下一季度建议。"""
    type_stats = df.groupby("activity_type").agg(
        count=("record_id", "count"),
        avg_sales=("sales", "mean"),
    ).sort_values("avg_sales", ascending=False)

    recs = []

    # 活动类型建议
    if len(type_stats) > 0:
        best_type = type_stats.index[0]
        recs.append({
            "category": "活动类型",
            "suggestion": f"重点推广 {best_type}（场均销售 {type_stats.iloc[0]['avg_sales']:,.0f} 元），"
                         f"增加 {type_stats.index[-1] if len(type_stats)>1 else '外拍活动'} 的比重以提升多样性",
        })

    # 门店建议
    store_stats = df.groupby("store_name").size()
    active = len(store_stats)
    recs.append({
        "category": "门店",
        "suggestion": f"本季度覆盖 {active} 家门店，下季度目标新增 50 家门店首场活动。"
                     "优先推动 S/A 级无活动门店。",
    })

    # 代理商建议
    dealer_stats = df.groupby("dealer").size()
    low_dealers = dealer_stats[dealer_stats < 5]
    recs.append({
        "category": "代理商",
        "suggestion": f"{len(low_dealers)} 家代理商活动量不足 5 场，需专项辅导。"
                     "高绩效代理商的活动 SOP 向低绩效代理商输出。",
    })

    # 区域建议
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"
    region_stats = df.groupby(region_col).size().sort_values(ascending=False)
    if len(region_stats) >= 2:
        recs.append({
            "category": "区域",
            "suggestion": f"成熟区域 {region_stats.index[0]} 的活动模式向 "
                         f"{region_stats.index[-1]} 等低活动量区域复制。",
        })

    # 产品建议
    luna_sales = _safe(df["luna_sales"]).sum()
    recs.append({
        "category": "产品",
        "suggestion": f"Luna 本季度销量 {luna_sales:.0f} 台，建议增加新品品鉴会专项活动，"
                     "配合外拍活动展示 Luna 全景拍摄优势。",
    })

    return {"recommendations": recs}


def _q_funnel(df: pd.DataFrame) -> dict:
    """三、活动转化漏斗。"""
    sales = _safe(df["sales_clean"])
    parts = _safe(df["participants"])
    wechat = _safe(df["wechat_adds"])
    hosts = _safe(df["converted_hosts"])
    return {
        "funnel": {
            "total_activities": len(df),
            "has_participants": int((parts > 0).sum()),
            "has_wechat": int((wechat > 0).sum()),
            "has_hosts": int((hosts > 0).sum()),
            "has_sales": int((sales > 0).sum()),
        },
    }


def _q_type_analysis(df: pd.DataFrame) -> dict:
    """四、活动类型经营分析。"""
    completed_mask = df["activity_status"].isin(COMPLETED_STATUSES)
    type_stats = df.groupby("activity_type").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
    ).reset_index()
    effective = df[completed_mask].groupby("activity_type").size()
    type_stats["effective_activities"] = type_stats["activity_type"].map(effective).fillna(0).astype(int)
    type_stats["effective_rate"] = (type_stats["effective_activities"] / type_stats["activity_count"]).round(4)
    drone_col = "drone_display"
    if drone_col in df.columns:
        drone_counts = df[df[drone_col].astype(str).str.strip().ne("") & df[drone_col].notna()].groupby("activity_type").size()
        type_stats["drone_activities"] = type_stats["activity_type"].map(drone_counts).fillna(0).astype(int)
    else:
        type_stats["drone_activities"] = 0
    type_stats = type_stats.sort_values("activity_count", ascending=False)

    # type x month cross
    df_m = df.copy()
    df_m["month"] = df_m["activity_date"].dt.month
    tm = df_m.groupby(["activity_type", "month"]).size().reset_index(name="cnt")

    analyses = []
    if len(type_stats) > 0:
        top = type_stats.iloc[0]
        analyses.append(f"{top['activity_type']} 场次最高（{int(top['activity_count'])}场），"
                        f"销售额 {top['total_sales']/10000:.1f} 万元。")
        best_eff = type_stats[type_stats["effective_rate"] > 0].nlargest(1, "effective_rate")
        if len(best_eff) > 0:
            analyses.append(f"{best_eff.iloc[0]['activity_type']} 有效活动率最高（{best_eff.iloc[0]['effective_rate']:.0%}）。")

    return {
        "type_analysis": type_stats.to_dict("records"),
        "type_month": tm.to_dict("records"),
        "analysis": analyses,
    }


def _q_comparisons(df: pd.DataFrame) -> dict:
    """九、渠道 & 无人机 & 异业合作对比。"""
    sales = _safe(df["sales"])
    parts = _safe(df["participants"])
    wechat = _safe(df["wechat"])
    hosts = _safe(df["hosts"])

    st_col = df["store_type"] if "store_type" in df.columns else pd.Series("", index=df.index)
    # channel comparison
    channel_cmp = []
    for cat, mask_fn in [("Mall店", lambda s: s.str.contains("Mall|商场|购物中心", na=False)),
                         ("照材店", lambda s: s.str.contains("照材|摄影|数码", na=False)),
                         ("直营店", lambda s: s.str.contains("直营", na=False))]:
        mask = mask_fn(st_col)
        channel_cmp.append({
            "category": cat,
            "activity_count": int(mask.sum()),
            "total_sales": float(sales[mask].sum()),
            "total_hosts": int(hosts[mask].sum()),
            "total_participants": int(parts[mask].sum()),
            "total_wechat": int(wechat[mask].sum()),
        })

    # drone comparison
    if "drone_display" in df.columns:
        drone_mask = df["drone_display"].astype(str).str.strip().ne("") & df["drone_display"].notna()
    else:
        drone_mask = pd.Series(False, index=df.index)
    drone_cmp = [
        {"category": "无人机活动", "activity_count": int(drone_mask.sum()),
         "total_sales": float(sales[drone_mask].sum()),
         "total_hosts": int(hosts[drone_mask].sum()),
         "total_participants": int(parts[drone_mask].sum()),
         "total_wechat": int(wechat[drone_mask].sum())},
        {"category": "普通活动", "activity_count": int((~drone_mask).sum()),
         "total_sales": float(sales[~drone_mask].sum()),
         "total_hosts": int(hosts[~drone_mask].sum()),
         "total_participants": int(parts[~drone_mask].sum()),
         "total_wechat": int(wechat[~drone_mask].sum())},
    ]

    # cross-brand comparison
    if "partner_brands" in df.columns:
        coop_mask = df["partner_brands"].notna() & df["partner_brands"].astype(str).str.strip().ne("") & df["partner_brands"].astype(str).str.strip().ne("无")
    else:
        coop_mask = pd.Series(False, index=df.index)
    crossbrand_cmp = [
        {"category": "异业合作", "activity_count": int(coop_mask.sum()),
         "total_sales": float(sales[coop_mask].sum()),
         "total_hosts": int(hosts[coop_mask].sum()),
         "total_participants": int(parts[coop_mask].sum()),
         "total_wechat": int(wechat[coop_mask].sum())},
        {"category": "普通活动", "activity_count": int((~coop_mask).sum()),
         "total_sales": float(sales[~coop_mask].sum()),
         "total_hosts": int(hosts[~coop_mask].sum()),
         "total_participants": int(parts[~coop_mask].sum()),
         "total_wechat": int(wechat[~coop_mask].sum())},
    ]

    # partner brands ranking
    partner_brands = []
    if "partner_brands" in df.columns:
        brands = df.loc[coop_mask, "partner_brands"].dropna().str.split(r"[,，、]").explode().str.strip()
        brands = brands[brands.ne("") & brands.ne("无") & brands.ne("nan")]
        if len(brands) > 0:
            brand_counts = brands.value_counts().head(15)
            partner_brands = [{"brand": b, "coop_count": int(c)} for b, c in brand_counts.items()]

    return {
        "channel_cmp": channel_cmp,
        "drone_cmp": drone_cmp,
        "crossbrand_cmp": crossbrand_cmp,
        "partner_brands": partner_brands,
    }


def _q_conclusion(df: pd.DataFrame) -> dict:
    """十、经营结论与建议（合并诊断+建议）。"""
    diag = _q_diagnosis(df)
    recs = _q_recommendations(df)
    return {
        "findings": diag.get("findings", []),
        "recommendations": recs.get("recommendations", []),
    }



# ═══════════════════════════════════════════════════════════
# 新品上市复盘
# ═══════════════════════════════════════════════════════════

def product_launch_review(merged: pd.DataFrame, launch_date: str = "2026-06-10",
                          product_name: str = "Luna") -> dict:
    """生成新品上市复盘数据。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    df["wechat"] = _safe(df["wechat_adds"])
    df = df[df["activity_date"].notna() & (df["activity_date"] <= pd.Timestamp.now())]

    launch_ts = pd.Timestamp(launch_date)
    before = df[df["activity_date"] < launch_ts].copy()
    after = df[df["activity_date"] >= launch_ts].copy()

    print(f"上市复盘 {product_name}: 上市前 {len(before)} 场, 上市后 {len(after)} 场")

    result = {
        "product_name": product_name,
        "launch_date": launch_date,
        "before_count": len(before),
        "after_count": len(after),
        "section_1_overview": _l_overview(after, product_name, launch_date),
        "section_2_comparison": _l_comparison(before, after, launch_date),
        "section_3_profile": _l_profile(after, product_name),
        "section_4_cases": _l_cases(after, product_name),
        "section_5_conclusion": _l_conclusion(before, after, product_name),
    }
    return result


def _l_overview(after: pd.DataFrame, product: str, launch_date: str) -> dict:
    """上市效果总览。"""
    total = len(after)
    total_sales = float(after["sales"].sum())
    total_participants = int(after["participants"].sum())
    stores = int(after["store_name"].nunique())
    dealers = int(after["dealer"].nunique())

    # 月度趋势
    monthly = after.groupby(after["activity_date"].dt.to_period("M").astype(str)).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
    ).reset_index()

    summary = (f"{product} 上市后（{launch_date}起）共举办 {total} 场活动，"
               f"覆盖 {stores} 家门店、{dealers} 家代理商。"
               f"活动销售额 {total_sales/10000:.1f} 万元，参与 {total_participants:,} 人次。")

    return {
        "kpis": {
            "total_activities": total,
            "total_sales": total_sales,
            "total_participants": total_participants,
            "stores_covered": stores,
            "dealers_covered": dealers,
        },
        "monthly_trend": monthly.to_dict("records"),
        "summary": summary,
    }


def _l_comparison(before: pd.DataFrame, after: pd.DataFrame, launch_date: str) -> dict:
    """上市前后对比。"""
    def _stats(df):
        return {
            "activity_count": len(df),
            "total_sales": float(df["sales"].sum()),
            "avg_sales": float(df["sales"].mean()) if len(df) else 0,
            "total_participants": int(df["participants"].sum()),
            "avg_participants": float(df["participants"].mean()) if len(df) else 0,
            "stores_covered": int(df["store_name"].nunique()),
            "dealers_covered": int(df["dealer"].nunique()),
            "type_distribution": df["activity_type"].value_counts().to_dict(),
        }

    before_stats = _stats(before)
    after_stats = _stats(after)

    # 计算变化
    changes = {}
    for key in ["activity_count", "total_sales", "avg_sales", "total_participants",
                "avg_participants", "stores_covered", "dealers_covered"]:
        old = before_stats[key]
        new = after_stats[key]
        if old > 0:
            changes[key] = round((new - old) / old, 4)
        else:
            changes[key] = None

    analyses = []
    if changes.get("activity_count") is not None:
        c = changes["activity_count"]
        analyses.append(f"上市后活动数量 {'增长' if c > 0 else '下降'} {abs(c):.0%}"
                       f"（{before_stats['activity_count']} → {after_stats['activity_count']} 场）。")
    if changes.get("avg_sales") is not None:
        c = changes["avg_sales"]
        analyses.append(f"场均销售额 {'提升' if c > 0 else '下降'} {abs(c):.0%}"
                       f"（¥{before_stats['avg_sales']:,.0f} → ¥{after_stats['avg_sales']:,.0f}）。")
    if changes.get("stores_covered") is not None:
        c = changes["stores_covered"]
        analyses.append(f"覆盖门店 {'增加' if c > 0 else '减少'} {abs(c):.0%}"
                       f"（{before_stats['stores_covered']} → {after_stats['stores_covered']} 家）。")

    # 活动类型变化
    before_types = before_stats["type_distribution"]
    after_types = after_stats["type_distribution"]
    new_types = set(after_types.keys()) - set(before_types.keys())
    if new_types:
        analyses.append(f"上市后新增活动类型：{', '.join(new_types)}。")

    return {
        "before": before_stats,
        "after": after_stats,
        "changes": changes,
        "analysis": analyses,
    }


def _l_profile(after: pd.DataFrame, product: str) -> dict:
    """Luna活动画像。"""
    # 哪些活动最适合
    product_col = "luna_sales"
    has_luna = product_col in after.columns
    if has_luna:
        luna_sales = _safe(after[product_col])
        luna_active = after[luna_sales > 0].copy()
    else:
        luna_active = after.copy()

    # 区域效果
    region_col = "province_unit_final" if "province_unit_final" in after.columns else "province"
    if has_luna and len(luna_active) > 0:
        region_perf = luna_active.groupby(region_col).agg(
            activity_count=("record_id", "count"),
            luna_sales=(product_col, lambda x: _safe(x).sum()),
        ).reset_index().rename(columns={region_col: "region"})
        region_perf = region_perf[region_perf["region"].notna()].sort_values("luna_sales", ascending=False)
    else:
        region_perf = after.groupby(region_col).agg(
            activity_count=("record_id", "count"),
            luna_sales=("sales", "sum"),
        ).reset_index().rename(columns={region_col: "region"})
        region_perf = region_perf[region_perf["region"].notna()].sort_values("activity_count", ascending=False)

    # 门店效果
    if has_luna and len(luna_active) > 0:
        store_perf = luna_active.groupby("store_name").agg(
            activity_count=("record_id", "count"),
            luna_sales=(product_col, lambda x: _safe(x).sum()),
            total_sales=("sales", "sum"),
        ).reset_index().sort_values("luna_sales", ascending=False).head(10)
    else:
        store_perf = after.groupby("store_name").agg(
            activity_count=("record_id", "count"),
            total_sales=("sales", "sum"),
        ).reset_index().sort_values("total_sales", ascending=False).head(10)

    # 代理商效果
    dealer_perf = after.groupby("dealer").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index().sort_values("total_sales", ascending=False).head(10)

    # 最佳活动类型
    if has_luna and len(luna_active) > 0:
        type_perf = luna_active.groupby("activity_type").agg(
            activity_count=("record_id", "count"),
            total_sales=("sales", "sum"),
            total_participants=("participants", "sum"),
        ).reset_index()
        type_perf["avg_sales"] = type_perf.apply(
            lambda r: round(r["total_sales"] / r["activity_count"], 2) if r["activity_count"] else 0, axis=1)
        type_perf = type_perf.sort_values("total_sales", ascending=False)
    else:
        type_perf = after.groupby("activity_type").agg(
            activity_count=("record_id", "count"),
            total_sales=("sales", "sum"),
            total_participants=("participants", "sum"),
            avg_sales=("sales", "mean"),
        ).reset_index().sort_values("avg_sales", ascending=False)

    analyses = []
    if len(region_perf) > 0:
        analyses.append(f"{product} 活动效果最好的区域：{region_perf.iloc[0]['region']}。")
    if len(store_perf) > 0:
        analyses.append(f"门店效果最佳：{store_perf.iloc[0]['store_name']}。")
    if len(type_perf) > 0:
        analyses.append(f"最适合 {product} 的活动类型：{type_perf.iloc[0]['activity_type']}。")

    return {
        "region_perf": region_perf.to_dict("records"),
        "store_perf": store_perf.to_dict("records"),
        "dealer_perf": dealer_perf.to_dict("records"),
        "type_perf": type_perf.to_dict("records"),
        "analysis": analyses,
    }


def _l_cases(after: pd.DataFrame, product: str) -> dict:
    """优秀Luna案例。"""
    completed = after[after["activity_status"].isin(COMPLETED_STATUSES)].copy()
    if len(completed) == 0:
        completed = after.copy()

    # 综合评分
    completed["score"] = (completed["sales"].rank(pct=True) * 0.4 +
                          completed["participants"].rank(pct=True) * 0.3 +
                          completed["wechat"].rank(pct=True) * 0.3)
    top = completed.nlargest(10, "score")

    cases = top[["activity_desc", "activity_type", "store_name", "dealer",
                 "sales", "participants", "wechat", "score",
                 "activity_date", "province"]].to_dict("records")

    # SOP 总结
    analyses = []
    if cases:
        type_dist = top["activity_type"].value_counts()
        analyses.append(f"优秀案例活动类型分布：{', '.join([f'{t}({c})' for t, c in type_dist.items()])}。")
        avg_sales = float(top["sales"].mean())
        avg_part = float(top["participants"].mean())
        analyses.append(f"优秀案例场均销售 ¥{avg_sales:,.0f}，场均参与 {avg_part:.0f} 人。")
        analyses.append(f"Luna 活动 SOP 建议："
                       "①选择高客流门店；②配置体验+教学环节；③设置企微添加激励；"
                       "④配合外拍展示全景优势；⑤现场限时优惠促成交。")

    return {"cases": cases, "analysis": analyses}


def _l_conclusion(before: pd.DataFrame, after: pd.DataFrame, product: str) -> dict:
    """经营结论。"""
    before_count = len(before)
    after_count = len(after)
    after_sales = float(after["sales"].sum())
    before_avg = float(before["sales"].mean()) if len(before) else 0
    after_avg = float(after["sales"].mean()) if len(after) else 0

    # 上市效果总结
    if after_count > before_count:
        effect = f"{product} 上市带动活动数量增长，上市后 {after_count} 场 vs 上市前 {before_count} 场。"
    else:
        effect = f"{product} 上市后活动 {after_count} 场，与上市前 {before_count} 场相比有所调整。"

    # 成功经验
    successes = [
        f"上市后覆盖 {after['store_name'].nunique()} 家门店，品牌曝光广泛。",
        f"活动参与 {int(after['participants'].sum()):,} 人次，用户触达效果好。",
        f"企微添加 {int(_safe(after['wechat_adds']).sum()):,} 人，私域沉淀有成效。",
    ]

    # 存在问题
    problems = []
    comp = after[after["activity_status"].isin(COMPLETED_STATUSES)]
    if len(comp) > 0:
        low = (comp["sales"] < 500).sum()
        if low / len(comp) > 0.5:
            problems.append(f"{low}/{len(comp)} 场已完成活动销售低于 500 元，转化不足。")
    if after_avg < before_avg:
        problems.append(f"场均销售额下降（¥{before_avg:,.0f} → ¥{after_avg:,.0f}），活动质量需提升。")
    problems.append("活动完成率偏低，复盘机制需加强。")

    # Q3建议
    q3_recs = [
        f"加大 {product} 专项活动投入，重点推广外拍活动和新品品鉴会。",
        "标准化 Luna 活动 SOP，向更多门店复制。",
        "加强活动销售转化设计，提升场均销售额。",
        "建立活动复盘制度，沉淀优秀经验。",
    ]

    return {
        "effect_summary": effect,
        "successes": successes,
        "problems": problems,
        "q3_recommendations": q3_recs,
    }


if __name__ == "__main__":
    from .data_model import build_all_models
    models = build_all_models()
    merged = models["merged_activity_store"]

    print("\n" + "=" * 60)
    print("Q2 季度经营复盘")
    print("=" * 60)
    q2 = quarterly_review(merged, 2026, 2)
    print(f"\n总览: {q2['section_1_overview']['summary']}")

    print("\n" + "=" * 60)
    print("Luna 上市复盘")
    print("=" * 60)
    luna = product_launch_review(merged)
    print(f"\n总览: {luna['section_1_overview']['summary']}")
