"""代理商评分：活动量 25% + 销售表现 40% + 门店覆盖 20% + 完成率 15%。"""

from __future__ import annotations
import pandas as pd
from metrics import dealer_metrics
from .activity_score import _percentile_score, _grade


def score_dealers() -> pd.DataFrame:
    """计算代理商评分。"""
    df = dealer_metrics.dealer_metrics()
    if df.empty:
        return df

    df["volume_score"] = _percentile_score(df["activity_count"])
    df["sales_score"] = _percentile_score(df["total_sales"])
    df["coverage_score"] = _percentile_score(df["covered_stores"])
    df["completion_score"] = _percentile_score(df["completion_rate_pct"])

    df["dealer_score"] = (
        df["volume_score"] * 0.25
        + df["sales_score"] * 0.40
        + df["coverage_score"] * 0.20
        + df["completion_score"] * 0.15
    ).round(1)

    df["grade"] = df["dealer_score"].apply(_grade)
    df = df.sort_values("dealer_score", ascending=False).reset_index(drop=True)
    return df


def dealer_score_distribution() -> dict:
    df = score_dealers()
    if df.empty:
        return {}
    dist = df["grade"].value_counts().to_dict()
    return {
        "total_scored": len(df),
        "grade_distribution": dist,
        "avg_score": round(df["dealer_score"].mean(), 1),
    }
