"""代理商 API：列表、排名、详情。"""

from __future__ import annotations
from flask import Blueprint, request
from .filters import query_df, json_response, json_single

dealer_bp = Blueprint("dealer", __name__, url_prefix="/api/dealers")


@dealer_bp.route("/")
def dealer_list():
    """代理商指标列表。"""
    region = request.args.get("region", "")
    business_category = request.args.get("business_category", "")
    conds = []
    params: dict = {}
    if region:
        conds.append("d.regions LIKE :region")
        params["region"] = f"%{region}%"
    if business_category:
        conds.append("f.business_category = :bc")
        params["bc"] = business_category
    cond = (" WHERE " + " AND ".join(conds)) if conds else ""

    df = query_df(f"""
        SELECT
            d.dealer_id, d.dealer, d.store_count, d.mall_count, d.active_count,
            d.regions, d.total_area,
            COUNT(f.activity_id) AS activity_count,
            SUM(CASE WHEN f.is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count,
            ROUND(COALESCE(SUM(f.sales_clean),0),0) AS total_sales,
            SUM(COALESCE(f.wechat_adds,0)) AS total_wechat,
            SUM(COALESCE(f.participants,0)) AS total_participants,
            COUNT(DISTINCT f.store_id) AS covered_stores,
            ROUND(CAST(SUM(CASE WHEN f.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(COUNT(f.activity_id),0) * 100, 1) AS completion_rate
        FROM dim_dealer d
        LEFT JOIN fact_activity f ON d.dealer = f.dealer
        {cond}
        GROUP BY d.dealer_id, d.dealer, d.store_count, d.mall_count, d.active_count,
                 d.regions, d.total_area
        ORDER BY total_sales DESC
    """, params)
    # Frontend-expected aliases
    df["total_wechat_adds"] = df["total_wechat"]
    df["active_stores"] = df["covered_stores"]
    df["completed_count"] = df["valid_count"]
    df["store_coverage_rate"] = (df["covered_stores"] / df["store_count"]).clip(upper=1).fillna(0)
    df["sales_per_activity"] = (df["total_sales"] / df["activity_count"]).fillna(0)
    df["activity_types"] = 0
    df["completion_rate"] = df["completion_rate"] / 100
    return json_response(df, total=len(df))


@dealer_bp.route("/top")
def top_dealers():
    """代理商排名 Top N。"""
    limit = int(request.args.get("limit", 15))
    df = query_df(f"""
        SELECT dealer,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               COUNT(DISTINCT store_id) AS covered_stores
        FROM fact_activity
        WHERE dealer IS NOT NULL
        GROUP BY dealer ORDER BY total_sales DESC LIMIT :limit
    """, {"limit": limit})
    return json_response(df)


@dealer_bp.route("/<dealer_name>")
def dealer_detail(dealer_name: str):
    """代理商详情。"""
    df = query_df("""
        SELECT dealer,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               SUM(wechat_adds) AS total_wechat,
               SUM(participants) AS total_participants,
               COUNT(DISTINCT store_id) AS covered_stores,
               COUNT(DISTINCT activity_type) AS activity_types,
               ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                   / COUNT(*) * 100, 1) AS completion_rate
        FROM fact_activity WHERE dealer = :dealer
        GROUP BY dealer
    """, {"dealer": dealer_name})
    if df.empty:
        return json_single({"error": "not found"})
    return json_single(df.iloc[0].to_dict())
