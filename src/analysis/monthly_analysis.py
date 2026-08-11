"""每月经营分析 (Monthly Analysis)。

输出月度经营复盘：总览、趋势、门店/代理商/产品/区域排名。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from .common import prepare, safe_num, finding, rec, today_str
from .common import (
    zero_activity_stores, zero_activity_dealers,
    low_conversion_stores, low_conversion_dealers,
    low_wechat_stores, low_wechat_dealers,
    activity_count_stores, activity_count_dealers,
)
from .common import compute_health_score


def monthly_analysis(merged: pd.DataFrame, year: int | None = None,
                     month: int | None = None,
                     dim_store: pd.DataFrame | None = None,
                     dim_dealer: pd.DataFrame | None = None) -> dict:
    """生成月度经营分析。

    Args:
        merged: merged_activity_store 宽表
        year/month: 指定月份，None 则取数据最新月份
    """
    df = prepare(merged)
    if year is None or month is None:
        latest = pd.Timestamp(today_str(df))
        year, month = latest.year, latest.month
    label = f"{year}年{month}月"

    month_df = df[
        (df["activity_date"].dt.year == year) & (df["activity_date"].dt.month == month)
    ].copy()

    # 上月对比
    prev_date = pd.Timestamp(year=year, month=month, day=1) - pd.DateOffset(months=1)
    prev_df = df[
        (df["activity_date"].dt.year == prev_date.year)
        & (df["activity_date"].dt.month == prev_date.month)
    ].copy()

    # ── 经营数据 ─────────────────────────────
    data = {
        "month_label": label,
        "year": year,
        "month": month,
        "activity_count": int(len(month_df)),
        "total_sales": float(month_df["sales"].sum()),
        "total_participants": int(month_df["participants"].sum()),
        "total_wechat": int(month_df["wechat"].sum()),
        "total_hosts": int(month_df["hosts"].sum()),
        "stores_covered": int(month_df["store_name"].nunique()),
        "dealers_covered": int(month_df["dealer_final"].nunique()) if "dealer_final" in month_df.columns else int(month_df["dealer"].nunique()),
        "completed_count": int(month_df["is_completed"].sum()),
        "completion_rate": float(month_df["is_completed"].mean()) if len(month_df) else 0,
        "health_score": compute_health_score(month_df),
    }

    def _stats(d):
        return {
            "count": int(len(d)),
            "sales": float(d["sales"].sum()),
            "participants": int(d["participants"].sum()),
            "stores": int(d["store_name"].nunique()),
            "wechat": int(d["wechat"].sum()),
        }
    cur = _stats(month_df)
    prev = _stats(prev_df)
    changes = {}
    for k in cur:
        changes[k] = (cur[k] - prev[k]) / prev[k] if prev[k] else None
    data["prev_stats"] = prev
    data["changes"] = changes

    # 月内每日趋势
    daily = month_df.groupby(month_df["activity_date"].dt.day).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
    ).reset_index().rename(columns={"activity_date": "day"})
    data["daily_trend"] = daily.to_dict("records")

    # 活动类型分布
    by_type = month_df.groupby("activity_type").agg(
        count=("record_id", "count"),
        sales=("sales", "sum"),
        participants=("participants", "sum"),
    ).reset_index().sort_values("count", ascending=False)
    data["by_type"] = by_type.to_dict("records")

    # 门店排名 Top20
    data["store_ranking"] = _rank_stores(month_df)
    # 代理商排名 Top20
    dealer_col = "dealer_final" if "dealer_final" in month_df.columns else "dealer"
    data["dealer_ranking"] = _rank_dealers(month_df, dealer_col)
    # 产品表现
    data["product_perf"] = _product_perf(month_df)
    # 区域表现 Top10
    region_col = "dim_province_unit" if "dim_province_unit" in month_df.columns else "province"
    data["region_perf"] = _rank_regions(month_df, region_col)

    # ── 活动量与转化分析 ─────────────────────
    data["activity_count_store"] = activity_count_stores(month_df)
    data["activity_count_dealer"] = activity_count_dealers(month_df, dealer_col)
    data["zero_activity_stores"] = zero_activity_stores(month_df, dim_store) if dim_store is not None else []
    data["zero_activity_dealers"] = zero_activity_dealers(month_df, dim_dealer, dealer_col) if dim_dealer is not None else []
    data["low_conversion_stores"] = low_conversion_stores(month_df)
    data["low_conversion_dealers"] = low_conversion_dealers(month_df, dealer_col)
    data["low_wechat_stores"] = low_wechat_stores(month_df)
    data["low_wechat_dealers"] = low_wechat_dealers(month_df, dealer_col)

    # ── 经营结论 ─────────────────────────────
    findings = []
    if cur["count"] == 0:
        findings.append(finding(
            f"{label} 无活动数据",
            "当月无活动提报或数据未同步",
            "月度经营达成归零",
            "立即排查并恢复活动提报",
            severity="high",
        ))
    else:
        chg = changes["count"]
        chg_txt = f"环比{('+'+str(round(chg*100))+'%') if chg and chg>0 else (str(round(chg*100))+'%' if chg else '持平')}"
        findings.append(finding(
            f"{label} 共 {cur['count']} 场活动，销售额 {cur['sales']:.0f} 元，{chg_txt}",
            "月度经营节奏" + ("向好" if cur["count"] >= prev["count"] else "走弱"),
            "影响季度经营达成",
            "对走弱区域专项督导，巩固向好区域打法",
            severity="medium",
        ))

    # 产品维度结论
    prod = data["product_perf"]
    if prod:
        top_p = max(prod, key=lambda x: x.get("total_sales", 0))
        findings.append(finding(
            f"本月产品表现最佳：{top_p['product']}，销量 {top_p['total_sales']} 台",
            "该产品活动适配度高，转化强",
            "可加大该产品活动投放",
            f"扩大 {top_p['product']} 体验活动覆盖",
            severity="low",
        ))

    # 门店排名结论
    if data["store_ranking"]:
        top_s = data["store_ranking"][0]
        findings.append(finding(
            f"门店冠军：{top_s['store_name']}，{top_s['activity_count']} 场活动，销售 {top_s['total_sales']:.0f} 元",
            "该门店活动执行与转化能力突出",
            "可作为标杆复制",
            "提炼冠军门店打法，同省区推广",
            severity="low",
        ))

    # ── 经营建议 ─────────────────────────────
    recommendations = []
    recommendations.append(rec(
        f"{label} 经营复盘",
        f"本月 {cur['count']} 场活动，销售 {cur['sales']:.0f} 元，企微蓄水 {cur['wechat']} 人，覆盖 {cur['stores']} 家门店。",
        owner="运营部", priority=1, timeline="本月",
    ))
    if data["store_ranking"]:
        top_s = data["store_ranking"][0]
        recommendations.append(rec(
            "复制冠军门店打法",
            f"{top_s['store_name']} 本月销售 {top_s['total_sales']:.0f} 元，提炼其活动模式推广至同省区",
            owner="省区负责人", priority=2, timeline="下月",
        ))
    if prod:
        top_p = max(prod, key=lambda x: x.get("total_sales", 0))
        recommendations.append(rec(
            "重点产品加码",
            f"{top_p['product']} 转化最佳，下月增加其专项活动场次",
            owner="运营部", priority=2, timeline="下月",
        ))
    recommendations.append(rec(
        "下月经营规划",
        "基于本月达成缺口与优秀案例，制定下月活动场次、销售目标与门店覆盖计划",
        owner="运营部", priority=1, timeline="下月",
    ))

    return {
        "label": label,
        "type": "monthly",
        "data": data,
        "findings": findings,
        "recommendations": recommendations,
    }


def _rank_stores(df: pd.DataFrame) -> list:
    if len(df) == 0:
        return []
    g = df.groupby("store_name").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
    ).reset_index().sort_values("total_sales", ascending=False).head(20)
    return g.to_dict("records")


def _rank_dealers(df: pd.DataFrame, col: str) -> list:
    if len(df) == 0 or col not in df.columns:
        return []
    g = df.groupby(col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index().sort_values("total_sales", ascending=False).head(20)
    g = g.rename(columns={col: "dealer"})
    return g.to_dict("records")


def _product_perf(df: pd.DataFrame) -> list:
    if len(df) == 0:
        return []
    products = ["luna", "x_series", "go_series", "ace_series", "drone"]
    names = ["Luna", "X系列", "Go", "Ace", "无人机"]
    rows = []
    for p, n in zip(products, names):
        if p in df.columns:
            total = float(df[p].sum())
            if total > 0:
                rows.append({"product": n, "total_sales": total,
                             "activity_count": int(len(df[df[p] > 0]))})
    rows.sort(key=lambda x: x["total_sales"], reverse=True)
    return rows


def _rank_regions(df: pd.DataFrame, col: str) -> list:
    if len(df) == 0 or col not in df.columns:
        return []
    g = df.groupby(col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index().sort_values("total_sales", ascending=False).head(10)
    g = g.rename(columns={col: "region"})
    return g.to_dict("records")
