"""评分体系 (Scoring System)。

四维评分：
  - Store Score   门店评分
  - Dealer Score  代理商评分
  - Activity Score 活动评分
  - Region Score   区域评分

评分维度（权重来自 rules_engine）：
  - activity_volume (20%)    活动量
  - completion_quality (25%) 完成质量
  - sales_performance (35%)  销售表现
  - engagement (20%)         互动参与

所有评分 0-100，映射 A/B/C/D 等级。
"""

from __future__ import annotations

import pandas as pd
from .config import COMPLETED_STATUSES
import numpy as np

from .rules_engine import get_engine
from .analysis.common import compute_health_score, compute_health_score_by_group


def _safe(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _normalize(series: pd.Series, max_val: float = None) -> pd.Series:
    """归一化到 0-100。使用百分位排名，分布更均匀。"""
    if max_val is not None:
        return (series / max_val * 100).clip(0, 100)
    if series.max() == 0:
        return pd.Series(0, index=series.index)
    # 百分位排名：0值给0分，非零值按排名分布到 30-100
    nonzero = series[series > 0]
    if len(nonzero) == 0:
        return pd.Series(0, index=series.index)
    rank = series.rank(pct=True) * 100
    # 0值的排名也参与，但分数从30起步而非0，避免极低值拉低整体
    rank = rank.where(series > 0, 0)
    return rank.round(1)


# ── 活动评分 ────────────────────────────────────────────────

def score_activities(merged: pd.DataFrame) -> pd.DataFrame:
    """对每条活动打分。"""
    engine = get_engine()
    df = merged.copy()
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    df["wechat"] = _safe(df["wechat_adds"])

    # 活动评分基于 4 个子维度
    # 1. 销售表现 (35%): 销售额归一化
    sales_score = _normalize(df["sales"])
    # 2. 互动参与 (25%): 参与人数 + 企微
    engage_raw = df["participants"] + df["wechat"] * 2
    engage_score = _normalize(engage_raw)
    # 3. 完成质量 (25%): 已完成=100, 执行中=60, 待评估=30, 终止=0
    status_map = {"已完成": 100, "待评估": 100, "交付执行中": 70, "复盘收集中": 80, "终止": 0}
    quality_score = df["activity_status"].map(status_map).fillna(30).astype(float)
    # 4. 活动量维度对单条活动不适用，用活动类型的平均表现替代 (20%)
    type_avg = df.groupby("activity_type")["sales"].transform("mean")
    type_score = _normalize(type_avg)

    w = engine.get_scoring_weights()
    df["activity_score"] = (
        sales_score * w["sales_performance"] +
        engage_score * w["engagement"] +
        quality_score * w["completion_quality"] +
        type_score * w["activity_volume"]
    ).round(1)

    df["activity_grade"] = df["activity_score"].apply(engine.get_grade)
    # 活动分类（来自 rules_engine）
    df_classified = engine.classify_activities_batch(df)
    if "activity_class" in df_classified.columns:
        df["activity_class"] = df_classified["activity_class"].values
    return df


# ── 门店评分 ────────────────────────────────────────────────

def score_stores(merged: pd.DataFrame, dim_store: pd.DataFrame) -> pd.DataFrame:
    """门店评分。"""
    engine = get_engine()
    df = merged.copy()
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    df["wechat"] = _safe(df["wechat_adds"])
    df["hosts"] = _safe(df["converted_hosts"])

    result = df.groupby("store_name").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()

    # 4 维度评分
    if len(result) == 0:
        return result
    # 1. 活动量 (20%)
    vol_score = _normalize(result["activity_count"])
    # 2. 完成质量 (25%)
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    qual_score = result["completion_rate"] * 100
    # 3. 销售表现 (35%)
    sales_score = _normalize(result["total_sales"])
    # 4. 互动参与 (20%)
    engage_raw = result["total_participants"] + result["total_wechat"] * 2
    engage_score = _normalize(engage_raw)
    # 健康度: 有效活动(蓄水率>5%或转化主机) / 总活动 * 100
    result = result.merge(
        compute_health_score_by_group(df, "store_name"), on="store_name", how="left"
    )
    result["health_score"] = result["health_score"].fillna(0)

    w = engine.get_scoring_weights()
    result["store_score"] = (
        vol_score * w["activity_volume"] +
        qual_score * w["completion_quality"] +
        sales_score * w["sales_performance"] +
        engage_score * w["engagement"]
    ).round(1)
    result["store_grade"] = result["store_score"].apply(engine.get_grade)

    # 关联门店维度
    store_info = dim_store[["store_name", "province_unit", "region", "city",
                            "store_level", "store_category", "business_status"]].copy()
    store_info = store_info.drop_duplicates(subset="store_name", keep="first")
    result = result.merge(store_info, on="store_name", how="left")
    return result.sort_values("store_score", ascending=False)


# ── 代理商评分 ──────────────────────────────────────────────

def score_dealers(merged: pd.DataFrame, dim_dealer: pd.DataFrame) -> pd.DataFrame:
    """代理商评分。"""
    engine = get_engine()
    df = merged.copy()
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    df["wechat"] = _safe(df["wechat_adds"])
    df["hosts"] = _safe(df["converted_hosts"])
    df["dealer"] = df.get("dealer_final", df["dealer"])

    result = df.groupby("dealer").agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        active_stores=("store_name", "nunique"),
        activity_types=("activity_type", "nunique"),
    ).reset_index()
    result["completion_rate"] = result["completed_count"] / result["activity_count"]

    result = result.merge(dim_dealer[["dealer", "store_count"]], on="dealer", how="left")
    result["coverage_rate"] = result["active_stores"] / result["store_count"]

    # 4 维度评分
    if len(result) == 0:
        return result
    vol_score = _normalize(result["activity_count"])
    qual_score = result["completion_rate"] * 100
    sales_score = _normalize(result["total_sales"])
    engage_score = _normalize(result["total_participants"])
    # 健康度: 有效活动(蓄水率>5%或转化主机) / 总活动 * 100
    result = result.merge(
        compute_health_score_by_group(df, "dealer"), on="dealer", how="left"
    )
    result["health_score"] = result["health_score"].fillna(0)

    w = engine.get_scoring_weights()
    result["dealer_score"] = (
        vol_score * w["activity_volume"] +
        qual_score * w["completion_quality"] +
        sales_score * w["sales_performance"] +
        engage_score * w["engagement"]
    ).round(1)
    result["dealer_grade"] = result["dealer_score"].apply(engine.get_grade)
    return result.sort_values("dealer_score", ascending=False)


# ── 区域评分 ────────────────────────────────────────────────

def score_regions(merged: pd.DataFrame) -> pd.DataFrame:
    """区域评分。"""
    engine = get_engine()
    df = merged.copy()
    df["sales"] = _safe(df["sales_clean"])
    df["participants"] = _safe(df["participants"])
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"

    result = df.groupby(region_col).agg(
        activity_count=("record_id", "count"),
        completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        active_stores=("store_name", "nunique"),
        dealers=("dealer", "nunique"),
        activity_types=("activity_type", "nunique"),
    ).reset_index().rename(columns={region_col: "region"})
    result["completion_rate"] = result["completed_count"] / result["activity_count"]
    result = result[result["region"].notna()]

    # 4 维度评分
    if len(result) == 0:
        return result
    vol_score = _normalize(result["activity_count"])
    qual_score = result["completion_rate"] * 100
    sales_score = _normalize(result["total_sales"])
    engage_score = _normalize(result["total_participants"])

    w = engine.get_scoring_weights()
    result["region_score"] = (
        vol_score * w["activity_volume"] +
        qual_score * w["completion_quality"] +
        sales_score * w["sales_performance"] +
        engage_score * w["engagement"]
    ).round(1)
    result["region_grade"] = result["region_score"].apply(engine.get_grade)
    return result.sort_values("region_score", ascending=False)


# ── 汇总 ────────────────────────────────────────────────────

def compute_all_scores(merged: pd.DataFrame, dim_store: pd.DataFrame,
                       dim_dealer: pd.DataFrame) -> dict:
    """计算全部评分。"""
    print("计算四维评分体系...")
    scores = {
        "activity_scores": score_activities(merged),
        "store_scores": score_stores(merged, dim_store),
        "dealer_scores": score_dealers(merged, dim_dealer),
        "region_scores": score_regions(merged),
    }
    for k, v in scores.items():
        if isinstance(v, pd.DataFrame):
            print(f"  {k}: {len(v)} 条")
            if "activity_score" in v.columns:
                print(f"    分数分布: {v['activity_score'].describe().to_dict()}")
            elif "store_score" in v.columns:
                grades = v["store_grade"].value_counts().to_dict()
                print(f"    等级分布: {grades}")
            elif "dealer_score" in v.columns:
                grades = v["dealer_grade"].value_counts().to_dict()
                print(f"    等级分布: {grades}")
            elif "region_score" in v.columns:
                grades = v["region_grade"].value_counts().to_dict()
                print(f"    等级分布: {grades}")
    return scores


if __name__ == "__main__":
    from .data_model import build_all_models
    models = build_all_models()
    scores = compute_all_scores(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )
    print("\n=== 门店评分 Top10 ===")
    print(scores["store_scores"][["store_name", "store_score", "store_grade",
          "activity_count", "total_sales"]].head(10).to_string(index=False))
    print("\n=== 代理商评分 Top10 ===")
    print(scores["dealer_scores"][["dealer", "dealer_score", "dealer_grade",
          "activity_count", "total_sales"]].head(10).to_string(index=False))
