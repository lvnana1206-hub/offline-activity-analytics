"""经营诊断模型。

不是展示图，而是自动分析当前存在哪些问题。
基于 merged_activity_store 和统一指标，输出结构化诊断报告。
"""

from __future__ import annotations

import pandas as pd
from .config import COMPLETED_STATUSES
import numpy as np
from datetime import datetime


def _safe_num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def diagnose_inactive_stores(merged: pd.DataFrame, dim_store: pd.DataFrame,
                             days: int = 30) -> list:
    """诊断：连续 N 天无活动的门店。"""
    results = []
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    latest_date = df["activity_date"].max()
    threshold = latest_date - pd.Timedelta(days=days)

    # 最近活动日期
    last_activity = df.groupby("store_name")["activity_date"].max().reset_index()
    last_activity.columns = ["store_name", "last_activity_date"]

    # 所有已开业门店
    active_stores = dim_store[
        (dim_store["store_name"].notna()) &
        (dim_store["store_status"] == "已开业")
    ][["store_name", "dealer", "province_unit", "region", "city", "store_level"]].copy()
    active_stores = active_stores.drop_duplicates(subset="store_name")

    # 从未有活动的门店
    never_active = active_stores[~active_stores["store_name"].isin(last_activity["store_name"])]
    for _, row in never_active.iterrows():
        results.append({
            "issue_type": "从未有活动",
            "severity": "high",
            "store_name": row["store_name"],
            "dealer": row.get("dealer"),
            "region": row.get("region"),
            "province_unit": row.get("province_unit"),
            "store_level": row.get("store_level"),
            "last_activity_date": None,
            "days_inactive": None,
            "description": f"门店 [{row['store_name']}] 自记录以来从未举办活动",
        })

    # 有活动但已超过 N 天的门店
    inactive = last_activity[last_activity["last_activity_date"] < threshold].copy()
    inactive = inactive.merge(active_stores, on="store_name", how="inner")
    for _, row in inactive.iterrows():
        days_inactive = (latest_date - row["last_activity_date"]).days
        results.append({
            "issue_type": f"连续{days}天以上无活动",
            "severity": "medium" if days_inactive < 60 else "high",
            "store_name": row["store_name"],
            "dealer": row.get("dealer"),
            "region": row.get("region"),
            "province_unit": row.get("province_unit"),
            "store_level": row.get("store_level"),
            "last_activity_date": str(row["last_activity_date"].date()),
            "days_inactive": days_inactive,
            "description": f"门店 [{row['store_name']}] 已 {days_inactive} 天无活动（上次: {row['last_activity_date'].date()}）",
        })

    return results


def diagnose_low_completion(merged: pd.DataFrame, threshold: float = 0.05) -> list:
    """诊断：活动完成率过低的门店。"""
    results = []
    df = merged.copy()
    store_stats = df.groupby("store_name").agg(
        total=("record_id", "count"),
        completed=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
    ).reset_index()
    store_stats["completion_rate"] = store_stats["completed"] / store_stats["total"]
    # 仅看活动数 >= 5 的门店
    store_stats = store_stats[store_stats["total"] >= 5]
    low = store_stats[store_stats["completion_rate"] < threshold]

    for _, row in low.iterrows():
        results.append({
            "issue_type": "活动完成率低",
            "severity": "medium",
            "store_name": row["store_name"],
            "total_activities": int(row["total"]),
            "completed": int(row["completed"]),
            "completion_rate": round(row["completion_rate"], 3),
            "description": f"门店 [{row['store_name']}] 共 {int(row['total'])} 场活动仅完成 {int(row['completed'])} 场（完成率 {row['completion_rate']:.1%}）",
        })
    return results


def diagnose_single_activity_type(merged: pd.DataFrame, min_activities: int = 5) -> list:
    """诊断：活动类型单一的门店。"""
    results = []
    df = merged.copy()
    store_types = df.groupby("store_name").agg(
        total=("record_id", "count"),
        type_count=("activity_type", "nunique"),
        top_type=("activity_type", lambda x: x.mode().iloc[0] if len(x.mode()) else None),
        top_type_ratio=("activity_type", lambda x: x.value_counts().iloc[0] / len(x) if len(x) else 0),
    ).reset_index()
    store_types = store_types[(store_types["total"] >= min_activities) &
                               (store_types["type_count"] == 1)]

    for _, row in store_types.iterrows():
        results.append({
            "issue_type": "活动类型单一",
            "severity": "low",
            "store_name": row["store_name"],
            "total_activities": int(row["total"]),
            "only_type": row["top_type"],
            "description": f"门店 [{row['store_name']}] {int(row['total'])} 场活动全部为 [{row['top_type']}]，缺乏活动多样性",
        })
    return results


def diagnose_low_sales_activities(merged: pd.DataFrame, threshold: float = 500) -> list:
    """诊断：销售表现差的活动（已完成但销售额低于阈值）。"""
    results = []
    df = merged.copy()
    df["sales"] = _safe_num(df["sales_clean"])
    completed = df[df["activity_status"].isin(COMPLETED_STATUSES)]
    low_sales = completed[completed["sales"] < threshold]

    results.append({
        "issue_type": "已完成活动销售低",
        "severity": "info",
        "count": len(low_sales),
        "total_completed": len(completed),
        "ratio": len(low_sales) / len(completed) if len(completed) else 0,
        "description": f"{len(low_sales)} 场已完成活动销售额低于 {threshold} 元（占已完成活动 {len(low_sales)/len(completed):.1%}）" if len(completed) else "无已完成活动",
    })
    return results


def diagnose_region_gaps(merged: pd.DataFrame, dim_dealer: pd.DataFrame) -> list:
    """诊断：区域覆盖不足（门店覆盖率或活动密度低的区域）。"""
    results = []
    df = merged.copy()
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"
    df["dealer"] = df.get("dealer_final", df["dealer"])

    region_stats = df.groupby(region_col).agg(
        activity_count=("record_id", "count"),
        active_stores=("store_name", "nunique"),
        total_sales=("sales_clean", lambda x: _safe_num(x).sum()),
    ).reset_index().rename(columns={region_col: "region"})

    # 区域门店总数（从代理商维度反推，仅用于参考）
    dealer_region = dim_dealer[["dealer", "province_units"]].copy()
    if "store_count" in dim_dealer.columns:
        dealer_region["store_count"] = dim_dealer["store_count"].values

    # 找活动量极低的区域（少于5场活动）
    for _, row in region_stats.iterrows():
        if row["activity_count"] < 5 and row["region"] and row["region"] != "nan":
            results.append({
                "issue_type": "区域活动覆盖不足",
                "severity": "medium",
                "region": row["region"],
                "activity_count": int(row["activity_count"]),
                "active_stores": int(row["active_stores"]),
                "description": f"区域 [{row['region']}] 仅 {int(row['activity_count'])} 场活动，覆盖 {int(row['active_stores'])} 家门店",
            })

    # 代理商执行率低
    dealer_stats = df.groupby("dealer").agg(
        activity_count=("record_id", "count"),
        active_stores=("store_name", "nunique"),
    ).reset_index()
    dealer_stats = dealer_stats.merge(
        dim_dealer[["dealer", "store_count"]], on="dealer", how="left"
    )
    dealer_stats["coverage_rate"] = dealer_stats["active_stores"] / dealer_stats["store_count"]
    low_coverage = dealer_stats[(dealer_stats["store_count"] >= 10) &
                                 (dealer_stats["coverage_rate"] < 0.3)]

    for _, row in low_coverage.iterrows():
        results.append({
            "issue_type": "代理商门店覆盖率低",
            "severity": "medium",
            "dealer": row["dealer"],
            "store_count": int(row["store_count"]) if pd.notna(row["store_count"]) else 0,
            "active_stores": int(row["active_stores"]),
            "coverage_rate": round(row["coverage_rate"], 3) if pd.notna(row["coverage_rate"]) else 0,
            "description": f"代理商 [{row['dealer']}] 有 {int(row['store_count'])} 家门店但仅 {int(row['active_stores'])} 家有活动（覆盖率 {row['coverage_rate']:.1%}）",
        })

    return results


def diagnose_activity_quality(merged: pd.DataFrame) -> list:
    """诊断：活动质量问题（异常销售额、零参与等）。"""
    results = []
    df = merged.copy()
    df["sales"] = _safe_num(df["sales_clean"])
    df["participants"] = _safe_num(df["participants"])

    # 销售额异常标记
    if "sales_anomaly" in df.columns:
        anomaly = df[df["sales_anomaly"] == True]
        if len(anomaly) > 0:
            results.append({
                "issue_type": "销售额异常标记",
                "severity": "medium",
                "count": len(anomaly),
                "description": f"{len(anomaly)} 场活动被标记为销售额异常，需人工复核",
            })

    # 零参与人数的活动
    zero_participant = df[(df["participants"] == 0) & (df["activity_status"].isin(COMPLETED_STATUSES))]
    if len(zero_participant) > 0:
        results.append({
            "issue_type": "零参与已完成活动",
            "severity": "high",
            "count": len(zero_participant),
            "description": f"{len(zero_participant)} 场已完成活动参与人数为 0，数据可能缺失或活动质量极差",
        })

    # 高费用低产出活动（费用 > 1000 但销售 = 0）
    df["cost"] = _safe_num(df["activity_cost"])
    high_cost_low_return = df[(df["cost"] > 1000) & (df["sales"] == 0) &
                               (df["activity_status"].isin(COMPLETED_STATUSES))]
    if len(high_cost_low_return) > 0:
        results.append({
            "issue_type": "高费用零产出活动",
            "severity": "high",
            "count": len(high_cost_low_return),
            "description": f"{len(high_cost_low_return)} 场已完成活动费用超 1000 元但销售额为 0",
        })

    return results


def diagnose_excellent_activities(merged: pd.DataFrame, top_pct: float = 0.05) -> list:
    """筛选优秀活动（销售额 Top 5%）。"""
    df = merged.copy()
    df["sales"] = _safe_num(df["sales_clean"])
    df["participants"] = _safe_num(df["participants"])
    df["wechat"] = _safe_num(df["wechat_adds"])
    completed = df[df["activity_status"].isin(COMPLETED_STATUSES)]
    if len(completed) == 0:
        return []

    threshold = completed["sales"].quantile(1 - top_pct)
    excellent = completed[completed["sales"] >= threshold].sort_values("sales", ascending=False)

    results = []
    for _, row in excellent.iterrows():
        results.append({
            "rank": len(results) + 1,
            "store_name": row["store_name"],
            "activity_type": row["activity_type"],
            "activity_desc": row["activity_desc"],
            "sales": float(row["sales"]),
            "participants": int(row["participants"]),
            "wechat_adds": int(row["wechat"]),
            "activity_date": str(row["activity_date"].date()) if pd.notna(row["activity_date"]) else None,
            "province_unit": row.get("province_unit_final"),
            "dealer": row.get("dealer_final", row.get("dealer")),
        })
    return results


def run_full_diagnosis(merged: pd.DataFrame, dim_store: pd.DataFrame,
                       dim_dealer: pd.DataFrame) -> dict:
    """运行全部诊断，返回结构化报告。"""
    print("\n运行经营诊断...")
    diagnosis = {
        "inactive_stores": diagnose_inactive_stores(merged, dim_store),
        "low_completion": diagnose_low_completion(merged),
        "single_activity_type": diagnose_single_activity_type(merged),
        "low_sales_activities": diagnose_low_sales_activities(merged),
        "region_gaps": diagnose_region_gaps(merged, dim_dealer),
        "activity_quality": diagnose_activity_quality(merged),
        "excellent_activities": diagnose_excellent_activities(merged),
    }

    for k, v in diagnosis.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} 项")

    return diagnosis


if __name__ == "__main__":
    from .data_model import build_all_models
    models = build_all_models()
    report = run_full_diagnosis(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )
    print("\n=== 诊断摘要 ===")
    for k, v in report.items():
        if isinstance(v, list) and len(v) > 0:
            print(f"\n--- {k} ({len(v)} 项) ---")
            for item in v[:5]:
                if isinstance(item, dict):
                    print(f"  {item.get('description', item)}")
