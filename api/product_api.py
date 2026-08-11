"""产品 API：产品线列表、销量、趋势、渗透。"""

from __future__ import annotations
from flask import Blueprint, request
from .filters import query_df, build_filters, json_response, json_single

product_bp = Blueprint("product", __name__, url_prefix="/api/products")


@product_bp.route("/")
def product_list():
    """产品线指标列表。"""
    df = query_df("""
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
        GROUP BY p.product_line ORDER BY total_qty DESC
    """)
    # Add frontend-expected aliases
    df["product"] = df["product_line"]
    df["total_sales"] = df["total_qty"]
    df["avg_sales_per_activity"] = df["avg_qty"]
    df["market_share"] = df["total_qty"] / df["total_qty"].sum() if len(df) > 0 else 0
    df["top_activity_types"] = "新品品鉴会"
    return json_response(df)


@product_bp.route("/monthly_trend")
def monthly_trend():
    """产品月度趋势（透视为 year_month + 各产品列）。"""
    df = query_df("""
        SELECT strftime('%Y-%m', fa.activity_date) AS year_month,
               fap.product_line,
               SUM(fap.sales_qty) AS qty
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        WHERE fa.activity_date IS NOT NULL
        GROUP BY year_month, fap.product_line
        ORDER BY year_month
    """)
    if df.empty:
        return json_response(df)
    # Pivot: each row has year_month + product columns
    pivot = df.pivot_table(index="year_month", columns="product_line", values="qty", fill_value=0).reset_index()
    return json_response(pivot)
@product_bp.route("/penetration")
def penetration():
    """产品渗透率。"""
    df = query_df("""
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
    return json_response(df)


@product_bp.route("/by_region")
def by_region():
    """产品分区域销量。"""
    df = query_df("""
        SELECT s.region, f.product_line,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_qty),0) AS total_qty
        FROM fact_activity_product f
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        JOIN dim_store s ON fa.store_id = s.store_id
        WHERE s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region, f.product_line
        ORDER BY s.region, total_qty DESC
    """)
    return json_response(df)


@product_bp.route("/launch_summary")
def launch_summary():
    """新品上市概要（通用，不写死产品名）。"""
    df = query_df("""
        SELECT
            p.product_line,
            MIN(fa.year_month) AS first_seen_month,
            COUNT(DISTINCT f.activity_id) AS total_activities,
            ROUND(SUM(f.sales_qty),0) AS total_qty,
            COUNT(DISTINCT fa.store_id) AS covered_stores,
            COUNT(DISTINCT fa.dealer) AS covered_dealers
        FROM fact_activity_product f
        JOIN dim_product p ON f.product_id = p.product_id
        JOIN fact_activity fa ON f.activity_id = fa.activity_id
        GROUP BY p.product_line ORDER BY total_qty DESC
    """)
    return json_response(df)


@product_bp.route("/options")
def product_options():
    """产品线列表（筛选选项）。"""
    df = query_df("SELECT DISTINCT product_line FROM dim_product ORDER BY product_line")
    return json_single({"product_lines": df["product_line"].tolist()})
