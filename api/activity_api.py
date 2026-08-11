"""活动 API：列表、详情、筛选。"""

from __future__ import annotations
from flask import Blueprint, request
from .filters import query_df, build_filters, json_response, json_single

activity_bp = Blueprint("activity", __name__, url_prefix="/api/activities")


@activity_bp.route("/")
def activity_list():
    """活动列表（分页+筛选）。"""
    where, params = build_filters()
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 50))
    order = request.args.get("order_by", "activity_date")
    direction = "DESC" if request.args.get("desc", "1") == "1" else "ASC"

    allowed = {"activity_date", "sales_clean", "wechat_adds", "participants"}
    order_col = order if order in allowed else "activity_date"

    total = query_df(f"SELECT COUNT(*) AS n FROM fact_activity f{where}", params)["n"].iloc[0]

    df = query_df(f"""
        SELECT activity_id, activity_desc, activity_date, activity_type, activity_status,
               store_name, dealer, sales_clean, wechat_adds, participants,
               converted_hosts, quarter_name, year_month, is_valid_activity
        FROM fact_activity f{where}
        ORDER BY {order_col} {direction}
        LIMIT :limit OFFSET :offset
    """, {**params, "limit": size, "offset": (page - 1) * size})
    return json_response(df, total=int(total), page=page, size=size)


@activity_bp.route("/by_type")
def by_type():
    """分类型统计。"""
    where, params = build_filters()
    df = query_df(f"""
        SELECT activity_type,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0) AS avg_sales
        FROM fact_activity f{where}
        GROUP BY activity_type ORDER BY activity_count DESC
    """, params)
    return json_response(df)


@activity_bp.route("/by_status")
def by_status():
    """分状态统计。"""
    where, params = build_filters()
    df = query_df(f"""
        SELECT COALESCE(activity_status,'未填写') AS activity_status,
               COUNT(*) AS count
        FROM fact_activity f{where}
        GROUP BY activity_status ORDER BY count DESC
    """, params)
    return json_response(df)


@activity_bp.route("/by_source")
def by_source():
    """分来源统计。"""
    where, params = build_filters()
    df = query_df(f"""
        SELECT COALESCE(activity_source,'未填写') AS activity_source,
               COUNT(*) AS count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat
        FROM fact_activity f{where}
        GROUP BY activity_source ORDER BY count DESC
    """, params)
    return json_response(df)


@activity_bp.route("/monthly_trend")
def monthly_trend():
    """月度趋势。"""
    where, params = build_filters()
    extra = where.replace("WHERE ", "AND ") if where else ""
    df = query_df(f"""
        SELECT year_month,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               SUM(participants) AS total_participants
        FROM fact_activity f
        WHERE year_month IS NOT NULL {extra}
        GROUP BY year_month ORDER BY year_month
    """, params)
    return json_response(df)


@activity_bp.route("/<activity_id>")
def activity_detail(activity_id: str):
    """单条活动详情。"""
    df = query_df("""
        SELECT * FROM fact_activity WHERE activity_id = :aid
    """, {"aid": activity_id})
    if df.empty:
        return json_single({"error": "not found"}, status="error")
    return json_single(df.iloc[0].to_dict())


@activity_bp.route("/options")
def activity_options():
    """筛选选项：活动类型、状态、来源。"""
    types = query_df("SELECT DISTINCT activity_type FROM fact_activity WHERE activity_type IS NOT NULL ORDER BY activity_type")
    statuses = query_df("SELECT DISTINCT activity_status FROM fact_activity WHERE activity_status IS NOT NULL ORDER BY activity_status")
    sources = query_df("SELECT DISTINCT activity_source FROM fact_activity WHERE activity_source IS NOT NULL ORDER BY activity_source")
    return json_single({
        "activity_types": types["activity_type"].tolist(),
        "statuses": statuses["activity_status"].tolist(),
        "sources": sources["activity_source"].tolist(),
    })
