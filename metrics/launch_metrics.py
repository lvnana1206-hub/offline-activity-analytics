"""新品指标：通用产品上市分析，不写死任何产品名。

自动识别所有产品线，支持新品上市追踪、渗透率、趋势对比。
"""

from __future__ import annotations
import pandas as pd
from .db import query


def product_launch_summary() -> pd.DataFrame:
    """所有产品线上市概要：首次出现月份、总销量、覆盖门店、趋势。"""
    return query("""
        SELECT
            p.product_line,
            MIN(fa.year_month) AS first_seen_month,
            COUNT(DISTINCT f.activity_id) AS total_activities,
            ROUND(SUM(f.sales_qty),0) AS total_qty,
            COUNT(DISTINCT fa.store_id) AS covered_stores,
            COUNT(DISTINCT fa.dealer) AS covered_dealers,
            MAX(fa.year_month) AS last_seen_month
        FROM fact_activity_product f
        JOIN dim_product p ON f.product_id = p.product_id
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        GROUP BY p.product_line
        ORDER BY total_qty DESC
    """)


def product_launch_trend(product_line: str | None = None) -> pd.DataFrame:
    """产品月度上市趋势（全部或指定产品线）。"""
    where = ""
    params = {}
    if product_line:
        where = "WHERE f.product_line = :pl"
        params = {"pl": product_line}
    return query(f"""
        SELECT fa.year_month, f.product_line,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_qty),0) AS total_qty,
               COUNT(DISTINCT fa.store_id) AS new_stores
        FROM fact_activity_product f
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        {where}
        GROUP BY fa.year_month, f.product_line
        ORDER BY fa.year_month, f.product_line
    """, params)


def product_penetration() -> pd.DataFrame:
    """产品渗透率：各产品线覆盖门店数 / 总门店数。"""
    return query("""
        SELECT
            p.product_line,
            COUNT(DISTINCT fa.store_id) AS covered_stores,
            (SELECT COUNT(*) FROM dim_store) AS total_stores,
            ROUND(CAST(COUNT(DISTINCT fa.store_id) AS FLOAT)
                / (SELECT COUNT(*) FROM dim_store) * 100, 1) AS penetration_pct
        FROM fact_activity_product f
        JOIN dim_product p ON f.product_id = p.product_id
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        WHERE fa.store_id IS NOT NULL
        GROUP BY p.product_line
        ORDER BY penetration_pct DESC
    """)


def product_quarterly_comparison() -> pd.DataFrame:
    """产品季度对比。"""
    return query("""
        SELECT fa.quarter_name, f.product_line,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_qty),0) AS total_qty,
               COUNT(DISTINCT fa.store_id) AS stores
        FROM fact_activity_product f
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        WHERE fa.quarter_name IS NOT NULL AND fa.quarter_name NOT LIKE '%<NA>%'
        GROUP BY fa.quarter_name, f.product_line
        ORDER BY fa.quarter_name, total_qty DESC
    """)


def launch_analysis(product_line: str) -> dict:
    """单个产品线上市深度分析（通用，任意产品线可调用）。"""
    summary = product_launch_summary()
    row = summary[summary["product_line"] == product_line]
    if row.empty:
        return {"product_line": product_line, "found": False}
    trend = product_launch_trend(product_line)
    penetr = product_penetration()
    pen_row = penetr[penetr["product_line"] == product_line]
    return {
        "product_line": product_line,
        "found": True,
        "first_seen_month": row.iloc[0]["first_seen_month"],
        "total_activities": int(row.iloc[0]["total_activities"]),
        "total_qty": int(row.iloc[0]["total_qty"]),
        "covered_stores": int(row.iloc[0]["covered_stores"]),
        "covered_dealers": int(row.iloc[0]["covered_dealers"]),
        "penetration_pct": float(pen_row.iloc[0]["penetration_pct"]) if not pen_row.empty else 0,
        "monthly_trend": trend.to_dict("records"),
    }
