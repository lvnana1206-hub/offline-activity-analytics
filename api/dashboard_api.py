"""Dashboard 概览 API。"""

from __future__ import annotations
from flask import Blueprint, request
from .filters import query_df, query_scalar, build_filters, json_response, json_single

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("/overview")
def overview():
    """全局概览指标（支持筛选参数）。"""
    where, params = build_filters()
    row = query_df(f"""
        SELECT
            COUNT(*) AS total_activities,
            SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_activities,
            SUM(CASE WHEN is_recap_completed=1 THEN 1 ELSE 0 END) AS recap_completed,
            COALESCE(ROUND(SUM(sales_clean),0),0) AS total_sales,
            COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
            COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
            COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
            COUNT(DISTINCT store_id) AS active_stores,
            COUNT(DISTINCT dealer) AS active_dealers,
            ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(COUNT(*),0) * 100, 1) AS completion_rate
        FROM fact_activity f{where}
    """, params).iloc[0].to_dict()
    return json_single(row)


@dashboard_bp.route("/activity_by_type")
def by_type():
    """按活动类型统计。"""
    where, params = build_filters()
    extra = where.replace("WHERE ", "AND ") if where else ""
    df = query_df(f"""
        SELECT activity_type,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0) AS avg_sales
        FROM fact_activity f
        WHERE activity_type IS NOT NULL {extra}
        GROUP BY activity_type ORDER BY activity_count DESC
    """, params)
    return json_response(df)


@dashboard_bp.route("/trend")
def trend():
    """月度趋势。"""
    where, params = build_filters()
    extra = where.replace("WHERE ", "AND ") if where else ""
    df = query_df(f"""
        SELECT year_month,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat
        FROM fact_activity f
        WHERE year_month IS NOT NULL {extra}
        GROUP BY year_month ORDER BY year_month
    """, params)
    return json_response(df)


@dashboard_bp.route("/quarterly_trend")
def quarterly_trend():
    """季度趋势。"""
    where, params = build_filters()
    extra = where.replace("WHERE ", "AND ") if where else ""
    df = query_df(f"""
        SELECT quarter_name,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat
        FROM fact_activity f
        WHERE quarter_name IS NOT NULL AND quarter_name NOT LIKE '%<NA>%' {extra}
        GROUP BY quarter_name ORDER BY quarter_name
    """, params)
    return json_response(df)


@dashboard_bp.route("/region_summary")
def region_summary():
    """区域汇总（需 JOIN dim_store）。"""
    where, params = build_filters(join_store=True)
    df = query_df(f"""
        SELECT s.region,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               SUM(f.wechat_adds) AS total_wechat,
               COUNT(DISTINCT f.store_id) AS active_stores
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        {where}
        {"AND" if where else "WHERE"} s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region ORDER BY total_sales DESC
    """, params)
    return json_response(df)
