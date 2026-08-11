"""统一业务数据模型（Phase 2）。

构建四张表，所有后续经营分析基于 merged_activity_store：
  - fact_activity         活动事实表（含时间维度、业务标签、产品识别）
  - dim_store             门店维度表（含生命周期字段）
  - dim_dealer            代理商维度表
  - merged_activity_store 经营分析统一数据集（活动 LEFT JOIN 门店）

通用性：不写死任何产品名称或上市时间，新增产品列自动识别。
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd
import numpy as np

from data_loader import load_activity, load_stores
from config import (
    ACTIVITY_COLUMNS, STORE_COLUMNS, NUMERIC_FIELDS, DATE_FIELDS,
    ACTIVITY_TYPE_CATEGORIES, COMPLETED_STATUSES,
)
from .model_utils import (
    add_time_dimensions,
    add_business_flags,
    add_product_fields,
    normalize_store_name,
    build_store_name_index,
    match_store_name,
    compute_months_between,
    compute_quality_report,
    NEW_STORE_THRESHOLD_MONTHS,
)

# dim_store 门店维度补充字段（从门店表取，匹配后注入活动表）
_STORE_ENRICH_COLS = [
    "dealer", "province_unit", "region", "province", "city",
    "city_tier", "business_status", "store_status",
    "open_date", "close_date", "store_level", "shop_type",
    "mall_level", "area_sqm", "can_fly_indoor", "insta_manager",
    "ops_manager", "dealer_ops_rep", "feishu_group", "mall_name",
    "store_address", "store_manager", "manager_phone",
    "dealer_distribution", "store_category",
]


# ── 事实表 ────────────────────────────────────────────────

def build_fact_activity(activities: pd.DataFrame) -> pd.DataFrame:
    """活动事实表：重命名、清洗、添加时间维度+业务标签+产品字段。"""
    # 产品识别：从 config 映射 + DataFrame 列自动检测（不写死产品名）
    # 1) config 中以"销量"结尾的映射 -> {英文列: 产品线名}
    renamed_product_cols: dict[str, str] = {}
    for cn_name, en_name in ACTIVITY_COLUMNS.items():
        if cn_name.endswith("销量"):
            renamed_product_cols[en_name] = cn_name.replace("销量", "")
    # 2) DataFrame 中未被映射、仍以"销量"结尾的列（未来新增产品）
    for col in activities.columns:
        if isinstance(col, str) and col.endswith("销量") and col not in ACTIVITY_COLUMNS:
            renamed_product_cols[col] = col.replace("销量", "")

    df = activities.rename(columns=ACTIVITY_COLUMNS).copy()
    df = df[df["record_id"].notna() & (df["record_id"] != "")].copy()

    # 数值清洗
    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # 日期清洗
    for col in DATE_FIELDS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    # 字符串清洗
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    df = df.rename(columns={"record_id": "activity_id", "状态": "activity_status"})
    df = add_time_dimensions(df)
    df = add_business_flags(df)
    df = add_product_fields(df, renamed_product_cols)
    df.attrs["product_lines_detected"] = list(renamed_product_cols.values())
    return df.reset_index(drop=True)


# ── 门店维度表 ────────────────────────────────────────────

def build_dim_store(stores: pd.DataFrame) -> pd.DataFrame:
    """门店维度表：含 store_id、开业月份、是否新店等生命周期字段。"""
    df = stores.rename(columns=STORE_COLUMNS).copy()
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    df["area_sqm"] = pd.to_numeric(df.get("area_sqm"), errors="coerce")
    df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")
    df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce")
    df["business_status"] = df["business_status"].replace({"xxx": "未知"}).fillna("未知")

    # 生成 store_id
    df["store_id"] = "ST" + pd.Series(df.index, dtype=str).str.zfill(4)

    # 生命周期字段
    today = pd.Timestamp(date.today())
    df["open_month"] = df["open_date"].dt.month.astype("Int64")
    df["months_since_open"] = df["open_date"].apply(
        lambda d: compute_months_between(d, today)
    )
    df["is_new_store"] = df["months_since_open"].apply(
        lambda m: m is not None and m >= 0 and m < NEW_STORE_THRESHOLD_MONTHS
    )

    df = df[df["store_name"].notna()].reset_index(drop=True)
    return df


# ── 代理商维度表 ──────────────────────────────────────────

def build_dim_dealer(stores: pd.DataFrame) -> pd.DataFrame:
    """代理商维度表：从门店表聚合。"""
    s = stores.rename(columns=STORE_COLUMNS).copy()
    s = s[s["dealer"].notna()]
    grouped = s.groupby("dealer").agg(
        store_count=("store_name", "count"),
        mall_count=("store_category", lambda x: (x == "Mall店").sum()),
        camera_count=("store_category", lambda x: (x == "照材店").sum()),
        active_count=("store_status", lambda x: (x == "已开业").sum()),
        province_units=("province_unit", lambda x: "/".join(sorted(set(x.dropna())))),
        regions=("region", lambda x: "/".join(sorted(set(x.dropna())))),
        cities=("city", lambda x: x.nunique()),
        total_area=("area_sqm", "sum"),
    ).reset_index()
    grouped["dealer_id"] = "DR" + pd.Series(grouped.index, dtype=str).str.zfill(3)
    return grouped


# ── 统一数据集 ────────────────────────────────────────────

def build_merged_activity_store(
    fact_activity: pd.DataFrame, dim_store: pd.DataFrame
) -> pd.DataFrame:
    """活动 LEFT JOIN 门店维度，自动补充代理商/省区/店长/开业时间等。

    匹配策略：门店名称精确 → 标准化 → 子串模糊。
    """
    store_names = set(dim_store["store_name"].dropna().astype(str))
    name_index = build_store_name_index(store_names)

    # 门店维度查找表
    dim_clean = dim_store[dim_store["store_name"].notna()].drop_duplicates(
        subset="store_name", keep="first"
    )
    store_lookup = dim_clean.set_index("store_name").to_dict("index")

    # 匹配
    matched_names = {}
    unmatched = []
    for name in fact_activity["store_name"].dropna().unique():
        m = match_store_name(name, name_index, store_names)
        if m:
            matched_names[name] = m
        else:
            unmatched.append(name)

    merged = fact_activity.copy()
    merged["matched_store_name"] = merged["store_name"].map(matched_names)
    merged["has_store_dim"] = merged["matched_store_name"].notna()
    merged["store_id"] = merged["matched_store_name"].map(
        lambda sn: store_lookup.get(sn, {}).get("store_id") if sn else None
    )

    # 注入门店维度字段（dim_ 前缀）
    for col in _STORE_ENRICH_COLS:
        merged[f"dim_{col}"] = merged["matched_store_name"].map(
            lambda sn: store_lookup.get(sn, {}).get(col) if sn else None
        )

    # 合并优先级：门店维度值优先，活动表值回退
    merged["dealer_final"] = merged["dim_dealer"].fillna(merged["dealer"])
    merged["province_unit_final"] = merged["dim_province_unit"]
    merged["region_final"] = merged["dim_region"]
    merged["province_final"] = merged["dim_province"]
    merged["city_final"] = merged["dim_city"]
    merged["city_tier_final"] = merged["dim_city_tier"]
    merged["store_manager_final"] = merged["dim_store_manager"]
    merged["open_date_final"] = merged["dim_open_date"]
    merged["store_type_final"] = merged["dim_shop_type"]
    merged["store_category_final"] = merged.get("store_category")

    # 门店生命周期（注入到活动行）
    merged["store_open_month"] = merged["dim_open_date"].dt.month.astype("Int64")
    merged["store_months_since_open"] = merged.apply(
        lambda r: compute_months_between(r["dim_open_date"], r["activity_date"]),
        axis=1,
    )
    merged["is_new_store_activity"] = merged["store_months_since_open"].apply(
        lambda m: m is not None and m >= 0 and m < NEW_STORE_THRESHOLD_MONTHS
    )

    return merged


# ── 全量构建 ──────────────────────────────────────────────

def build_all_models() -> dict:
    """构建全部数据模型，返回 dict。"""
    print("=" * 60)
    print("统一业务数据模型构建 (Phase 2)")
    print("=" * 60)

    activities = load_activity()
    stores = load_stores()
    print(f"输入: 活动 {len(activities)} 条, 门店 {len(stores)} 条")

    print("构建 fact_activity...")
    fact = build_fact_activity(activities)
    product_lines = fact.attrs.get("product_lines_detected", [])
    print(f"  事实表: {len(fact)} 条, {fact.shape[1]} 列")
    print(f"  自动识别产品线: {product_lines}")

    print("构建 dim_store...")
    dim_store = build_dim_store(stores)
    print(f"  门店维度: {len(dim_store)} 条")

    print("构建 dim_dealer...")
    dim_dealer = build_dim_dealer(stores)
    print(f"  代理商维度: {len(dim_dealer)} 条")

    print("构建 merged_activity_store...")
    merged = build_merged_activity_store(fact, dim_store)
    match_rate = merged["has_store_dim"].mean()
    print(f"  统一数据集: {len(merged)} 条, {merged.shape[1]} 列")
    print(f"  门店匹配率: {match_rate:.1%}")

    quality = compute_quality_report({
        "fact_activity": fact, "dim_store": dim_store, "merged_activity_store": merged,
    })

    print("=" * 60)
    print("构建完成")
    print("=" * 60)

    return {
        "fact_activity": fact,
        "dim_store": dim_store,
        "dim_dealer": dim_dealer,
        "merged_activity_store": merged,
        "quality": quality,
    }


if __name__ == "__main__":
    models = build_all_models()
    merged = models["merged_activity_store"]
    print(f"\nmerged_activity_store: {merged.shape}")
    print(f"列名: {list(merged.columns)}")
    print(f"\n数据质量: {models['quality']}")
