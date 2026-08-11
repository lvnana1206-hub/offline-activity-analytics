"""季度经营复盘 (Quarterly Analysis)。

作为 analysis/ 包的季度模块，委托 review_engine 生成完整季度复盘，
并在其基础上补充经营结论与建议的结构化输出。
"""
from __future__ import annotations

import pandas as pd

from .common import prepare, finding, rec
from ..review_engine import quarterly_review, product_launch_review


def quarterly_analysis(merged: pd.DataFrame, year: int = 2026,
                       quarter: int = 2) -> dict:
    """季度经营复盘，整合 review_engine 输出并补齐结论/建议结构。

    Args:
        merged: merged_activity_store 宽表
        year/quarter: 季度
    """
    review = quarterly_review(merged, year=year, quarter=quarter)
    if isinstance(review, dict) and review.get("error"):
        return review

    # review_engine 已输出 section_1..10，这里补充顶层 findings/recommendations
    # 以统一 daily/weekly/monthly/quarterly 的三层结构
    overview = review.get("section_1_overview", {})
    kpis = overview.get("kpis", {})
    diagnosis = review.get("section_9_diagnosis", {})
    recs = review.get("section_10_recommendations", {})

    findings = []
    for f in diagnosis.get("findings", []):
        findings.append(finding(
            f.get("finding", ""),
            f.get("cause", ""),
            f.get("impact", ""),
            f.get("action", ""),
            severity="medium",
        ))

    recommendations = []
    for r in recs.get("recommendations", []):
        recommendations.append(rec(
            r.get("category", ""),
            r.get("suggestion", ""),
            owner="运营部", priority=1, timeline="Q" + str(quarter % 4 + 1),
        ))

    return {
        "label": review.get("label", f"{year} Q{quarter}"),
        "type": "quarterly",
        "year": year,
        "quarter": quarter,
        "data": review,
        "findings": findings,
        "recommendations": recommendations,
    }


def luna_analysis(merged: pd.DataFrame) -> dict:
    """Luna 上市经营复盘（专题），委托 review_engine.product_launch_review。"""
    return product_launch_review(merged)
