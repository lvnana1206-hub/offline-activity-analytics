"""区域指标：活动量、销售、门店覆盖、代理商分布。"""

from __future__ import annotations
import pandas as pd
from .db import query


def region_metrics() -> pd.DataFrame:
    """区域级指标明细。"""
    return query("""
        SELECT
            s.region,
            COUNT(*) AS activity_count,
            SUM(CASE WHEN f.is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count,
            ROUND(SUM(f.sales_clean),0) AS total_sales,
            ROUND(AVG(CASE WHEN f.is_valid_activity=1 THEN f.sales_clean END),0) AS avg_sales,
            SUM(f.wechat_adds) AS total_wechat,
            SUM(f.participants) AS total_participants,
            COUNT(DISTINCT f.store_id) AS active_stores,
            COUNT(DISTINCT f.dealer) AS active_dealers,
            COUNT(DISTINCT f.activity_type) AS activity_types
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region
        ORDER BY total_sales DESC
    """)


def province_metrics() -> pd.DataFrame:
    """省级指标。"""
    return query("""
        SELECT
            s.province, s.region,
            COUNT(*) AS activity_count,
            ROUND(SUM(f.sales_clean),0) AS total_sales,
            SUM(f.wechat_adds) AS total_wechat,
            COUNT(DISTINCT f.store_id) AS active_stores
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE s.province IS NOT NULL AND s.province != ''
        GROUP BY s.province, s.region
        ORDER BY total_sales DESC
    """)


def region_store_coverage() -> pd.DataFrame:
    """区域门店覆盖率。"""
    return query("""
        SELECT s.region,
               COUNT(*) AS total_stores,
               COUNT(DISTINCT f.store_id) AS active_stores,
               ROUND(CAST(COUNT(DISTINCT f.store_id) AS FLOAT) / COUNT(*) * 100, 1) AS coverage_pct
        FROM dim_store s
        LEFT JOIN fact_activity f ON s.store_id = f.store_id
        WHERE s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region
        ORDER BY total_stores DESC
    """)
