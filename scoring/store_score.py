"""门店评分：活动量 30% + 销售表现 40% + 企微蓄水 20% + 完成率 10%。"""

from __future__ import annotations
import pandas as pd
from metrics import store_metrics
from .activity_score import _percentile_score, _grade


def score_stores(business_category: str = "") -> pd.DataFrame:
    """计算门店评分。"""
    df = store_metrics.store_metrics(business_category)
    if df.empty:
        return df

    df["volume_score"] = _percentile_score(df["activity_count"])
    df["sales_score"] = _percentile_score(df["total_sales"])
    df["wechat_score"] = _percentile_score(df["total_wechat"])
    df["completion_score"] = _percentile_score(df["completion_rate_pct"])

    df["store_score"] = (
        df["volume_score"] * 0.30
        + df["sales_score"] * 0.40
        + df["wechat_score"] * 0.20
        + df["completion_score"] * 0.10
    ).round(1)

    df["grade"] = df["store_score"].apply(_grade)
    df = df.sort_values("store_score", ascending=False).reset_index(drop=True)
    return df


def store_score_distribution() -> dict:
    df = score_stores()
    if df.empty:
        return {}
    dist = df["grade"].value_counts().to_dict()
    return {
        "total_scored": len(df),
        "grade_distribution": dist,
        "avg_score": round(df["store_score"].mean(), 1),
        "a_grade_stores": int(dist.get("A", 0)),
        "d_grade_stores": int(dist.get("D", 0)),
    }
