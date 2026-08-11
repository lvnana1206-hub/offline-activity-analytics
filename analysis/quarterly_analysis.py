"""季度经营复盘：Q-over-Q 对比、产品、门店、区域复盘、下季度建议。"""

from __future__ import annotations
from datetime import datetime
from metrics.db import query


def quarterly_analysis(year: int | None = None, quarter: int | None = None, business_category: str = "") -> dict:
    """生成季度经营复盘 JSON。"""
    if year is None or quarter is None:
        today = datetime.now()
        year = today.year
        quarter = (today.month - 1) // 3 + 1

    qn = f"{year}Q{quarter}"

    # business_category 筛选条件
    bc_cond = " AND business_category = :bc" if business_category else ""
    base_params = {"qn": qn}
    if business_category:
        base_params["bc"] = business_category

    # 本季度概览
    current = query(
        "SELECT COUNT(*) AS activity_count, ROUND(SUM(sales_clean),0) AS total_sales, "
        "SUM(wechat_adds) AS total_wechat, SUM(participants) AS total_participants, "
        "SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count, "
        "SUM(CASE WHEN is_recap_completed=1 THEN 1 ELSE 0 END) AS recap_count "
        "FROM fact_activity WHERE quarter_name = :qn" + bc_cond,
        base_params
    ).iloc[0].to_dict()

    # 上季度
    prev_q = quarter - 1
    prev_y = year
    if prev_q == 0:
        prev_q = 4
        prev_y = year - 1
    prev_qn = f"{prev_y}Q{prev_q}"
    prev_params = {"qn": prev_qn}
    if business_category:
        prev_params["bc"] = business_category
    previous = query(
        "SELECT COUNT(*) AS activity_count, ROUND(SUM(sales_clean),0) AS total_sales, "
        "SUM(wechat_adds) AS total_wechat "
        "FROM fact_activity WHERE quarter_name = :qn" + bc_cond,
        prev_params
    ).iloc[0].to_dict()

    # Q-over-Q 环比
    qoq = {}
    for k in ["activity_count", "total_sales", "total_wechat"]:
        prev_val = float(previous.get(k, 0) or 0)
        curr_val = float(current.get(k, 0) or 0)
        qoq[k] = {"current": curr_val, "previous": prev_val,
                  "change_pct": round((curr_val - prev_val) / prev_val * 100, 1) if prev_val else None}

    # 分类型
    by_type = query(
        "SELECT activity_type, COUNT(*) AS activity_count, ROUND(SUM(sales_clean),0) AS total_sales "
        "FROM fact_activity WHERE quarter_name = :qn" + bc_cond + " AND activity_type IS NOT NULL "
        "GROUP BY activity_type ORDER BY activity_count DESC",
        base_params
    )

    # 门店 Top10
    top_stores = query(
        "SELECT s.store_name, s.dealer, s.region, COUNT(*) AS activity_count, "
        "ROUND(SUM(f.sales_clean),0) AS total_sales "
        "FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id "
        "WHERE f.quarter_name = :qn" + bc_cond.replace("business_category", "f.business_category") +
        " GROUP BY s.store_name, s.dealer, s.region ORDER BY total_sales DESC LIMIT 10",
        base_params
    )

    # 产品表现
    products = query(
        "SELECT f.product_line, COUNT(*) AS activity_count, ROUND(SUM(f.sales_qty),0) AS total_qty "
        "FROM fact_activity_product f JOIN fact_activity fa ON f.activity_id = fa.activity_id "
        "WHERE fa.quarter_name = :qn" + bc_cond.replace("business_category", "fa.business_category") +
        " GROUP BY f.product_line ORDER BY total_qty DESC",
        base_params
    )

    # 区域表现
    regions = query(
        "SELECT s.region, COUNT(*) AS activity_count, ROUND(SUM(f.sales_clean),0) AS total_sales, "
        "SUM(f.wechat_adds) AS total_wechat "
        "FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id "
        "WHERE f.quarter_name = :qn" + bc_cond.replace("business_category", "f.business_category") +
        " AND s.region IS NOT NULL GROUP BY s.region ORDER BY total_sales DESC",
        base_params
    )

    # 建议
    suggestions = []
    if qoq["activity_count"]["change_pct"] is not None and qoq["activity_count"]["change_pct"] < 0:
        suggestions.append(f"活动量环比下降 {qoq['activity_count']['change_pct']}%，建议加强活动推进。")
    if qoq["total_sales"]["change_pct"] is not None and qoq["total_sales"]["change_pct"] < 0:
        suggestions.append(f"销售额环比下降 {qoq['total_sales']['change_pct']}%，建议优化活动类型结构。")
    if float(current.get("recap_count", 0)) < float(current.get("activity_count", 0)) * 0.5:
        suggestions.append("复盘完成率偏低，建议建立活动 7 天闭环制度。")
    if not suggestions:
        suggestions.append("季度经营整体平稳，建议保持现有节奏并优化高效活动类型占比。")

    return {
        "quarter_name": qn,
        "year": year,
        "quarter": quarter,
        "current": {k: (int(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and v != v) else v) for k, v in current.items()},
        "previous_quarter": prev_qn,
        "qoq_comparison": qoq,
        "by_type": by_type.to_dict("records"),
        "top_stores": top_stores.to_dict("records"),
        "product_performance": products.to_dict("records"),
        "region_performance": regions.to_dict("records"),
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
