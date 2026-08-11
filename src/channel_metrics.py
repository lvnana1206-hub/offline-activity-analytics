"""渠道分析指标：Mall店 vs 照材店、无人机 vs 普通活动、异业合作品牌排行。

所有函数接受 merged DataFrame，返回 DataFrame 或 dict，不修改原始数据。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from .config import COMPLETED_STATUSES
from .metrics import _safe_numeric
from .filter_engine import classify_store_type


def _base_agg(df: pd.DataFrame) -> dict:
    """计算一组活动的基础汇总指标。"""
    sales = _safe_numeric(df["sales_clean"])
    parts = _safe_numeric(df["participants"])
    wechat = _safe_numeric(df["wechat_adds"])
    hosts = _safe_numeric(df["converted_hosts"])
    total = len(df)
    completed = df["activity_status"].isin(COMPLETED_STATUSES).sum()
    return {
        "count": total,
        "completed": int(completed),
        "completion_rate": float(completed / total) if total else 0,
        "sales": float(sales.sum()),
        "avg_sales": float(sales[sales > 0].mean()) if (sales > 0).any() else 0,
        "participants": int(parts.sum()),
        "wechat": int(wechat.sum()),
        "hosts": int(hosts.sum()),
        "stores": int(df["store_name"].nunique()),
        "luna": int(_safe_numeric(df["luna_sales"]).sum()) if "luna_sales" in df.columns else 0,
        "x": int(_safe_numeric(df["x_series_sales"]).sum()) if "x_series_sales" in df.columns else 0,
        "go": int(_safe_numeric(df["go_series_sales"]).sum()) if "go_series_sales" in df.columns else 0,
        "ace": int(_safe_numeric(df["ace_series_sales"]).sum()) if "ace_series_sales" in df.columns else 0,
        "drone": int(_safe_numeric(df["drone_sales"]).sum()) if "drone_sales" in df.columns else 0,
        "conv_rate": float(hosts.sum() / parts.sum() * 100) if parts.sum() else 0,
    }


def channel_comparison(merged: pd.DataFrame) -> dict:
    """Mall店 vs 照材店经营对比。"""
    df = merged.copy()
    masks = {}
    for idx in df.index:
        st = classify_store_type(
            df.get("store_type", pd.Series()).get(idx),
            df.get("store_category_final", pd.Series()).get(idx),
            df.get("dim_store_category", pd.Series()).get(idx),
        )
        masks.setdefault(st, []).append(idx)

    mall_df = df.loc[masks.get("Mall店", [])]
    material_df = df.loc[masks.get("照材店", [])]
    direct_df = df.loc[masks.get("直营店", [])]

    return {
        "mall": _base_agg(mall_df),
        "material": _base_agg(material_df),
        "direct": _base_agg(direct_df),
    }


def drone_comparison(merged: pd.DataFrame) -> dict:
    """无人机活动 vs 普通活动对比。"""
    df = merged.copy()
    if "drone_display" not in df.columns:
        drone_mask = pd.Series(False, index=df.index)
    else:
        drone_mask = df["drone_display"].astype(str).str.strip().ne("") & df["drone_display"].notna()
    drone_df = df[drone_mask]
    normal_df = df[~drone_mask]
    return {
        "drone": _base_agg(drone_df),
        "normal": _base_agg(normal_df),
    }


def brand_ranking(merged: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """异业合作品牌排行。"""
    df = merged.copy()
    if "partner_brands" not in df.columns:
        return pd.DataFrame(columns=["brand", "count", "sales", "avg_sales"])
    df["sales"] = _safe_numeric(df["sales_clean"])
    # split partner_brands by comma/、 and explode
    brands = df["partner_brands"].dropna().str.split(r"[,，、]").explode().str.strip()
    brands = brands[brands.ne("") & brands.ne("无") & brands.ne("nan")]
    if len(brands) == 0:
        return pd.DataFrame(columns=["brand", "count", "sales", "avg_sales"])
    brand_df = pd.DataFrame({"brand": brands, "sales_idx": brands.index})
    brand_df = brand_df.merge(df[["sales"]], left_on="sales_idx", right_index=True, how="left")
    result = brand_df.groupby("brand").agg(
        count=("brand", "count"),
        sales=("sales", "sum"),
    ).reset_index()
    result["avg_sales"] = result["sales"] / result["count"]
    return result.sort_values("count", ascending=False).head(top_n)


def conversion_funnel(merged: pd.DataFrame) -> dict:
    """活动转化漏斗：活动场次 → 参与人数 → 企微添加 → 转化主机。"""
    df = merged.copy()
    sales = _safe_numeric(df["sales_clean"])
    parts = _safe_numeric(df["participants"])
    wechat = _safe_numeric(df["wechat_adds"])
    hosts = _safe_numeric(df["converted_hosts"])
    total_activities = len(df)
    total_participants = int(parts.sum())
    total_wechat = int(wechat.sum())
    total_hosts = int(hosts.sum())
    total_sales = float(sales.sum())

    return {
        "stages": [
            {"name": "活动场次", "value": total_activities},
            {"name": "参与人数", "value": total_participants},
            {"name": "企微添加", "value": total_wechat},
            {"name": "转化主机", "value": total_hosts},
            {"name": "销售额", "value": int(total_sales)},
        ],
        "rates": {
            "participation_rate": total_participants / total_activities if total_activities else 0,
            "wechat_rate": total_wechat / total_participants if total_participants else 0,
            "conversion_rate": total_hosts / total_participants if total_participants else 0,
            "sales_per_host": total_sales / total_hosts if total_hosts else 0,
        },
    }


def product_type_cross(merged: pd.DataFrame) -> pd.DataFrame:
    """产品 x 活动类型交叉分析矩阵。"""
    df = merged.copy()
    product_cols = {
        "Luna": "luna_sales",
        "X系列": "x_series_sales",
        "Go系列": "go_series_sales",
        "Ace系列": "ace_series_sales",
    }
    rows = []
    for atype, group in df.groupby("activity_type"):
        row = {"activity_type": atype}
        for pname, pcol in product_cols.items():
            if pcol in group.columns:
                row[pname] = int(_safe_numeric(group[pcol]).sum())
            else:
                row[pname] = 0
        rows.append(row)
    return pd.DataFrame(rows)


def type_month_cross(merged: pd.DataFrame) -> pd.DataFrame:
    """活动类型 x 月份交叉分析。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df = df.dropna(subset=["activity_date"])
    df["year_month"] = df["activity_date"].dt.to_period("M").astype(str)
    result = df.groupby(["activity_type", "year_month"]).size().reset_index(name="count")
    return result


def product_monthly(merged: pd.DataFrame) -> pd.DataFrame:
    """产品线月度销量趋势。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df = df.dropna(subset=["activity_date"])
    df["year_month"] = df["activity_date"].dt.to_period("M").astype(str)
    product_cols = {
        "Luna": "luna_sales",
        "X系列": "x_series_sales",
        "Go系列": "go_series_sales",
        "Ace系列": "ace_series_sales",
    }
    rows = []
    for ym, group in df.groupby("year_month"):
        row = {"year_month": ym}
        for pname, pcol in product_cols.items():
            if pcol in group.columns:
                row[pname] = int(_safe_numeric(group[pcol]).sum())
            else:
                row[pname] = 0
        rows.append(row)
    return pd.DataFrame(rows).sort_values("year_month")


def monthly_multi_trend(merged: pd.DataFrame) -> pd.DataFrame:
    """月度多维度趋势：活动数、销售额、企微、参与、有效活动、无人机。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df = df.dropna(subset=["activity_date"])
    df["year_month"] = df["activity_date"].dt.to_period("M").astype(str)
    df["sales"] = _safe_numeric(df["sales_clean"])
    df["parts"] = _safe_numeric(df["participants"])
    df["wechat"] = _safe_numeric(df["wechat_adds"])

    if "drone_display" in df.columns:
        drone_mask = df["drone_display"].astype(str).str.strip().ne("") & df["drone_display"].notna()
    else:
        drone_mask = pd.Series(False, index=df.index)

    result = df.groupby("year_month").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        participants=("parts", "sum"),
        wechat_adds=("wechat", "sum"),
        effective=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        drone_count=("record_id", lambda x: drone_mask.loc[x.index].sum()),
    ).reset_index()
    return result.sort_values("year_month")
