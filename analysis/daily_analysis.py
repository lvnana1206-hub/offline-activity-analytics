"""每日经营分析：今日活动、待复盘、异常、建议。"""

from __future__ import annotations
from datetime import date, datetime
from metrics.db import query
import pandas as pd


def daily_analysis(target_date: str | None = None) -> dict:
    """生成每日经营分析 JSON。target_date 格式 YYYY-MM-DD，默认今天。"""
    if target_date is None:
        target_date = date.today().isoformat()

    today = query("SELECT activity_id, activity_desc, activity_type, activity_status, store_name, dealer, sales_clean, wechat_adds, participants FROM fact_activity WHERE date(activity_date) = :d ORDER BY sales_clean DESC", {"d": target_date})

    pending = query("SELECT activity_id, activity_desc, activity_date, store_name, activity_status FROM fact_activity WHERE activity_status IN ('交付执行中','复盘收集中') ORDER BY activity_date DESC LIMIT 20")

    anomalies = query("SELECT activity_id, activity_desc, activity_date, store_name, sales_clean, wechat_adds, anomaly_reason FROM fact_activity WHERE sales_anomaly = 1 OR (is_valid_activity = 1 AND sales_clean = 0 AND wechat_adds = 0) ORDER BY activity_date DESC LIMIT 20")

    inactive = query("SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level, MAX(f.activity_date) AS last_activity FROM dim_store s LEFT JOIN fact_activity f ON s.store_id = f.store_id WHERE s.store_status = '已开业' GROUP BY s.store_id, s.store_name, s.dealer, s.region, s.store_level HAVING last_activity IS NULL OR date(last_activity) < date(:d, '-30 days') ORDER BY s.store_level LIMIT 20", {"d": target_date})

    summary = {
        "target_date": target_date,
        "activity_count": len(today),
        "total_sales": float(today["sales_clean"].sum()) if not today.empty else 0,
        "total_wechat": float(today["wechat_adds"].sum()) if not today.empty else 0,
        "total_participants": float(today["participants"].sum()) if not today.empty else 0,
        "pending_recap": len(pending),
        "anomaly_count": len(anomalies),
        "inactive_store_count": len(inactive),
    }

    suggestions = []
    if summary["activity_count"] == 0:
        suggestions.append("今日无活动记录，建议确认是否有遗漏提报。")
    if summary["pending_recap"] > 0:
        suggestions.append(f"{summary['pending_recap']} 场活动待复盘，建议区域经理跟进闭环。")
    if summary["anomaly_count"] > 0:
        suggestions.append(f"{summary['anomaly_count']} 条异常活动，建议逐条核查原因。")
    if summary["inactive_store_count"] > 0:
        suggestions.append(f"{summary['inactive_store_count']} 家门店 30 天以上无活动，建议推动首场活动。")
    if not suggestions:
        suggestions.append("经营正常，暂无紧急事项。")

    return {
        "summary": summary,
        "today_activities": today.to_dict("records"),
        "pending_recap": pending.to_dict("records"),
        "anomalies": anomalies.to_dict("records"),
        "inactive_stores": inactive.to_dict("records"),
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
