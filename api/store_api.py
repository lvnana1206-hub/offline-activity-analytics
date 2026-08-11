"""门店 API：列表、排名、不活跃。"""

from __future__ import annotations
from flask import Blueprint, request
from .filters import query_df, build_filters, json_response, json_single

store_bp = Blueprint("store", __name__, url_prefix="/api/stores")


@store_bp.route("/")
def store_list():
    """门店指标列表（支持 region/dealer 筛选）。"""
    region = request.args.get("region", "")
    dealer = request.args.get("dealer", "")
    store_category = request.args.get("store_category", "")
    business_category = request.args.get("business_category", "")
    conds = []
    params: dict = {}
    if region:
        conds.append("s.region = :region")
        params["region"] = region
    if dealer:
        conds.append("s.dealer = :dealer")
        params["dealer"] = dealer
    if store_category:
        conds.append("s.store_category = :store_category")
        params["store_category"] = store_category
    if business_category:
        conds.append("f.business_category = :business_category")
        params["business_category"] = business_category
    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    df = query_df(f"""
        SELECT s.store_id, s.store_name, s.dealer, s.region, s.province, s.city,
               s.store_level, s.store_category, s.is_new_store,
               COUNT(f.activity_id) AS activity_count,
               SUM(CASE WHEN f.is_valid_activity=1 THEN 1 ELSE 0 END) AS valid_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               SUM(f.wechat_adds) AS total_wechat,
               SUM(f.participants) AS total_participants,
               MAX(f.activity_date) AS last_activity
        FROM dim_store s
        LEFT JOIN fact_activity f ON s.store_id = f.store_id
        {where}
        GROUP BY s.store_id, s.store_name, s.dealer, s.region, s.province, s.city,
                 s.store_level, s.store_category, s.is_new_store
        ORDER BY total_sales DESC
    """, params)
    # Frontend-expected aliases
    df["province_unit"] = df["province"]
    df["completed_count"] = df["valid_count"]
    df["completion_rate"] = (df["completed_count"] / df["activity_count"].clip(lower=1)).clip(upper=1).fillna(0)
    df["total_wechat_adds"] = df["total_wechat"]
    return json_response(df, total=len(df))


@store_bp.route("/top")
def top_stores():
    """销售 Top N 门店。"""
    limit = int(request.args.get("limit", 20))
    df = query_df(f"""
        SELECT s.store_name, s.dealer, s.region,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               SUM(f.wechat_adds) AS total_wechat
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        GROUP BY s.store_name, s.dealer, s.region
        ORDER BY total_sales DESC LIMIT :limit
    """, {"limit": limit})
    return json_response(df)


@store_bp.route("/inactive")
def inactive_stores():
    """不活跃门店。"""
    days = int(request.args.get("days", 30))
    df = query_df(f"""
        SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level,
               MAX(f.activity_date) AS last_activity
        FROM dim_store s
        LEFT JOIN fact_activity f ON s.store_id = f.store_id
        WHERE s.store_status = '已开业'
        GROUP BY s.store_id, s.store_name, s.dealer, s.region, s.store_level
        HAVING last_activity IS NULL
            OR date(last_activity) < date('now', '-{days} days')
        ORDER BY s.store_level, s.store_name
    """)
    return json_response(df, total=len(df))


@store_bp.route("/never_active")
def never_active():
    """从未活动门店。"""
    df = query_df("""
        SELECT s.store_id, s.store_name, s.dealer, s.region, s.store_level
        FROM dim_store s
        WHERE s.store_id NOT IN (
            SELECT DISTINCT store_id FROM fact_activity WHERE store_id IS NOT NULL
        ) AND s.store_status = '已开业'
        ORDER BY s.store_level, s.store_name
    """)
    return json_response(df, total=len(df))


@store_bp.route("/regions")
def regions():
    """区域列表（筛选选项）。"""
    df = query_df("SELECT DISTINCT region FROM dim_store WHERE region IS NOT NULL AND region != '' ORDER BY region")
    return json_single({"regions": df["region"].tolist()})
