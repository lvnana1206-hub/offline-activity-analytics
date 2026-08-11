"""门店指标：覆盖率、活跃度、销售、排名、不活跃门店。"""

from __future__ import annotations
import pandas as pd
from .db import query, scalar


def store_overview(business_category: str = "") -> dict:
    """门店全局概览。"""
    total = scalar("SELECT COUNT(*) FROM dim_store")
    if business_category:
        active = scalar("SELECT COUNT(DISTINCT store_id) FROM fact_activity WHERE store_id IS NOT NULL AND business_category = :bc", {"bc": business_category})
    else:
        active = scalar("SELECT COUNT(DISTINCT store_id) FROM fact_activity WHERE store_id IS NOT NULL")
    return {
        "total_stores": int(total),
        "active_stores": int(active),
        "inactive_stores": int(total) - int(active),
        "store_coverage_rate": round(int(active) / int(total) * 100, 1) if total else 0,
    }


def store_metrics(business_category: str = "") -> pd.DataFrame:
    """门店级指标明细。"""
    bc_cond = " AND f.business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT
            f.store_id, s.store_name, s.dealer, s.region, s.province, s.city,
            s.store_level, s.store_category, s.is_new_store,
            COUNT(*) AS activity_count,
            SUM(CASE WHEN f.is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count,
            SUM(CASE WHEN f.is_recap_completed=1 THEN 1 ELSE 0 END) AS recap_completed,
            ROUND(SUM(f.sales_clean),0) AS total_sales,
            ROUND(AVG(CASE WHEN f.is_valid_activity=1 THEN f.sales_clean END),0) AS avg_sales,
            SUM(f.wechat_adds) AS total_wechat,
            SUM(f.participants) AS total_participants,
            ROUND(CAST(SUM(CASE WHEN f.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                / COUNT(*) * 100, 1) AS completion_rate_pct,
            MAX(f.activity_date) AS last_activity_date
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.store_id IS NOT NULL{bc_cond}
        GROUP BY f.store_id, s.store_name, s.dealer, s.region, s.province, s.city,
                 s.store_level, s.store_category, s.is_new_store
        ORDER BY total_sales DESC
    """, params)


def top_stores(limit: int = 20, business_category: str = "") -> pd.DataFrame:
    return store_metrics(business_category).head(limit)


def inactive_stores(days: int = 30, business_category: str = "") -> pd.DataFrame:
    """N 天内无活动的已开业门店。"""
    bc_cond = " AND business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level,
               s.store_status, s.open_date
        FROM dim_store s
        WHERE s.store_id NOT IN (
            SELECT DISTINCT store_id FROM fact_activity
            WHERE store_id IS NOT NULL AND activity_date >= date('now','-{days} days'){bc_cond}
        ) AND s.store_status = '已开业'
        ORDER BY s.store_level, s.store_name
    """, params)


def never_active_stores(business_category: str = "") -> pd.DataFrame:
    """从未举办活动的已开业门店。"""
    bc_cond = " AND business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level
        FROM dim_store s
        WHERE s.store_id NOT IN (
            SELECT DISTINCT store_id FROM fact_activity WHERE store_id IS NOT NULL{bc_cond}
        ) AND s.store_status = '已开业'
        ORDER BY s.store_level, s.store_name
    """, params)
