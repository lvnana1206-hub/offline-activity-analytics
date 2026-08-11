from __future__ import annotations

"""数据模型构建模块。

产出四张维度/事实表，以及核心宽表 merged_activity_store。

维度表：
  - dim_store      门店维度
  - dim_dealer     代理商维度
  - dim_employee   员工维度
事实表：
  - fact_activity  活动事实
核心宽表：
  - merged_activity_store  活动×门店关联宽表（所有分析的基础）
"""

import re
import pandas as pd
import numpy as np

from .data_loader import load_activity, load_stores


# ── 门店名称标准化 ──────────────────────────────────────────

_STOPWORDS = {"授权体验店", "授权店", "直营旗舰店", "直营店", "专卖店", "照材专卖店", "照材专区", "体验店"}

def _normalize_store_name(name: str) -> str:
    """标准化门店名称用于匹配：去括号、去常见后缀、去空格。"""
    if not name or name is None:
        return ""
    s = str(name)
    # 去括号内容
    s = re.sub(r"[\(（].*?[\)）]", "", s)
    # 去常见后缀词（从长到短）
    for suffix in sorted(_STOPWORDS, key=len, reverse=True):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    # 去空格和特殊字符
    s = re.sub(r"[\s\u3000]+", "", s)
    return s


def _build_store_name_index(stores: pd.DataFrame) -> dict:
    """构建 {标准化名称: 原始名称} 索引，并附加模糊前缀匹配。"""
    index = {}
    for name in stores["store_name"].dropna().unique():
        index[_normalize_store_name(name)] = name
    return index


def _match_store_name(activity_name: str, name_index: dict, store_names: set) -> str | None:
    """尝试匹配活动表中的门店名到门店维度表。
    策略：精确 -> 标准化精确 -> 前缀包含。
    """
    if not activity_name:
        return None
    # 1. 精确匹配
    if activity_name in store_names:
        return activity_name
    # 2. 标准化后精确匹配
    norm = _normalize_store_name(activity_name)
    if norm in name_index:
        return name_index[norm]
    # 3. 前缀包含：活动名是维度名的子串，或反过来
    for sn in store_names:
        norm_sn = _normalize_store_name(sn)
        if not norm_sn or len(norm_sn) < 4:
            continue
        if norm_sn in norm or norm in norm_sn:
            return sn
    return None


# ── 维度表构建 ──────────────────────────────────────────────

def build_dim_store(stores: pd.DataFrame) -> pd.DataFrame:
    """门店维度表：选取门店相关字段，去重。"""
    cols = [
        "store_name", "dealer", "dealer_distribution", "store_category",
        "province_unit", "region", "province", "city", "city_tier",
        "business_status", "store_status", "open_date", "close_date",
        "store_level", "shop_type", "mall_level", "area_sqm",
        "can_fly_indoor", "insta_manager", "ops_manager", "dealer_ops_rep",
        "feishu_group", "mall_name", "store_address", "store_manager", "manager_phone",
    ]
    dim = stores[[c for c in cols if c in stores.columns]].copy()
    for c in cols:
        if c not in dim.columns:
            dim[c] = None
    dim["store_key"] = dim.index.astype(str)
    return dim


def build_dim_dealer(stores: pd.DataFrame) -> pd.DataFrame:
    """代理商维度表：从门店表聚合。"""
    grouped = stores.groupby("dealer").agg(
        store_count=("store_name", "count"),
        mall_count=("store_category", lambda x: (x == "Mall店").sum()),
        camera_count=("store_category", lambda x: (x == "照材店").sum()),
        active_count=("store_status", lambda x: (x == "已开业").sum()),
        opening_count=("store_status", lambda x: (x == "开业中").sum()),
        province_units=("province_unit", lambda x: "/".join(sorted(set(x.dropna())))),
        provinces=("province", lambda x: "/".join(sorted(set(x.dropna())))),
        cities=("city", lambda x: x.nunique()),
        regions=("region", lambda x: "/".join(sorted(set(x.dropna())))),
    ).reset_index()
    return grouped


def build_dim_employee(stores: pd.DataFrame) -> pd.DataFrame:
    """员工维度表：YourCompany客户负责人。"""
    emp = stores[stores["insta_manager"].notna()].groupby("insta_manager").agg(
        managed_stores=("store_name", "count"),
        province_units=("province_unit", lambda x: "/".join(sorted(set(x.dropna())))),
        regions=("region", lambda x: "/".join(sorted(set(x.dropna())))),
        dealers=("dealer", lambda x: "/".join(sorted(set(x.dropna())))),
    ).reset_index()
    return emp


# ── 核心宽表 ────────────────────────────────────────────────

def build_merged_activity_store(
    activities: pd.DataFrame, stores: pd.DataFrame
) -> pd.DataFrame:
    """构建 merged_activity_store：活动 LEFT JOIN 门店维度。

    匹配策略：
      1. 门店名称精确匹配
      2. 标准化名称匹配
      3. 前缀/子串模糊匹配
    匹配失败的记录保留活动数据，门店维度字段为空。
    """
    name_index = _build_store_name_index(stores)
    store_names = set(stores["store_name"].dropna().unique())

    # 构建门店维度查找字典
    dim_store = build_dim_store(stores)
    # 过滤空门店名，避免重复索引
    dim_store_clean = dim_store[dim_store["store_name"].notna()].drop_duplicates(subset="store_name", keep="first")
    store_lookup = dim_store_clean.set_index("store_name").to_dict("index")

    # 匹配活动表门店名 -> 门店维度门店名
    matched_names = {}
    unmatched = []
    for name in activities["store_name"].dropna().unique():
        match = _match_store_name(name, name_index, store_names)
        if match:
            matched_names[name] = match
        else:
            unmatched.append(name)

    print(f"  门店匹配: {len(matched_names)} 匹配成功, {len(unmatched)} 未匹配")
    if unmatched:
        print(f"  未匹配门店: {unmatched[:15]}")

    # 将匹配结果映射回活动表
    activities = activities.copy()
    activities["matched_store_name"] = activities["store_name"].map(matched_names)

    # 从门店维度补充字段
    store_enrich_cols = [
        "dealer", "province", "province_unit", "region", "city_tier", "business_status",
    "store_status", "open_date", "close_date", "store_level", "shop_type",
    "mall_level", "area_sqm", "can_fly_indoor", "insta_manager",
    "ops_manager", "dealer_ops_rep", "mall_name", "store_address",
    "store_manager", "manager_phone", "dealer_distribution", "store_category",
]

    for col in store_enrich_cols:
        if col in dim_store_clean.columns:
            activities[f"dim_{col}"] = activities["matched_store_name"].map(
                lambda sn: store_lookup.get(sn, {}).get(col) if sn else None
            )
        else:
            activities[f"dim_{col}"] = None

    # 合并优先级：门店维度值优先，活动表值回退
    activities["dealer_final"] = activities["dim_dealer"].fillna(activities["dealer"])
    activities["province_unit_final"] = activities["dim_province_unit"]
    activities["region_final"] = activities["dim_region"]
    activities["city_tier_final"] = activities["dim_city_tier"]
    activities["store_level_final"] = activities["dim_store_level"]
    # 门店类别：维度优先，活动表回退
    activities["store_category_final"] = activities["store_category"] if "store_category" in activities.columns else None

    # 省份：维度优先，活动表回退
    activities["province"] = activities.get("dim_province")
    activities["province_unit"] = activities.get("dim_province_unit")

    # 标记是否成功关联门店
    activities["has_store_dim"] = activities["matched_store_name"].notna()

    return activities


def build_all_models(activities: pd.DataFrame | None = None) -> dict:
    """构建全部数据模型，返回字典。

    Args:
        activities: 外部传入的活动 DataFrame；None 则从 Excel 加载。
    """
    print("=" * 60)
    print("开始构建数据模型")
    print("=" * 60)

    if activities is None:
        activities = load_activity()
    stores = load_stores()
    print(f"活动事实表: {len(activities)} 条记录, {activities.shape[1]} 列")
    print(f"门店维度表: {len(stores)} 条记录, {stores.shape[1]} 列")

    print("\n构建代理商维度表...")
    dim_dealer = build_dim_dealer(stores)
    print(f"  代理商维度: {len(dim_dealer)} 条")

    print("\n构建员工维度表...")
    dim_employee = build_dim_employee(stores)
    print(f"  员工维度: {len(dim_employee)} 条")

    print("\n构建门店维度表...")
    dim_store = build_dim_store(stores)
    print(f"  门店维度: {len(dim_store)} 条")

    print("\n构建核心宽表 merged_activity_store...")
    merged = build_merged_activity_store(activities, stores)
    match_rate = merged["has_store_dim"].mean()
    print(f"  merged_activity_store: {len(merged)} 条, 门店匹配率 {match_rate:.1%}")

    return {
        "fact_activity": activities,
        "dim_store": dim_store,
        "dim_dealer": dim_dealer,
        "dim_employee": dim_employee,
        "merged_activity_store": merged,
        "raw_stores": stores,
    }


if __name__ == "__main__":
    models = build_all_models()
    merged = models["merged_activity_store"]
    print(f"\nmerged_activity_store 列数: {merged.shape[1]}")
    print(f"列名: {list(merged.columns)}")
