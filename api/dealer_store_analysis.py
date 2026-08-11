"""代理商/门店维度分析：活动量、零活动、低转化、低企微。"""

from __future__ import annotations
from metrics.db import query


def generate_dealer_store_analysis(date_from: str = "", date_to: str = "", dealer_type: str = "") -> dict:
    """生成代理商和门店维度的分析数据。

    Args:
        date_from: 起始日期 (YYYY-MM-DD)，空表示不限
        date_to: 结束日期 (YYYY-MM-DD)，空表示不限
        dealer_type: 业态筛选 (Mall商/照材商)，空表示全部
    Returns:
        dict with activity_count_store, activity_count_dealer, zero_activity_stores,
        zero_activity_dealers, low_conversion_stores, low_conversion_dealers,
        low_wechat_stores, low_wechat_dealers
    """
    bc = dealer_type if dealer_type and dealer_type != "all" else ""
    bc_cond = " AND f.business_category = :bc" if bc else ""
    bc_plain = " AND business_category = :bc" if bc else ""
    params = {"bc": bc} if bc else {}

    # Date filter
    date_cond = ""
    if date_from:
        date_cond += " AND f.activity_date >= :df"
        params["df"] = date_from
    if date_to:
        date_cond += " AND f.activity_date <= :dt"
        params["dt"] = date_to

    date_cond_plain = date_cond.replace("f.", "")

    # ── 门店活动量 Top20 ──
    activity_count_store = query(f"""
        SELECT s.store_name,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.wechat_adds),0),0) AS total_wechat
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.store_id IS NOT NULL{bc_cond}{date_cond}
        GROUP BY s.store_name ORDER BY activity_count DESC LIMIT 20
    """, params).to_dict("records")

    # ── 代理商活动量 Top20 ──
    activity_count_dealer = query(f"""
        SELECT f.dealer,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.wechat_adds),0),0) AS total_wechat,
               COUNT(DISTINCT f.store_id) AS stores
        FROM fact_activity f
        WHERE f.dealer IS NOT NULL{bc_cond}{date_cond}
        GROUP BY f.dealer ORDER BY activity_count DESC LIMIT 20
    """, params).to_dict("records")

    # ── 零活动门店 ──
    zero_activity_stores = query(f"""
        SELECT s.store_name, s.dealer, s.province_unit, s.region, s.store_category
        FROM dim_store s
        WHERE s.store_status = '已开业'
        AND s.store_id NOT IN (
            SELECT DISTINCT store_id FROM fact_activity
            WHERE store_id IS NOT NULL{bc_plain}{date_cond_plain}
        )
        ORDER BY s.store_level, s.store_name
    """, params).to_dict("records")

    # ── 零活动代理商 ──
    zero_activity_dealers = query(f"""
        SELECT d.dealer, d.store_count,
               GROUP_CONCAT(d.province_units, '/') AS province_units
        FROM dim_dealer d
        WHERE d.dealer NOT IN (
            SELECT DISTINCT dealer FROM fact_activity
            WHERE dealer IS NOT NULL{bc_plain}{date_cond_plain}
        )
        ORDER BY d.store_count DESC
    """, params).to_dict("records")

    # ── 转化率最低门店 Top20 ──
    low_conversion_stores = query(f"""
        SELECT s.store_name AS store,
               COUNT(*) AS activity_count,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.converted_hosts),0),0) AS total_hosts,
               CASE WHEN SUM(f.participants) > 0
                   THEN ROUND(CAST(SUM(f.converted_hosts) AS FLOAT)/SUM(f.participants),4)
                   ELSE 0 END AS conversion_rate
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.store_id IS NOT NULL{bc_cond}{date_cond}
        GROUP BY s.store_name
        HAVING activity_count >= 3
        ORDER BY conversion_rate ASC LIMIT 20
    """, params).to_dict("records")

    # ── 转化率最低代理商 Top20 ──
    low_conversion_dealers = query(f"""
        SELECT f.dealer,
               COUNT(*) AS activity_count,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.converted_hosts),0),0) AS total_hosts,
               CASE WHEN SUM(f.participants) > 0
                   THEN ROUND(CAST(SUM(f.converted_hosts) AS FLOAT)/SUM(f.participants),4)
                   ELSE 0 END AS conversion_rate
        FROM fact_activity f
        WHERE f.dealer IS NOT NULL{bc_cond}{date_cond}
        GROUP BY f.dealer
        HAVING activity_count >= 3
        ORDER BY conversion_rate ASC LIMIT 20
    """, params).to_dict("records")

    # ── 企微蓄水率最低门店 Top20 ──
    low_wechat_stores = query(f"""
        SELECT s.store_name AS store,
               COUNT(*) AS activity_count,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.wechat_adds),0),0) AS total_wechat,
               CASE WHEN SUM(f.participants) > 0
                   THEN ROUND(CAST(SUM(f.wechat_adds) AS FLOAT)/SUM(f.participants),4)
                   ELSE 0 END AS wechat_rate
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.store_id IS NOT NULL{bc_cond}{date_cond}
        GROUP BY s.store_name
        HAVING activity_count >= 3
        ORDER BY wechat_rate ASC LIMIT 20
    """, params).to_dict("records")

    # ── 企微蓄水率最低代理商 Top20 ──
    low_wechat_dealers = query(f"""
        SELECT f.dealer,
               COUNT(*) AS activity_count,
               COALESCE(ROUND(SUM(f.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(f.wechat_adds),0),0) AS total_wechat,
               CASE WHEN SUM(f.participants) > 0
                   THEN ROUND(CAST(SUM(f.wechat_adds) AS FLOAT)/SUM(f.participants),4)
                   ELSE 0 END AS wechat_rate
        FROM fact_activity f
        WHERE f.dealer IS NOT NULL{bc_cond}{date_cond}
        GROUP BY f.dealer
        HAVING activity_count >= 3
        ORDER BY wechat_rate ASC LIMIT 20
    """, params).to_dict("records")

    return {
        "activity_count_store": activity_count_store,
        "activity_count_dealer": activity_count_dealer,
        "zero_activity_stores": zero_activity_stores,
        "zero_activity_dealers": zero_activity_dealers,
        "low_conversion_stores": low_conversion_stores,
        "low_conversion_dealers": low_conversion_dealers,
        "low_wechat_stores": low_wechat_stores,
        "low_wechat_dealers": low_wechat_dealers,
    }
