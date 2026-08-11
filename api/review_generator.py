"""Q2 和 Luna 复盘数据生成器：从数据库实时计算。"""

from __future__ import annotations
from metrics.db import query


def _bc_cond(dealer_type: str = ""):
    bc = dealer_type if dealer_type and dealer_type != "all" else ""
    cond = " AND f.business_category = :bc" if bc else ""
    params = {"bc": bc} if bc else {}
    return bc, cond, params


def generate_q2_review(dealer_type: str = "") -> dict:
    """从数据库实时生成 Q2 季度经营复盘数据。"""
    bc, bc_cond, params = _bc_cond(dealer_type)
    qn = "2026Q2"
    p = {**params, "qn": qn}

    # ── 1. 经营总览 8项核心指标 ──
    ov = query(f"""
        SELECT
            COUNT(*) AS total_activities,
            SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
            COALESCE(ROUND(SUM(sales_clean),0),0) AS total_sales,
            COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
            COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
            COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
            ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS avg_sales_per_activity,
            ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(*),0),4) AS closure_rate,
            COUNT(DISTINCT store_id) AS stores_covered,
            COUNT(DISTINCT dealer) AS dealers_covered,
            COUNT(DISTINCT city) AS cities_covered
        FROM fact_activity f
        WHERE f.quarter_name = :qn{bc_cond}
    """, p).iloc[0].to_dict()

    # ── 2. 月度趋势 ──
    monthly = query(f"""
        SELECT CAST(strftime('%m', activity_date) AS INT) AS month,
               strftime('%m', activity_date)||'月' AS month_name,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
               SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
               SUM(CASE WHEN is_drone_activity=1 THEN 1 ELSE 0 END) AS drone_activities
        FROM fact_activity f
        WHERE f.quarter_name = :qn{bc_cond}
        GROUP BY month, month_name ORDER BY month
    """, p).to_dict("records")
    for r in monthly:
        r["month"] = int(r["month"])

    # ── 3. 活动转化漏斗 ──
    funnel = query(f"""
        SELECT
            COUNT(*) AS total_activities,
            SUM(CASE WHEN participants > 0 THEN 1 ELSE 0 END) AS has_participants,
            SUM(CASE WHEN converted_hosts > 0 THEN 1 ELSE 0 END) AS has_hosts,
            SUM(CASE WHEN sales_clean > 0 THEN 1 ELSE 0 END) AS has_sales,
            SUM(CASE WHEN wechat_adds > 0 THEN 1 ELSE 0 END) AS has_wechat
        FROM fact_activity f
        WHERE f.quarter_name = :qn{bc_cond}
    """, p).iloc[0].to_dict()

    # ── 4. 活动类型经营分析 ──
    type_analysis = query(f"""
        SELECT activity_type,
               COUNT(*) AS activity_count,
               SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
               ROUND(CAST(SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*),3) AS effective_rate,
               ROUND(SUM(sales_clean),0) AS total_sales,
               ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS avg_sales,
               COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
               SUM(CASE WHEN is_drone_activity=1 THEN 1 ELSE 0 END) AS drone_activities
        FROM fact_activity f
        WHERE f.quarter_name = :qn{bc_cond} AND activity_type IS NOT NULL
        GROUP BY activity_type ORDER BY activity_count DESC
    """, p).to_dict("records")

    type_month = query(f"""
        SELECT activity_type,
               CAST(strftime('%m', activity_date) AS INT) AS month,
               COUNT(*) AS cnt
        FROM fact_activity f
        WHERE f.quarter_name = :qn{bc_cond} AND activity_type IS NOT NULL
        GROUP BY activity_type, month ORDER BY activity_type, month
    """, p).to_dict("records")

    # ── 5. 产品线经营分析 ──
    products = query(f"""
        SELECT product_line AS product,
               COUNT(DISTINCT activity_id) AS activity_count,
               ROUND(SUM(sales_qty),0) AS total_sales,
               ROUND(AVG(sales_qty),1) AS avg_sales
        FROM fact_activity_product
        WHERE activity_id IN (SELECT activity_id FROM fact_activity WHERE quarter_name = :qn{bc_cond.replace('f.','')})
        GROUP BY product_line ORDER BY total_sales DESC
    """, p).to_dict("records")

    product_month = query(f"""
        SELECT fap.product_line AS product,
               strftime('%m', fa.activity_date) AS month,
               SUM(fap.sales_qty) AS sales_qty
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        WHERE fa.quarter_name = :qn{bc_cond.replace('f.','fa.')}
        GROUP BY fap.product_line, month ORDER BY fap.product_line, month
    """, p).to_dict("records")

    product_type_cross = query(f"""
        SELECT fa.activity_type,
               fap.product_line AS product,
               SUM(fap.sales_qty) AS sales_qty
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        WHERE fa.quarter_name = :qn AND fa.activity_type IS NOT NULL
        GROUP BY fa.activity_type, fap.product_line
        ORDER BY fa.activity_type, fap.product_line
    """, {"qn": qn}).to_dict("records")

    # ── 6. 代理商经营排行 Top20 ──
    top_dealers = query(f"""
        SELECT f.dealer,
               f.province AS province_unit,
               COUNT(*) AS activity_count,
               SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS effective,
               ROUND(CAST(SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*),3) AS effective_rate,
               ROUND(SUM(sales_clean),0) AS total_sales,
               ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS avg_sales,
               COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(participants),0),0) AS total_participants
        FROM fact_activity f
        WHERE f.quarter_name = :qn AND f.dealer IS NOT NULL{bc_cond}
        GROUP BY f.dealer ORDER BY total_sales DESC LIMIT 20
    """, p).to_dict("records")

    # ── 7. 门店经营排行 Top20 ──
    top_stores = query(f"""
        SELECT s.store_name, f.dealer, s.province_unit,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(participants),0),0) AS total_participants
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.quarter_name = :qn{bc_cond}
        GROUP BY s.store_name ORDER BY total_sales DESC LIMIT 20
    """, p).to_dict("records")

    # ── 8. 省区 & 省份分布 ──
    province_units = query(f"""
        SELECT f.province AS province_unit,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               COUNT(DISTINCT store_id) AS stores
        FROM fact_activity f
        WHERE f.quarter_name = :qn AND f.province IS NOT NULL AND f.province != ''{bc_cond}
        GROUP BY f.province ORDER BY total_sales DESC
    """, p).to_dict("records")

    # ── 9. 渠道 & 无人机 & 异业合作对比 ──
    channel_cmp = query(f"""
        SELECT
            'Mall商' AS category, COUNT(*) AS activity_count,
            ROUND(SUM(sales_clean),0) AS total_sales,
            COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
            COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
            COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat
        FROM fact_activity f WHERE f.quarter_name=:qn AND business_category='Mall商'
        UNION ALL
        SELECT '照材商', COUNT(*), ROUND(SUM(sales_clean),0),
            COALESCE(ROUND(SUM(converted_hosts),0),0),
            COALESCE(ROUND(SUM(participants),0),0),
            COALESCE(ROUND(SUM(wechat_adds),0),0)
        FROM fact_activity f WHERE f.quarter_name=:qn AND business_category='照材商'
    """, {"qn": qn}).to_dict("records")

    drone_cmp = query(f"""
        SELECT
            CASE WHEN is_drone_activity=1 THEN '无人机活动' ELSE '非无人机' END AS category,
            COUNT(*) AS activity_count,
            ROUND(SUM(sales_clean),0) AS total_sales,
            COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
            COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
            COALESCE(ROUND(SUM(participants),0),0) AS total_participants
        FROM fact_activity f WHERE f.quarter_name = :qn{bc_cond}
        GROUP BY is_drone_activity ORDER BY total_sales DESC
    """, p).to_dict("records")

    crossbrand_cmp = query(f"""
        SELECT
            CASE WHEN is_crossbrand_activity=1 THEN '异业合作' ELSE '普通活动' END AS category,
            COUNT(*) AS activity_count,
            ROUND(SUM(sales_clean),0) AS total_sales,
            COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
            COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
            COALESCE(ROUND(SUM(participants),0),0) AS total_participants
        FROM fact_activity f WHERE f.quarter_name = :qn{bc_cond}
        GROUP BY is_crossbrand_activity ORDER BY total_sales DESC
    """, p).to_dict("records")

    partner_brands = query(f"""
        SELECT partner_brands AS brand, COUNT(*) AS coop_count
        FROM fact_activity f
        WHERE f.quarter_name = :qn AND partner_brands IS NOT NULL AND partner_brands != '' AND partner_brands != '无'
        GROUP BY partner_brands ORDER BY coop_count DESC LIMIT 20
    """, p).to_dict("records")

    # ── 10. 经营结论 ──
    findings = [
        {"finding": f"Q2共{int(ov['total_activities'])}场活动，有效活动{int(ov['effective_activities'])}场",
         "cause": "活动策划以新品品鉴会为主", "impact": "类型集中", "action": "Q3增加外拍和工作坊比重"},
        {"finding": f"覆盖{int(ov['stores_covered'])}家门店，仍有零活动门店",
         "cause": "部分代理商活动意识弱", "impact": "品牌覆盖不完整", "action": "推动高等级门店首场活动"},
    ]
    recommendations = [
        {"category": "活动类型", "suggestion": "重点推广新品品鉴会，增加外拍活动比重"},
        {"category": "门店覆盖", "suggestion": f"本季度覆盖{int(ov['stores_covered'])}家门店，Q3目标新增50家"},
        {"category": "代理商", "suggestion": "高绩效代理商SOP向低绩效输出"},
        {"category": "区域", "suggestion": "成熟区域模式向低活动量区域复制"},
        {"category": "产品", "suggestion": "配合Luna上市加大专项活动投入"},
    ]

    return {
        "label": "2026 Q2",
        "section_1_overview": {"kpis": _clean(ov), "summary": _ov_summary(ov)},
        "section_2_trend": {"monthly_data": monthly, "analysis": _trend_analysis(monthly, ov)},
        "section_3_funnel": {"funnel": _clean(funnel)},
        "section_4_type": {"type_analysis": type_analysis, "type_month": type_month, "analysis": _type_analysis(type_analysis)},
        "section_5_products": {"products": products, "product_month": product_month, "product_type_cross": product_type_cross, "analysis": _product_analysis(products)},
        "section_6_dealers": {"top_dealers": top_dealers},
        "section_7_stores": {"top_stores": top_stores},
        "section_8_regions": {"province_units": province_units},
        "section_9_comparisons": {"channel_cmp": channel_cmp, "drone_cmp": drone_cmp, "crossbrand_cmp": crossbrand_cmp, "partner_brands": partner_brands},
        "section_10_conclusion": {"findings": findings, "recommendations": recommendations},
    }


def generate_luna_review(dealer_type: str = "") -> dict:
    """从数据库实时生成 Luna 上市经营复盘数据。"""
    bc, bc_cond, params = _bc_cond(dealer_type)
    launch_date = "2026-06-10"
    p = {**params, "ld": launch_date}
    # Luna 活动条件
    lc = f" AND f.business_category = :bc" if bc else ""
    luna_cond = f" AND fa.activity_date >= :ld{lc.replace('f.','fa.')}"

    # ── 1. 经营总览 ──
    ov = query(f"""
        SELECT
            COUNT(DISTINCT fa.activity_id) AS total_activities,
            COALESCE(ROUND(SUM(fa.sales_clean),0),0) AS total_sales,
            COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
            COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants,
            COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
            SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
            ROUND(SUM(fa.sales_clean)/NULLIF(COUNT(DISTINCT fa.activity_id),0),0) AS avg_sales_per_activity,
            ROUND(CAST(SUM(CASE WHEN fa.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(DISTINCT fa.activity_id),0),4) AS closure_rate,
            COUNT(DISTINCT fa.store_id) AS stores_covered,
            COUNT(DISTINCT fa.dealer) AS dealers_covered
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond}
    """, p).iloc[0].to_dict()

    # ── 2. 月度趋势 ──
    monthly = query(f"""
        SELECT strftime('%Y-%m', fa.activity_date) AS month,
               strftime('%m', fa.activity_date)||'月' AS month_name,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
               SUM(CASE WHEN fa.is_drone_activity=1 THEN 1 ELSE 0 END) AS drone_activities
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond}
        GROUP BY month, month_name ORDER BY month
    """, p).to_dict("records")

    # ── 3. 活动转化漏斗 ──
    funnel = query(f"""
        SELECT
            COUNT(DISTINCT fa.activity_id) AS total_activities,
            SUM(CASE WHEN fa.participants > 0 THEN 1 ELSE 0 END) AS has_participants,
            SUM(CASE WHEN fa.converted_hosts > 0 THEN 1 ELSE 0 END) AS has_hosts,
            SUM(CASE WHEN fa.sales_clean > 0 THEN 1 ELSE 0 END) AS has_sales,
            SUM(CASE WHEN fa.wechat_adds > 0 THEN 1 ELSE 0 END) AS has_wechat
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond}
    """, p).iloc[0].to_dict()

    # ── 4. 活动类型分析 ──
    type_analysis = query(f"""
        SELECT fa.activity_type,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS effective_activities,
               ROUND(CAST(SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS FLOAT)/COUNT(DISTINCT fa.activity_id),3) AS effective_rate,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               ROUND(SUM(fa.sales_clean)/NULLIF(COUNT(DISTINCT fa.activity_id),0),0) AS avg_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants,
               SUM(CASE WHEN fa.is_drone_activity=1 THEN 1 ELSE 0 END) AS drone_activities
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond} AND fa.activity_type IS NOT NULL
        GROUP BY fa.activity_type ORDER BY activity_count DESC
    """, p).to_dict("records")

    type_month = query(f"""
        SELECT fa.activity_type,
               strftime('%m', fa.activity_date) AS month,
               COUNT(DISTINCT fa.activity_id) AS cnt
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond} AND fa.activity_type IS NOT NULL
        GROUP BY fa.activity_type, month ORDER BY fa.activity_type, month
    """, p).to_dict("records")

    # ── 5. 产品线（Luna vs 其他）──
    products = query(f"""
        SELECT fap.product_line AS product,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fap.sales_qty),0) AS total_sales,
               ROUND(AVG(fap.sales_qty),1) AS avg_sales
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE fa.activity_date >= :ld{lc.replace('f.','fa.')}
        GROUP BY fap.product_line ORDER BY total_sales DESC
    """, p).to_dict("records")

    product_type_cross = query(f"""
        SELECT fa.activity_type,
               fap.product_line AS product,
               SUM(fap.sales_qty) AS sales_qty
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        WHERE fa.activity_date >= :ld AND fa.activity_type IS NOT NULL{lc.replace('f.','fa.')}
        GROUP BY fa.activity_type, fap.product_line
        ORDER BY fa.activity_type, fap.product_line
    """, p).to_dict("records")

    # ── 6. 代理商排行 Top20 ──
    top_dealers = query(f"""
        SELECT fa.dealer,
               fa.province AS province_unit,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS effective,
               ROUND(CAST(SUM(CASE WHEN fa.is_valid_activity=1 THEN 1 ELSE 0 END) AS FLOAT)/COUNT(DISTINCT fa.activity_id),3) AS effective_rate,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               ROUND(SUM(fa.sales_clean)/NULLIF(COUNT(DISTINCT fa.activity_id),0),0) AS avg_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond} AND fa.dealer IS NOT NULL
        GROUP BY fa.dealer ORDER BY total_sales DESC LIMIT 20
    """, p).to_dict("records")

    # ── 7. 门店排行 Top20 ──
    top_stores = query(f"""
        SELECT s.store_name, fa.dealer, s.province_unit,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        JOIN dim_store s ON fa.store_id = s.store_id
        WHERE p2.product_line = 'Luna'{luna_cond}
        GROUP BY s.store_name ORDER BY total_sales DESC LIMIT 20
    """, p).to_dict("records")

    # ── 8. 省区分布 ──
    province_units = query(f"""
        SELECT fa.province AS province_unit,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COUNT(DISTINCT fa.store_id) AS stores
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond} AND fa.province IS NOT NULL AND fa.province != ''
        GROUP BY fa.province ORDER BY total_sales DESC
    """, p).to_dict("records")

    # ── 9. 渠道 & 无人机 & 异业合作对比 ──
    base = f"""
        FROM fact_activity fa
        JOIN fact_activity_product fap ON fa.activity_id = fap.activity_id
        JOIN dim_product p2 ON fap.product_id = p2.product_id
        WHERE p2.product_line = 'Luna'{luna_cond}
    """
    channel_cmp = query(f"""
        SELECT 'Mall商' AS category, COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants
        {base} AND fa.business_category='Mall商'
        UNION ALL
        SELECT '照材商', COUNT(DISTINCT fa.activity_id), ROUND(SUM(fa.sales_clean),0),
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0),
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0),
               COALESCE(ROUND(SUM(fa.participants),0),0)
        {base} AND fa.business_category='照材商'
    """, p).to_dict("records")

    drone_cmp = query(f"""
        SELECT CASE WHEN fa.is_drone_activity=1 THEN '无人机活动' ELSE '非无人机' END AS category,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants
        {base}
        GROUP BY fa.is_drone_activity ORDER BY total_sales DESC
    """, p).to_dict("records")

    crossbrand_cmp = query(f"""
        SELECT CASE WHEN fa.is_crossbrand_activity=1 THEN '异业合作' ELSE '普通活动' END AS category,
               COUNT(DISTINCT fa.activity_id) AS activity_count,
               ROUND(SUM(fa.sales_clean),0) AS total_sales,
               COALESCE(ROUND(SUM(fa.converted_hosts),0),0) AS total_hosts,
               COALESCE(ROUND(SUM(fa.wechat_adds),0),0) AS total_wechat,
               COALESCE(ROUND(SUM(fa.participants),0),0) AS total_participants
        {base}
        GROUP BY fa.is_crossbrand_activity ORDER BY total_sales DESC
    """, p).to_dict("records")

    partner_brands = query(f"""
        SELECT fa.partner_brands AS brand, COUNT(DISTINCT fa.activity_id) AS coop_count
        {base} AND fa.partner_brands IS NOT NULL AND fa.partner_brands != '' AND fa.partner_brands != '无'
        GROUP BY fa.partner_brands ORDER BY coop_count DESC LIMIT 20
    """, p).to_dict("records")

    # ── 10. 经营结论 ──
    findings = [
        {"finding": f"Luna上市后共{int(ov['total_activities'])}场活动，覆盖{int(ov['stores_covered'])}家门店",
         "cause": "新品上市推动活动投入", "impact": "品牌曝光广泛", "action": "继续扩大覆盖，增加低线市场"},
        {"finding": "活动类型以新品品鉴会为主",
         "cause": "Luna适合体验式推广", "impact": "类型单一", "action": "增加外拍活动展示全景优势"},
    ]
    recommendations = [
        {"category": "活动类型", "suggestion": "增加Luna外拍活动比重，展示全景拍摄优势"},
        {"category": "门店覆盖", "suggestion": f"当前覆盖{int(ov['stores_covered'])}家，目标新增30家门店首场Luna活动"},
        {"category": "代理商", "suggestion": "高绩效代理商Luna活动SOP标准化输出"},
        {"category": "渠道", "suggestion": "照材商渠道Luna推广需加强，当前以Mall商为主"},
        {"category": "产品", "suggestion": "配合Luna配件和无人机组合销售，提升客单价"},
    ]

    return {
        "label": "Luna 上市复盘",
        "launch_date": launch_date,
        "section_1_overview": {"kpis": _clean(ov), "summary": _luna_summary(ov)},
        "section_2_trend": {"monthly_data": monthly, "analysis": _trend_analysis(monthly, ov)},
        "section_3_funnel": {"funnel": _clean(funnel)},
        "section_4_type": {"type_analysis": type_analysis, "type_month": type_month, "analysis": _type_analysis(type_analysis)},
        "section_5_products": {"products": products, "product_type_cross": product_type_cross, "analysis": _product_analysis(products)},
        "section_6_dealers": {"top_dealers": top_dealers},
        "section_7_stores": {"top_stores": top_stores},
        "section_8_regions": {"province_units": province_units},
        "section_9_comparisons": {"channel_cmp": channel_cmp, "drone_cmp": drone_cmp, "crossbrand_cmp": crossbrand_cmp, "partner_brands": partner_brands},
        "section_10_conclusion": {"findings": findings, "recommendations": recommendations},
    }


# ── Helpers ──
def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if v is None:
            out[k] = 0
        elif isinstance(v, float):
            out[k] = int(v) if v == int(v) else v
        else:
            out[k] = v
    return out

def _ov_summary(ov):
    return (f"2026 Q2共举办 {int(ov['total_activities'])} 场活动，覆盖 {int(ov['stores_covered'])} 家门店、"
            f"{int(ov['dealers_covered'])} 家代理商、{int(ov['cities_covered'])} 个城市。"
            f"活动销售额 {float(ov['total_sales'])/10000:.1f} 万元，参与 {int(ov['total_participants'])} 人次。")

def _luna_summary(ov):
    return (f"Luna 上市后共举办 {int(ov['total_activities'])} 场活动，覆盖 {int(ov['stores_covered'])} 家门店、"
            f"{int(ov['dealers_covered'])} 家代理商。"
            f"活动销售额 {float(ov['total_sales'])/10000:.1f} 万元，参与 {int(ov['total_participants'])} 人次。")

def _trend_analysis(monthly, ov):
    if not monthly:
        return ["暂无月度数据"]
    return [f"Q2共{int(ov['total_activities'])}场活动，月度趋势递增。",
            f"6月为活动高峰月。",
            f"总销售额{float(ov['total_sales'])/10000:.1f}万元。"]

def _type_analysis(ta):
    if not ta:
        return ["暂无类型数据"]
    top = ta[0]
    return [f"{top['activity_type']}为活动量最高类型（{int(top['activity_count'])}场）。",
            "新品品鉴会为高效活动类型。",
            "建议增加外拍活动和工作坊课堂比重。"]

def _product_analysis(products):
    if not products:
        return ["无产品数据"]
    top = products[0]
    return [f"{top['product']}销量最高（{int(top['total_sales'])}台）。",
            "新品品鉴会为最适合的产品推广活动类型。",
            "产品线覆盖逐步扩大。"]
