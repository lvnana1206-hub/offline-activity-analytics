"""代理商指标：门店覆盖、活动量、销售、排名。"""

from __future__ import annotations
import pandas as pd
from .db import query


def dealer_overview(business_category: str = "") -> dict:
    bc_cond = " AND f.business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    row = query(f"""
        SELECT COUNT(DISTINCT d.dealer_id) AS total_dealers,
               COUNT(DISTINCT f.dealer) AS active_dealers
        FROM dim_dealer d
        LEFT JOIN fact_activity f ON d.dealer = f.dealer
        WHERE 1=1{bc_cond}
    """, params).iloc[0]
    return {"total_dealers": int(row["total_dealers"]),
            "active_dealers": int(row["active_dealers"])}


def dealer_metrics(business_category: str = "") -> pd.DataFrame:
    """代理商级指标明细。"""
    bc_cond = " AND f.business_category = :bc" if business_category else ""
    params = {"bc": business_category} if business_category else {}
    return query(f"""
        SELECT
            f.dealer, d.dealer_id,
            d.store_count, d.mall_count, d.active_count, d.regions,
            COUNT(*) AS activity_count,
            SUM(CASE WHEN f.is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count,
            ROUND(SUM(f.sales_clean),0) AS total_sales,
            ROUND(AVG(CASE WHEN f.is_valid_activity=1 THEN f.sales_clean END),0) AS avg_sales,
            SUM(f.wechat_adds) AS total_wechat,
            SUM(f.participants) AS total_participants,
            COUNT(DISTINCT f.store_id) AS covered_stores,
            ROUND(CAST(SUM(CASE WHEN f.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                / COUNT(*) * 100, 1) AS completion_rate_pct
        FROM fact_activity f
        LEFT JOIN dim_dealer d ON f.dealer = d.dealer
        WHERE f.dealer IS NOT NULL{bc_cond}
        GROUP BY f.dealer, d.dealer_id, d.store_count, d.mall_count, d.active_count, d.regions
        ORDER BY total_sales DESC
    """, params)


def top_dealers(limit: int = 15, business_category: str = "") -> pd.DataFrame:
    return dealer_metrics(business_category).head(limit)
