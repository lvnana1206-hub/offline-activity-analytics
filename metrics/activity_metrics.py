"""活动指标：活动总量、完成率、销售额、企微、参与人数、趋势。"""

from __future__ import annotations
import pandas as pd
from .db import query, scalar


def activity_overview(business_category: str = "") -> dict:
    """全局活动概览指标。"""
    bc_cond = " AND business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    sql = f"""
        SELECT
            COUNT(*)                                        AS total_activities,
            SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS completed_activities,
            ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(COUNT(*),0) * 100, 1)               AS completion_rate_pct,
            COALESCE(ROUND(SUM(sales_clean),0),0)            AS total_sales,
            COALESCE(ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0),0) AS avg_sales_valid,
            COALESCE(ROUND(SUM(wechat_adds),0),0)            AS total_wechat_adds,
            COALESCE(ROUND(SUM(participants),0),0)           AS total_participants,
            COALESCE(ROUND(AVG(conversion_rate_pct),1),0)    AS avg_conversion_rate,
            SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_activities,
            SUM(CASE WHEN is_recap_completed=1 THEN 1 ELSE 0 END) AS recap_completed,
            SUM(CASE WHEN is_drone_activity=1 THEN 1 ELSE 0 END) AS drone_activities,
            SUM(CASE WHEN is_crossbrand_activity=1 THEN 1 ELSE 0 END) AS crossbrand_activities,
            SUM(CASE WHEN has_product_sales=1 THEN 1 ELSE 0 END) AS activities_with_product
        FROM fact_activity WHERE 1=1{bc_cond}
    """
    row = query(sql, params).iloc[0].to_dict()
    return {k: (int(v) if isinstance(v, (int, float)) and not pd.isna(v) else v) for k, v in row.items()}


def activity_by_type(business_category: str = "") -> pd.DataFrame:
    """按活动类型统计。"""
    bc_cond = " AND business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT activity_type,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0) AS avg_sales,
               SUM(wechat_adds) AS total_wechat,
               ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                   / COUNT(*) * 100, 1) AS completion_rate_pct
        FROM fact_activity
        WHERE activity_type IS NOT NULL{bc_cond}
        GROUP BY activity_type
        ORDER BY activity_count DESC
    """, params)


def activity_by_status() -> pd.DataFrame:
    """按状态统计。"""
    return query("""
        SELECT COALESCE(activity_status,'未填写') AS activity_status,
               COUNT(*) AS count
        FROM fact_activity
        GROUP BY activity_status
        ORDER BY count DESC
    """)


def activity_monthly_trend() -> pd.DataFrame:
    """月度趋势。"""
    return query("""
        SELECT year_month,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               SUM(participants) AS total_participants
        FROM fact_activity
        WHERE year_month IS NOT NULL
        GROUP BY year_month
        ORDER BY year_month
    """)


def activity_quarterly_trend() -> pd.DataFrame:
    """季度趋势。"""
    return query("""
        SELECT quarter_name,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0) AS avg_sales_valid
        FROM fact_activity
        WHERE quarter_name IS NOT NULL AND quarter_name NOT LIKE '%<NA>%'
        GROUP BY quarter_name
        ORDER BY quarter_name
    """)


def activity_by_source() -> pd.DataFrame:
    """按活动来源统计。"""
    return query("""
        SELECT COALESCE(activity_source,'未填写') AS activity_source,
               COUNT(*) AS count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat
        FROM fact_activity
        GROUP BY activity_source
        ORDER BY count DESC
    """)
