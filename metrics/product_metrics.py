"""产品指标：产品线销量、活动数、渗透门店、趋势。"""

from __future__ import annotations
import pandas as pd
from .db import query, scalar


def product_overview(business_category: str = "") -> dict:
    if business_category:
        row = query("""
            SELECT COUNT(DISTINCT f.product_line) AS total_products,
                   COUNT(DISTINCT f.activity_id) AS activities_with_product,
                   ROUND(SUM(f.sales_qty),0) AS total_qty
            FROM fact_activity_product f
            JOIN fact_activity fa ON f.activity_id = fa.activity_id
            WHERE fa.business_category = :bc
        """, {"bc": business_category}).iloc[0]
    else:
        row = query("""
            SELECT COUNT(DISTINCT product_line) AS total_products,
                   COUNT(DISTINCT activity_id) AS activities_with_product,
                   ROUND(SUM(sales_qty),0) AS total_qty
            FROM fact_activity_product
        """).iloc[0]
    return {"total_product_lines": int(row["total_products"]),
            "activities_with_product": int(row["activities_with_product"]),
            "total_sales_qty": int(row["total_qty"])}


def product_metrics(business_category: str = "") -> pd.DataFrame:
    """产品级指标明细。"""
    bc_cond = " AND fa.business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT
            p.product_line,
            COUNT(DISTINCT f.activity_id) AS activity_count,
            ROUND(SUM(f.sales_qty),0) AS total_qty,
            ROUND(AVG(f.sales_qty),1) AS avg_qty,
            COUNT(DISTINCT fa.store_id) AS covered_stores,
            COUNT(DISTINCT fa.dealer) AS covered_dealers
        FROM fact_activity_product f
        JOIN dim_product p ON f.product_id = p.product_id
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        WHERE 1=1{bc_cond}
        GROUP BY p.product_line
        ORDER BY total_qty DESC
    """, params)


def product_monthly_trend() -> pd.DataFrame:
    """产品月度销量趋势。"""
    return query("""
        SELECT fa.year_month, f.product_line,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_qty),0) AS total_qty
        FROM fact_activity_product f
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        WHERE fa.year_month IS NOT NULL
        GROUP BY fa.year_month, f.product_line
        ORDER BY fa.year_month, f.product_line
    """)


def product_by_region() -> pd.DataFrame:
    """产品分区域销量。"""
    return query("""
        SELECT s.region, f.product_line,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_qty),0) AS total_qty
        FROM fact_activity_product f
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        JOIN dim_store s ON fa.store_id = s.store_id
        WHERE s.region IS NOT NULL
        GROUP BY s.region, f.product_line
        ORDER BY s.region, total_qty DESC
    """)
