"""数据模型辅助函数：时间维度、业务标签、产品识别、门店匹配、质量检测。"""

from __future__ import annotations

import re
from datetime import date
import pandas as pd
import numpy as np

from config import COMPLETED_STATUSES

# ── 可配置阈值 ────────────────────────────────────────────

NEW_STORE_THRESHOLD_MONTHS = 3  # 开业 N 个月内视为新店


# ── 时间维度 ──────────────────────────────────────────────

def add_time_dimensions(df: pd.DataFrame, date_col: str = "activity_date") -> pd.DataFrame:
    """自动生成：年份、季度、月份、自然周、星期、年月、季度名称。"""
    dates = pd.to_datetime(df[date_col], errors="coerce")
    df["year"] = dates.dt.year.astype("Int64")
    df["quarter"] = dates.dt.quarter.astype("Int64")
    df["month"] = dates.dt.month.astype("Int64")
    df["week"] = dates.dt.isocalendar().week.astype("Int64")
    df["weekday"] = dates.dt.dayofweek + 1  # 1=周一 … 7=周日
    df["year_month"] = dates.dt.strftime("%Y-%m")
    iso = dates.dt.isocalendar()
    df["year_week"] = iso.year.astype("Int64").astype(str) + "W" + iso.week.astype("Int64").astype(str)
    df["quarter_name"] = dates.dt.year.astype("Int64").astype(str) + "Q" + dates.dt.quarter.astype("Int64").astype(str)
    return df


# ── 业务标签 ──────────────────────────────────────────────

def add_business_flags(df: pd.DataFrame) -> pd.DataFrame:
    """生成通用业务布尔字段，不写死任何产品名。"""
    sales = pd.to_numeric(df.get("sales_clean", pd.Series(dtype=float)), errors="coerce").fillna(0)
    wechat = pd.to_numeric(df.get("wechat_adds", pd.Series(dtype=float)), errors="coerce").fillna(0)
    part = pd.to_numeric(df.get("participants", pd.Series(dtype=float)), errors="coerce").fillna(0)
    atype = df.get("activity_type", pd.Series(dtype=str)).fillna("")
    status = df.get("activity_status", pd.Series(dtype=str)).fillna("")
    source = df.get("activity_source", pd.Series(dtype=str)).fillna("")
    weekday = df.get("weekday", pd.Series(dtype="Int64"))

    df["is_valid_activity"] = status.isin(COMPLETED_STATUSES) & ((sales > 0) | (wechat > 0) | (part > 0))
    df["is_recap_completed"] = status == "已完成"
    df["is_drone_activity"] = atype == "无人机专项"
    df["is_crossbrand_activity"] = atype.str.contains("异业", na=False)
    df["is_new_product_activity"] = atype.str.contains("新品|品鉴", na=False)
    df["is_store_activity"] = source == "门店自发组织"
    df["is_hq_activity"] = source.isin(["品牌要求", "市场/用户运营"])
    df["is_dealer_activity"] = source == "代理侧资源"
    df["is_holiday_activity"] = weekday.isin([6, 7])
    return df


# ── 产品识别（自动、不写死）──────────────────────────────

def detect_product_columns(df: pd.DataFrame) -> dict[str, str]:
    """自动扫描以"销量"结尾的列，提取产品线名称。

    新增产品列（如 Pocket系列销量）无需改代码，自动识别。
    """
    result: dict[str, str] = {}
    for col in df.columns:
        if isinstance(col, str) and col.endswith("销量"):
            result[col] = col.replace("销量", "")
    return result


def add_product_fields(df: pd.DataFrame, product_cols: dict[str, str] | None = None) -> pd.DataFrame:
    """生成通用产品字段：product_lines（列表）、has_product_sales、product_count。

    product_cols: {列名: 产品线名} 映射。不传则自动检测（以"销量"结尾的列）。
    新增产品列无需改代码，自动识别。
    """
    if product_cols is None:
        product_cols = detect_product_columns(df)

    def _collect(row):
        active = []
        for col, name in product_cols.items():
            v = row.get(col)
            if v is not None and pd.notna(v) and float(v) > 0:
                active.append(name)
        return active

    df["product_lines"] = df.apply(_collect, axis=1)
    df["has_product_sales"] = df["product_lines"].apply(len) > 0
    df["product_count"] = df["product_lines"].apply(len)
    return df


# ── 门店匹配 ──────────────────────────────────────────────

_STOPWORDS = sorted(
    {"授权体验店", "授权店", "直营旗舰店", "直营店", "专卖店",
     "照材专卖店", "照材专区", "体验店"},
    key=len, reverse=True,
)


def normalize_store_name(name) -> str:
    """标准化门店名称：去括号、去常见后缀、去空格。"""
    if not name or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name)
    s = re.sub(r"[\(（].*?[\)）]", "", s)
    for suf in _STOPWORDS:
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = re.sub(r"[\s\u3000]+", "", s)
    return s


def match_store_name(activity_name, name_index: dict, store_names: set) -> str | None:
    """匹配活动门店名到门店维度表。策略：精确 → 标准化 → 子串。"""
    if not activity_name or (isinstance(activity_name, float) and pd.isna(activity_name)):
        return None
    an = str(activity_name)
    if an in store_names:
        return an
    norm = normalize_store_name(an)
    if norm in name_index:
        return name_index[norm]
    for sn in store_names:
        nsn = normalize_store_name(sn)
        if len(nsn) < 4:
            continue
        if nsn in norm or norm in nsn:
            return sn
    return None


def build_store_name_index(store_names) -> dict:
    """{标准化名称: 原始名称} 索引。"""
    return {normalize_store_name(n): n for n in store_names if n}


# ── 门店生命周期 ──────────────────────────────────────────

def compute_months_between(start, end) -> int:
    """计算两个日期之间的月份数。"""
    if pd.isna(start) or pd.isna(end):
        return None
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    return (end.year - start.year) * 12 + (end.month - start.month)


# ── 数据质量检测 ──────────────────────────────────────────

def compute_quality_report(models: dict) -> dict:
    """计算数据质量指标，供 DATA_MODEL.md 使用。"""
    merged = models["merged_activity_store"]
    fact = models["fact_activity"]
    dim_store = models["dim_store"]

    total = len(merged)
    matched = int(merged["has_store_dim"].sum())
    unmatched_stores = merged.loc[~merged["has_store_dim"], "store_name"].dropna().unique().tolist()

    # 空值统计
    null_stats = {}
    for col in ["activity_date", "activity_type", "store_name", "dealer",
                "sales_clean", "wechat_adds", "participants", "activity_status"]:
        if col in merged.columns:
            null_stats[col] = int(merged[col].isna().sum())

    # 重复 activity_id
    dup_count = int(merged["activity_id"].duplicated().sum())

    # 日期异常
    dates = pd.to_datetime(merged["activity_date"], errors="coerce")
    date_invalid = int(dates.isna().sum())
    date_future = int((dates > pd.Timestamp.now() + pd.Timedelta(days=30)).sum())
    date_past = int((dates < pd.Timestamp("2024-01-01")).sum())

    # 从 product_lines 字段提取实际出现过的产品线
    all_lines: set[str] = set()
    for lines in merged.get("product_lines", pd.Series(dtype=object)):
        if isinstance(lines, list):
            all_lines.update(lines)

    result = {
        "total_activities": total,
        "total_stores": len(dim_store),
        "match_count": matched,
        "match_rate": round(matched / total, 4) if total else 0,
        "unmatched_store_names": unmatched_stores,
        "null_stats": null_stats,
        "duplicate_activity_ids": dup_count,
        "date_invalid": date_invalid,
        "date_future_anomaly": date_future,
        "date_past_anomaly": date_past,
        "product_lines_detected": sorted(all_lines),
        "valid_activity_count": int(merged.get("is_valid_activity", pd.Series()).sum()),
        "recap_completed_count": int(merged.get("is_recap_completed", pd.Series()).sum()),
    }
    return result
