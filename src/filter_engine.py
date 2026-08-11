"""筛选引擎：对 merged_activity_store 按门店类型/代理商类型/时间段筛选。

不修改原始数据，返回筛选后的副本，供 MetricsCenter 重算指标。
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# -- 门店类型分类 -----------------------------------------------

def classify_store_type(store_type, store_category_final=None, dim_store_category=None):
    """归一化为 Mall店|照材店|直营店|其他。"""
    raw = ""
    for v in (store_type, store_category_final, dim_store_category):
        if v is not None and str(v).strip() not in ("", "nan", "None"):
            raw = str(v)
            break
    if not raw:
        return "其他"
    combined = raw
    first = raw.split(",")[0].split("，")[0].strip()
    if "直营" in combined:
        return "直营店"
    if "Mall" in combined or "mall" in combined:
        return "Mall店"
    if "照材" in combined:
        return "照材店"
    if first in ("Mall店", "照材店", "直营店"):
        return first
    return "其他"


# -- 代理商类型分类 ---------------------------------------------

def classify_dealer_type(mall_count, camera_count):
    """根据门店结构将代理商归为 Mall商|照材商|综合。"""
    mc = int(mall_count or 0)
    cc = int(camera_count or 0)
    if mc == 0 and cc == 0:
        return "综合"
    if mc > cc * 2:
        return "Mall商"
    if cc > mc * 2:
        return "照材商"
    return "综合"


def build_dealer_type_map(dim_dealer: pd.DataFrame) -> dict:
    """构建 {dealer_name: dealer_type} 映射。"""
    result = {}
    for _, row in dim_dealer.iterrows():
        result[row["dealer"]] = classify_dealer_type(
            row.get("mall_count"), row.get("camera_count")
        )
    return result


# -- 时间段解析 -------------------------------------------------

def resolve_date_range(period, date_from, date_to, period_value):
    """将筛选器时间参数解析为 (start, end) Timestamp 元组。"""
    if period == "custom":
        start = pd.to_datetime(date_from, errors="coerce") if date_from else None
        end = pd.to_datetime(date_to, errors="coerce") if date_to else None
        if end is not None:
            end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        return start, end
    if period == "day" and period_value:
        d = pd.to_datetime(period_value, errors="coerce")
        if pd.isna(d):
            return None, None
        return d, d + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    if period == "week" and period_value:
        d = pd.to_datetime(period_value, errors="coerce")
        if pd.isna(d):
            return None, None
        start = d - pd.Timedelta(days=d.weekday())
        end = start + pd.Timedelta(days=7) - pd.Timedelta(seconds=1)
        return start, end
    if period == "month" and period_value:
        d = pd.to_datetime(period_value, errors="coerce")
        if pd.isna(d):
            return None, None
        start = d.to_period("M").start_time
        end = d.to_period("M").end_time
        return start, end
    return None, None


# -- 主筛选函数 -------------------------------------------------

def filter_merged(
    merged: pd.DataFrame,
    dim_dealer: pd.DataFrame,
    *,
    store_type: str = "",
    dealer_type: str = "",
    period: str = "all",
    date_from: str = "",
    date_to: str = "",
    period_value: str = "",
) -> pd.DataFrame:
    """对 merged_activity_store 执行筛选，返回副本。"""
    df = merged.copy()
    if len(df) == 0:
        return df

    # 1. 门店类型筛选
    if store_type and store_type != "all":
        st_col = df.get("store_type")
        sc_col = df.get("store_category_final")
        dsc_col = df.get("dim_store_category")
        masks = []
        for idx in df.index:
            st = st_col.loc[idx] if st_col is not None else None
            sc = sc_col.loc[idx] if sc_col is not None else None
            dsc = dsc_col.loc[idx] if dsc_col is not None else None
            masks.append(classify_store_type(st, sc, dsc) == store_type)
        df = df[masks]

    # 2. 代理商类型筛选
    if dealer_type and dealer_type != "all":
        dealer_map = build_dealer_type_map(dim_dealer)
        dealer_col = df.get("dealer_final", df.get("dealer"))
        df = df[dealer_col.map(lambda d: dealer_map.get(d, "综合") == dealer_type)]

    # 3. 时间段筛选
    start, end = resolve_date_range(period, date_from, date_to, period_value)
    if start is not None or end is not None:
        dates = pd.to_datetime(df["activity_date"], errors="coerce")
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= dates >= start
        if end is not None:
            mask &= dates <= end
        df = df[mask]

    return df


def get_filter_options(dim_dealer: pd.DataFrame, merged: pd.DataFrame) -> dict:
    """返回可用筛选选项(前端下拉菜单用)。"""
    dealer_map = build_dealer_type_map(dim_dealer)
    dealer_types = sorted(set(dealer_map.values()))
    store_types = set()
    for _, row in merged.iterrows():
        st = classify_store_type(
            row.get("store_type"), row.get("store_category_final"),
            row.get("dim_store_category"),
        )
        store_types.add(st)
    dates = pd.to_datetime(merged["activity_date"], errors="coerce").dropna()
    return {
        "store_types": sorted(store_types),
        "dealer_types": dealer_types,
        "date_min": dates.min().strftime("%Y-%m-%d") if len(dates) else None,
        "date_max": dates.max().strftime("%Y-%m-%d") if len(dates) else None,
    }
