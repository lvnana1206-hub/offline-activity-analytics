"""每月经营分析：月度总览、每日趋势、排名、复盘。"""

from __future__ import annotations
from datetime import datetime
from metrics.db import query


def monthly_analysis(year: int | None = None, month: int | None = None) -> dict:
    """生成月度经营分析 JSON。"""
    if year is None or month is None:
        today = datetime.now()
        year = today.year
        month = today.month

    ym = f"{year:04d}-{month:02d}"
    p = {"ym": ym}

    activities = query("SELECT activity_id, activity_type, activity_status, store_name, sales_clean, wechat_adds, participants, converted_hosts, is_valid_activity, is_drone_activity FROM fact_activity WHERE year_month = :ym", p)

    # 每日趋势
    daily_trend = query("SELECT CAST(strftime('%d', activity_date) AS INT) AS day, COUNT(*) AS activity_count, ROUND(SUM(sales_clean),0) AS total_sales, SUM(wechat_adds) AS total_wechat, SUM(converted_hosts) AS total_hosts, SUM(participants) AS total_participants FROM fact_activity WHERE year_month = :ym GROUP BY day ORDER BY day", p)

    # 门店排名 Top10
    top_stores = query("""SELECT s.store_name, s.dealer, s.region,
        COUNT(*) AS activity_count,
        ROUND(SUM(f.sales_clean),0) AS total_sales,
        SUM(f.wechat_adds) AS total_wechat,
        SUM(f.participants) AS total_participants,
        SUM(f.converted_hosts) AS total_hosts
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.year_month = :ym GROUP BY s.store_name, s.dealer, s.region
        ORDER BY total_sales DESC LIMIT 10""", p)

    # 代理商排名
    top_dealers = query("""SELECT dealer,
        COUNT(*) AS activity_count,
        ROUND(SUM(sales_clean),0) AS total_sales,
        SUM(wechat_adds) AS total_wechat,
        SUM(participants) AS total_participants,
        SUM(converted_hosts) AS total_hosts,
        COUNT(DISTINCT store_id) AS stores
        FROM fact_activity WHERE year_month = :ym AND dealer IS NOT NULL
        GROUP BY dealer ORDER BY total_sales DESC LIMIT 10""", p)

    # 产品表现
    products = query("SELECT f.product_line, COUNT(*) AS activity_count, ROUND(SUM(f.sales_qty),0) AS total_qty FROM fact_activity_product f JOIN fact_activity fa ON f.activity_id = fa.activity_id WHERE fa.year_month = :ym GROUP BY f.product_line ORDER BY total_qty DESC", p)

    # 区域表现
    regions = query("""SELECT s.region,
        COUNT(*) AS activity_count,
        ROUND(SUM(f.sales_clean),0) AS total_sales,
        SUM(f.wechat_adds) AS total_wechat,
        SUM(f.participants) AS total_participants,
        COUNT(DISTINCT f.store_id) AS stores
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.year_month = :ym AND s.region IS NOT NULL
        GROUP BY s.region ORDER BY total_sales DESC""", p)

    total_activities = len(activities)
    total_sales = float(activities["sales_clean"].sum()) if not activities.empty else 0
    total_hosts = float(activities["converted_hosts"].sum()) if not activities.empty else 0
    total_participants = float(activities["participants"].sum()) if not activities.empty else 0
    total_wechat = float(activities["wechat_adds"].sum()) if not activities.empty else 0
    valid = int(activities["is_valid_activity"].sum()) if not activities.empty else 0
    drone_count = int(activities["is_drone_activity"].sum()) if not activities.empty else 0

    # 健康度测算
    health_score = _health_score(total_activities, valid, total_sales, total_participants, total_wechat)

    # 效率测算
    efficiency = {
        "sales_per_activity": round(total_sales / total_activities, 0) if total_activities else 0,
        "hosts_per_activity": round(total_hosts / total_activities, 1) if total_activities else 0,
        "wechat_rate": round(total_wechat / total_participants, 4) if total_participants else 0,
        "conversion_rate": round(total_hosts / total_participants, 4) if total_participants else 0,
        "valid_rate": round(valid / total_activities, 4) if total_activities else 0,
        "drone_rate": round(drone_count / total_activities, 4) if total_activities else 0,
    }

    # 转化漏斗
    funnel = {
        "total_activities": total_activities,
        "has_participants": int((activities["participants"] > 0).sum()) if not activities.empty else 0,
        "has_wechat": int((activities["wechat_adds"] > 0).sum()) if not activities.empty else 0,
        "has_hosts": int((activities["converted_hosts"] > 0).sum()) if not activities.empty else 0,
        "has_sales": int((activities["sales_clean"] > 0).sum()) if not activities.empty else 0,
    }

    summary = {
        "year": year, "month": month, "year_month": ym,
        "activity_count": total_activities, "valid_activities": valid,
        "total_sales": total_sales, "total_wechat": total_wechat,
        "total_participants": total_participants, "total_hosts": total_hosts,
        "drone_activities": drone_count,
        "health_score": health_score,
    }

    return {
        "summary": summary,
        "daily_trend": daily_trend.to_dict("records"),
        "top_stores": top_stores.to_dict("records"),
        "top_dealers": top_dealers.to_dict("records"),
        "product_performance": products.to_dict("records"),
        "region_performance": regions.to_dict("records"),
        "efficiency": efficiency,
        "funnel": funnel,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _health_score(activities, valid, sales, participants, wechat):
    """计算活动举办健康度 (0-100)。"""
    if activities == 0:
        return 0
    score = 0
    score += min(activities / 50, 1) * 20  # 活动量 20分
    score += min(valid / activities, 1) * 20  # 有效率 20分
    score += min(sales / 500000, 1) * 25  # 销售额 25分
    score += min(participants / 5000, 1) * 15  # 参与度 15分
    score += min(wechat / 1000, 1) * 20  # 企微蓄水 20分
    return round(min(score, 100), 1)
