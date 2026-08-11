"""经营洞察引擎：自动生成经营摘要、问题、机会、风险、建议。"""

from __future__ import annotations
from datetime import datetime
from metrics import activity_metrics, store_metrics, dealer_metrics, product_metrics


def generate_insights(business_category: str = "") -> dict:
    """生成全局经营洞察 JSON。"""
    a_ov = activity_metrics.activity_overview(business_category)
    s_ov = store_metrics.store_overview(business_category)
    d_ov = dealer_metrics.dealer_overview(business_category)
    p_ov = product_metrics.product_overview(business_category)

    # ── 经营摘要 ──
    summary = {
        "total_activities": a_ov["total_activities"],
        "completed_activities": a_ov["completed_activities"],
        "completion_rate_pct": a_ov["completion_rate_pct"],
        "total_sales": a_ov["total_sales"],
        "total_wechat_adds": a_ov["total_wechat_adds"],
        "total_participants": a_ov["total_participants"],
        "active_stores": s_ov["active_stores"],
        "total_stores": s_ov["total_stores"],
        "store_coverage_rate": s_ov["store_coverage_rate"],
        "active_dealers": d_ov["active_dealers"],
        "total_product_lines": p_ov["total_product_lines"],
    }

    # ── 经营问题 ──
    problems = []
    if a_ov["completion_rate_pct"] < 50:
        problems.append({"issue": "活动完成率偏低", "detail": f"完成率仅 {a_ov['completion_rate_pct']}%，{a_ov['total_activities'] - a_ov['completed_activities']} 场未闭环", "impact": "high"})
    inactive = store_metrics.never_active_stores(business_category)
    if not inactive.empty:
        problems.append({"issue": "存在零活动门店", "detail": f"{len(inactive)} 家已开业门店从未举办活动", "impact": "medium"})

    # ── 增长机会 ──
    opportunities = []
    by_type = activity_metrics.activity_by_type(business_category)
    if not by_type.empty:
        best = by_type.iloc[0]
        opportunities.append({"opportunity": "高效活动类型推广", "detail": f"{best['activity_type']} 活动最多（{int(best['activity_count'])} 场），建议标准化推广"})
    top = store_metrics.top_stores(5, business_category)
    if not top.empty:
        opportunities.append({"opportunity": "优秀门店复制", "detail": f"Top5 门店销售 {float(top['total_sales'].sum()):,.0f} 元，建议提炼可复制模式"})
    pen = product_metrics.product_metrics(business_category)
    if not pen.empty:
        low_pen = pen[pen["covered_stores"] < pen["covered_stores"].median()]
        if not low_pen.empty:
            opportunities.append({"opportunity": "产品渗透提升", "detail": f"{len(low_pen)} 个产品线覆盖门店低于中位数，建议扩大铺货"})

    # ── 风险预警 ──
    risks = []
    risk_stores = store_metrics.inactive_stores(30, business_category)
    if not risk_stores.empty:
        risks.append({"risk": "门店沉睡风险", "detail": f"{len(risk_stores)} 家门店 30 天以上无活动", "level": "high"})
    dealers = dealer_metrics.dealer_metrics(business_category)
    if not dealers.empty:
        low_d = dealers[dealers["activity_count"] < dealers["activity_count"].median()]
        if not low_d.empty:
            risks.append({"risk": "代理商活跃度低", "detail": f"{len(low_d)} 家代理商活动量低于中位数", "level": "medium"})

    # ── 运营建议 ──
    recommendations = []
    if a_ov["completion_rate_pct"] < 50:
        recommendations.append("建立活动 7 天闭环制度（区域经理 + 店长）。")
    if not inactive.empty:
        recommendations.append(f"推动 {len(inactive)} 家零活动门店首场活动落地（省区负责人）。")
    if not by_type.empty:
        best_type = by_type.iloc[0]["activity_type"]
        recommendations.append(f"将 {best_type} 活动模式标准化推广（运营部）。")
    recommendations.append("活动标配企微添加环节，提升私域蓄水（店长）。")

    return {
        "summary": summary,
        "problems": problems,
        "opportunities": opportunities,
        "risks": risks,
        "recommendations": recommendations,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
