"""每周经营分析：本周总量、代理商表现、优秀/异常活动、风险门店。"""

from __future__ import annotations
from datetime import date, datetime, timedelta
from metrics.db import query


def weekly_analysis(target_date: str | None = None) -> dict:
    """生成本周经营分析 JSON。target_date 为本周任意日期。"""
    if target_date is None:
        target_date = date.today().isoformat()

    week = query("SELECT * FROM fact_activity WHERE strftime('%Y-W%W', activity_date) = strftime('%Y-W%W', date(:d)) ORDER BY activity_date", {"d": target_date})

    # 代理商本周表现
    dealer_perf = query("SELECT dealer, COUNT(*) AS activity_count, ROUND(SUM(sales_clean),0) AS total_sales, SUM(wechat_adds) AS total_wechat, SUM(participants) AS total_participants FROM fact_activity WHERE strftime('%Y-W%W', activity_date) = strftime('%Y-W%W', date(:d)) AND dealer IS NOT NULL GROUP BY dealer ORDER BY total_sales DESC", {"d": target_date})

    # 优秀活动（本周 Top5 by sales）
    excellent = query("SELECT activity_id, activity_desc, activity_type, store_name, sales_clean, wechat_adds, participants FROM fact_activity WHERE strftime('%Y-W%W', activity_date) = strftime('%Y-W%W', date(:d)) AND is_valid_activity = 1 ORDER BY sales_clean DESC LIMIT 5", {"d": target_date})

    # 异常活动
    anomalies = query("SELECT activity_id, activity_desc, store_name, sales_clean, anomaly_reason FROM fact_activity WHERE strftime('%Y-W%W', activity_date) = strftime('%Y-W%W', date(:d)) AND (sales_anomaly = 1 OR (is_valid_activity = 1 AND sales_clean = 0)) LIMIT 10", {"d": target_date})

    # 风险门店（本周无活动且上周也无活动）
    risk_stores = query("SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level, MAX(f.activity_date) AS last_activity FROM dim_store s LEFT JOIN fact_activity f ON s.store_id = f.store_id WHERE s.store_status = '已开业' GROUP BY s.store_id, s.store_name, s.dealer, s.region, s.store_level HAVING last_activity IS NULL OR date(last_activity) < date(:d, '-14 days') ORDER BY s.store_level LIMIT 20", {"d": target_date})

    summary = {
        "target_date": target_date,
        "activity_count": len(week),
        "total_sales": float(week["sales_clean"].sum()) if not week.empty else 0,
        "total_wechat": float(week["wechat_adds"].sum()) if not week.empty else 0,
        "total_participants": float(week["participants"].sum()) if not week.empty else 0,
        "valid_activities": int(week["is_valid_activity"].sum()) if not week.empty and "is_valid_activity" in week.columns else 0,
        "dealer_count": len(dealer_perf),
        "excellent_count": len(excellent),
        "anomaly_count": len(anomalies),
        "risk_store_count": len(risk_stores),
    }

    suggestions = []
    if summary["activity_count"] == 0:
        suggestions.append("本周无活动记录。")
    if summary["anomaly_count"] > 0:
        suggestions.append(f"{summary['anomaly_count']} 条异常活动需关注。")
    if summary["risk_store_count"] > 0:
        suggestions.append(f"{summary['risk_store_count']} 家门店连续两周无活动，建议区域负责人跟进。")
    if not suggestions:
        suggestions.append("本周经营正常。")

    return {
        "summary": summary,
        "dealer_performance": dealer_perf.to_dict("records"),
        "excellent_activities": excellent.to_dict("records"),
        "anomalies": anomalies.to_dict("records"),
        "risk_stores": risk_stores.to_dict("records"),
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
