"""统一指标体系。

所有指标基于 merged_activity_store 统一计算，禁止在页面层重复计算。
分为五组：活动指标、门店指标、代理商指标、产品指标、区域指标。
"""

from __future__ import annotations

import pandas as pd
from .config import COMPLETED_STATUSES
import numpy as np


def _safe_numeric(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


# ── 活动指标 ────────────────────────────────────────────────

def activity_metrics(merged: pd.DataFrame) -> dict:
    """活动维度指标。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])
    df["wechat_adds"] = _safe_numeric(df["wechat_adds"])
    df["hosts"] = _safe_numeric(df["converted_hosts"])

    total = len(df)
    completed = (df["activity_status"].isin(COMPLETED_STATUSES)).sum()
    terminated = (df["activity_status"] == "终止").sum()
    in_progress = df["activity_status"].isin(["交付执行中", "复盘收集中"]).sum()

    # 有效活动 = 已完成（有实际产出）
    valid = df[df["activity_status"].isin(COMPLETED_STATUSES)]
    valid_sales = _safe_numeric(valid["sales_clean"])

    return {
        "total_activities": total,
        "completed": int(completed),
        "in_progress": int(in_progress),
        "terminated": int(terminated),
        "pending": int(total - completed - in_progress - terminated),
        "completion_rate": completed / total if total else 0,
        "total_sales": float(df["sales"].sum()),
        "total_participants": int(df["participants"].sum()),
        "total_wechat_adds": int(df["wechat_adds"].sum()),
        "total_converted_hosts": int(df["hosts"].sum()),
        "avg_sales_per_activity": float(valid_sales.mean()) if len(valid_sales) else 0,
        "avg_participants": float(df["participants"].mean()),
        "avg_conversion_rate": float(_safe_numeric(df["conversion_rate_pct"]).mean()),
        # ── 相对值效率指标 ──
        "wechat_add_rate": float(df["wechat_adds"].sum() / df["participants"].sum()) if df["participants"].sum() else 0,
        "host_conversion_rate": float(df["hosts"].sum() / df["participants"].sum()) if df["participants"].sum() else 0,
        "sales_per_participant": float(df["sales"].sum() / df["participants"].sum()) if df["participants"].sum() else 0,
        "sales_per_host": float(df["sales"].sum() / df["hosts"].sum()) if df["hosts"].sum() else 0,
        "wechat_per_activity": float(df["wechat_adds"].sum() / total) if total else 0,
        "participants_per_activity": float(df["participants"].sum() / total) if total else 0,
        "hosts_per_activity": float(df["hosts"].sum() / total) if total else 0,
    }


def activity_metrics_by_type(merged: pd.DataFrame) -> pd.DataFrame:
    """按活动类型汇总指标。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])
    df["wechat_adds"] = _safe_numeric(df["wechat_adds"])
    df["hosts"] = _safe_numeric(df["converted_hosts"])

    result = df.groupby("activity_type").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        avg_participants=("participants", "mean"),
        total_wechat_adds=("wechat_adds", "sum"),
        total_converted_hosts=("hosts", "sum"),
        unique_stores=("store_name", "nunique"),
    ).reset_index()
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    result["sales_per_activity"] = result["total_sales"] / result["activity_count"]
    result["wechat_add_rate"] = result["total_wechat_adds"] / result["total_participants"]
    result["host_conversion_rate"] = result["total_converted_hosts"] / result["total_participants"]
    result["sales_per_participant"] = result["total_sales"] / result["total_participants"]
    result["participants_per_activity"] = result["total_participants"] / result["activity_count"]
    result["wechat_per_activity"] = result["total_wechat_adds"] / result["activity_count"]
    return result.sort_values("activity_count", ascending=False)


def activity_monthly_trend(merged: pd.DataFrame) -> pd.DataFrame:
    """按月汇总活动趋势。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df = df.dropna(subset=["activity_date"])
    df["year_month"] = df["activity_date"].dt.to_period("M").astype(str)
    df["sales"] = _safe_numeric(df["sales_clean"])

    result = df.groupby("year_month").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        unique_stores=("store_name", "nunique"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
    ).reset_index()
    return result.sort_values("year_month")


# ── 门店指标 ────────────────────────────────────────────────

def store_metrics(merged: pd.DataFrame, dim_store: pd.DataFrame) -> pd.DataFrame:
    """门店维度指标：活动能力、完成率、销售。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])

    result = df.groupby("store_name").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        total_wechat_adds=("wechat_adds", lambda x: _safe_numeric(x).sum()),
        activity_types=("activity_type", "nunique"),
        dealers=("dealer", "nunique"),
        last_activity_date=("activity_date", "max"),
    ).reset_index()
    result["completion_rate"] = result["completed_count"] / result["activity_count"]

    # 关联门店维度信息
    store_info = dim_store[["store_name", "province_unit", "region", "city",
                            "store_level", "store_category", "business_status"]].copy()
    store_info = store_info.drop_duplicates(subset="store_name", keep="first")
    result = result.merge(store_info, on="store_name", how="left")

    # 无活动门店
    all_stores = dim_store[dim_store["store_name"].notna()]["store_name"].unique()
    active_stores = df["store_name"].dropna().unique()
    inactive_stores = set(all_stores) - set(active_stores)

    result.attrs["inactive_store_count"] = len(inactive_stores)
    result.attrs["active_store_count"] = len(active_stores)
    return result.sort_values("activity_count", ascending=False)


# ── 代理商指标 ──────────────────────────────────────────────

def dealer_metrics(merged: pd.DataFrame, dim_dealer: pd.DataFrame) -> pd.DataFrame:
    """代理商维度指标：覆盖率、活动质量、执行率。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])
    # 用 dealer_final 优先
    df["dealer"] = df.get("dealer_final", df["dealer"])
    if "wechat_adds" in df.columns:
        df["wechat_adds"] = _safe_numeric(df["wechat_adds"])

    result = df.groupby("dealer").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        total_wechat_adds=("wechat_adds", "sum"),
        active_stores=("store_name", "nunique"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    result["sales_per_activity"] = result["total_sales"] / result["activity_count"]

    # 关联代理商维度
    result = result.merge(dim_dealer[["dealer", "store_count", "mall_count",
                                       "camera_count", "active_count"]],
                          on="dealer", how="left")
    result["store_coverage_rate"] = result["active_stores"] / result["store_count"]
    result["sales_per_store"] = result["total_sales"] / result["active_stores"]
    result["wechat_add_rate"] = result["total_wechat_adds"] / result["total_participants"]
    result["host_conversion_rate"] = result["total_converted_hosts"] / result["total_participants"] if "total_converted_hosts" in result.columns else 0
    result["activity_per_store"] = result["activity_count"] / result["store_count"]
    return result.sort_values("activity_count", ascending=False)


# ── 产品指标 ────────────────────────────────────────────────

def product_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """产品维度指标：各产品系列在活动中的表现。"""
    df = merged.copy()
    product_cols = {
        "Luna": "luna_sales",
        "X系列": "x_series_sales",
        "Go系列": "go_series_sales",
        "Ace系列": "ace_series_sales",
        "无人机": "drone_sales",
    }

    rows = []
    for product_name, col in product_cols.items():
        if col not in df.columns:
            continue
        sales = _safe_numeric(df[col])
        activities_with_product = (sales > 0).sum()
        total_sales = float(sales.sum())
        avg_sales = float(sales[sales > 0].mean()) if activities_with_product else 0

        # 按活动类型看该产品的适配度
        df_prod = df[sales > 0]
        top_types = df_prod["activity_type"].value_counts().head(3)

        rows.append({
            "product": product_name,
            "total_sales": total_sales,
            "activity_count": activities_with_product,
            "avg_sales_per_activity": avg_sales,
            "top_activity_types": "/".join(top_types.index.tolist()),
            "market_share": 0,  # 后面计算
        })

    result = pd.DataFrame(rows)
    total = result["total_sales"].sum()
    result["market_share"] = result["total_sales"] / total if total else 0
    return result.sort_values("total_sales", ascending=False)


# ── 区域指标 ────────────────────────────────────────────────

def region_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """区域维度指标：按省区单元和省份。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])
    # 用 province_unit_final 优先
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"

    result = df.groupby(region_col).agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        active_stores=("store_name", "nunique"),
        dealers=("dealer", "nunique"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()
    result = result.rename(columns={region_col: "region"})
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    result["sales_per_store"] = result["total_sales"] / result["active_stores"]
    result["sales_per_activity"] = result["total_sales"] / result["activity_count"]
    result["participants_per_activity"] = result["total_participants"] / result["activity_count"]
    result["activity_per_dealer"] = result["activity_count"] / result["dealers"]
    result = result[result["region"].notna()]
    return result.sort_values("activity_count", ascending=False)


def province_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """省份维度指标。"""
    df = merged.copy()
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["participants"] = _safe_numeric(df["participants"])

    result = df.groupby("province").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        active_stores=("store_name", "nunique"),
        cities=("city", "nunique"),
    ).reset_index()
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    result = result[result["province"].notna()]
    return result.sort_values("activity_count", ascending=False)


# ── 汇总接口 ────────────────────────────────────────────────

def compute_all_metrics(merged: pd.DataFrame, dim_store: pd.DataFrame,
                        dim_dealer: pd.DataFrame) -> dict:
    """一次性计算所有指标，返回统一字典。"""
    print("计算统一指标体系...")
    metrics = {
        "activity_overview": activity_metrics(merged),
        "activity_by_type": activity_metrics_by_type(merged),
        "activity_monthly_trend": activity_monthly_trend(merged),
        "store_metrics": store_metrics(merged, dim_store),
        "dealer_metrics": dealer_metrics(merged, dim_dealer),
        "product_metrics": product_metrics(merged),
        "region_metrics": region_metrics(merged),
        "province_metrics": province_metrics(merged),
    }
    for k, v in metrics.items():
        if isinstance(v, pd.DataFrame):
            print(f"  {k}: {len(v)} 行")
        elif isinstance(v, dict):
            print(f"  {k}: {len(v)} 项")
    return metrics


if __name__ == "__main__":
    from .data_model import build_all_models
    models = build_all_models()
    all_metrics = compute_all_metrics(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )
    print("\n=== 活动概览 ===")
    for k, v in all_metrics["activity_overview"].items():
        print(f"  {k}: {v}")
    print("\n=== 活动类型 ===")
    print(all_metrics["activity_by_type"][["activity_type", "activity_count",
          "completion_rate", "total_sales"]].to_string(index=False))
