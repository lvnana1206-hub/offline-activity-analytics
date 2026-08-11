"""活动评分：0-100 分，映射 A/B/C/D 等级。

4 维度加权：销售表现 40% + 企微蓄水 20% + 参与人数 20% + 复盘质量 20%。
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from metrics.db import query


def _percentile_score(s: pd.Series, reverse: bool = False) -> pd.Series:
    """百分位归一化到 0-100。"""
    s = pd.to_numeric(s, errors="coerce").fillna(0)
    if s.nunique() <= 1:
        return pd.Series(50.0, index=s.index)
    ranked = s.rank(pct=True)
    if reverse:
        ranked = 1 - ranked
    return (ranked * 100).round(1)


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


def score_activities(business_category: str = "") -> pd.DataFrame:
    """计算全部有效活动的评分。"""
    bc_cond = " AND business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    df = query(f"""
        SELECT activity_id, activity_desc, activity_type, store_name,
               sales_clean, wechat_adds, participants, converted_hosts,
               is_recap_completed, activity_status
        FROM fact_activity
        WHERE is_valid_activity = 1{bc_cond}
    """, params)
    if df.empty:
        return df

    df["sales_score"] = _percentile_score(df["sales_clean"])
    df["wechat_score"] = _percentile_score(df["wechat_adds"])
    df["participation_score"] = _percentile_score(df["participants"])
    df["quality_score"] = _percentile_score(df["converted_hosts"])

    df["activity_score"] = (
        df["sales_score"] * 0.40
        + df["wechat_score"] * 0.20
        + df["participation_score"] * 0.20
        + df["quality_score"] * 0.20
    ).round(1)

    df["grade"] = df["activity_score"].apply(_grade)
    df = df.sort_values("activity_score", ascending=False).reset_index(drop=True)
    return df


def score_distribution(business_category: str = "") -> dict:
    """评分分布统计。"""
    df = score_activities(business_category)
    if df.empty:
        return {}
    dist = df["grade"].value_counts().to_dict()
    return {
        "total_scored": len(df),
        "grade_distribution": dist,
        "avg_score": round(df["activity_score"].mean(), 1),
        "top_score": round(df["activity_score"].max(), 1),
    }
