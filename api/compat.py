"""兼容 API：为 bi_platform.html 提供数据格式适配。"""

from __future__ import annotations
from flask import Blueprint, request, jsonify
from .filters import query_df, query_scalar, build_filters, json_response, json_single
from .dealer_store_analysis import generate_dealer_store_analysis
from metrics.db import query
from sqlalchemy import create_engine, text
from config import PROJECT_ROOT
import numpy as np

compat_bp = Blueprint("compat", __name__)

DB_PATH = PROJECT_ROOT / "database" / "offline_activity.db"
DB_URL = f"sqlite:///{DB_PATH}"

_engine = None
def _eng():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine

def _bc_cond(req):
    bc = req.args.get("business_category", "")
    if not bc or bc == "all":
        bc = req.args.get("dealer_type", "")
    if not bc or bc == "all":
        bc = ""
    cond = " AND business_category = :bc" if bc else ""
    params = {"bc": bc} if bc else {}
    return cond, params

@compat_bp.route("/api/overview")
def overview():
    """全局概览（bi_platform 格式）。"""
    bc, params = _bc_cond(request)
    eng = _eng()
    with eng.connect() as conn:
        row = conn.execute(text(f"""
            SELECT
                COUNT(*) AS total_activities,
                SUM(CASE WHEN activity_status='已完成' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN activity_status='待评估' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN activity_status='交付执行中' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN activity_status='终止' THEN 1 ELSE 0 END) AS terminated,
                COALESCE(ROUND(SUM(sales_clean),0),0) AS total_sales,
                COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
                COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat_adds,
                COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_converted_hosts,
                COUNT(DISTINCT store_id) AS active_stores,
                COUNT(DISTINCT dealer) AS total_dealers,
                ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                    / NULLIF(COUNT(*),0), 4) AS completion_rate,
                COALESCE(ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0),0) AS avg_sales_per_activity
            FROM fact_activity WHERE 1=1{bc}
        """), params).mappings().first()
        total_stores = conn.execute(text("SELECT COUNT(*) FROM dim_store")).scalar()
    d = dict(row)
    d["total_stores"] = total_stores
    d["avg_participants"] = round(d["total_participants"] / d["total_activities"], 1) if d["total_activities"] else 0
    for k,v in d.items():
        if isinstance(v, (np.integer,)): d[k] = int(v)
        elif isinstance(v, (np.floating,)): d[k] = float(v) if not np.isnan(v) else 0
    return jsonify(d)

@compat_bp.route("/api/activity/by_type")
def activity_by_type():
    """活动分类型统计（bi_platform 格式）。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT activity_type,
               COUNT(*) AS activity_count,
               SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS completed_count,
               ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                   / COUNT(*) * 100, 1) AS completion_rate,
               ROUND(SUM(sales_clean),0) AS total_sales,
               ROUND(AVG(CASE WHEN is_valid_activity=1 THEN sales_clean END),0) AS avg_sales,
               ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS sales_per_activity,
               SUM(wechat_adds) AS total_wechat_adds,
               SUM(participants) AS total_participants,
               COUNT(DISTINCT store_id) AS unique_stores
        FROM fact_activity WHERE 1=1{bc} AND activity_type IS NOT NULL
        GROUP BY activity_type ORDER BY activity_count DESC
    """, params)
    df["completion_rate"] = df["completion_rate"] / 100
    return json_response(df)

@compat_bp.route("/api/activity/trend")
def activity_trend():
    """活动月度趋势（bi_platform 格式）。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT year_month,
               COUNT(*) AS activity_count,
               ROUND(SUM(sales_clean),0) AS total_sales,
               COUNT(DISTINCT store_id) AS unique_stores,
               SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS completed_count
        FROM fact_activity WHERE 1=1{bc} AND year_month IS NOT NULL
        GROUP BY year_month ORDER BY year_month
    """, params)
    return json_response(df)

@compat_bp.route("/api/type/month_cross")
def type_month_cross():
    """活动类型 x 月度交叉表（堆叠柱状图用）。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT activity_type, year_month, COUNT(*) AS count
        FROM fact_activity WHERE 1=1{bc} AND activity_type IS NOT NULL AND year_month IS NOT NULL
        GROUP BY activity_type, year_month ORDER BY year_month, activity_type
    """, params)
    return json_response(df)

@compat_bp.route("/api/analysis/dealer_store")
def analysis_dealer_store():
    """代理商/门店维度分析（活动页专用，无日期限制）。"""
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    ds = generate_dealer_store_analysis(date_from=date_from, date_to=date_to, dealer_type=bc)
    return jsonify({"data": ds})

@compat_bp.route("/api/regions")
def regions():
    """区域列表（bi_platform 格式）。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT s.region,
               COUNT(*) AS activity_count,
               SUM(CASE WHEN f.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS completed_count,
               ROUND(CAST(SUM(CASE WHEN f.activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                   / COUNT(*) * 100, 1) AS completion_rate,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               COUNT(DISTINCT f.store_id) AS active_stores,
               COUNT(DISTINCT f.dealer) AS dealers,
               ROUND(SUM(f.sales_clean)/NULLIF(COUNT(DISTINCT f.store_id),0),0) AS sales_per_store
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE 1=1{bc.replace("business_category", "f.business_category")} AND s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region ORDER BY total_sales DESC
    """, params)
    df["completion_rate"] = df["completion_rate"] / 100
    return json_response(df)

@compat_bp.route("/api/provinces")
def provinces():
    """省份销售统计。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT s.province,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE 1=1{bc.replace("business_category", "f.business_category")} AND s.province IS NOT NULL AND s.province != ''
        GROUP BY s.province ORDER BY total_sales DESC
    """, params)
    return json_response(df)

@compat_bp.route("/api/excellent")
def excellent():
    """优秀案例 Top10。"""
    bc, params = _bc_cond(request)
    df = query_df(f"""
        SELECT f.activity_desc, f.activity_type, f.store_name, f.dealer,
               f.sales_clean AS sales, f.participants, f.wechat_adds,
               f.activity_date, s.province AS province_unit
        FROM fact_activity f LEFT JOIN dim_store s ON f.store_id = s.store_id
        WHERE f.is_valid_activity = 1{bc} AND f.sales_clean IS NOT NULL
        ORDER BY f.sales_clean DESC LIMIT 10
    """, params)
    df.insert(0, "rank", range(1, len(df)+1))
    return json_response(df)

@compat_bp.route("/api/stores/inactive")
def stores_inactive():
    """无活动门店统计。"""
    bc, params = _bc_cond(request)
    count = query_scalar(f"""
        SELECT COUNT(*) FROM dim_store s
        WHERE s.store_status = '已开业'
        AND s.store_id NOT IN (
            SELECT DISTINCT store_id FROM fact_activity
            WHERE store_id IS NOT NULL{bc}
        )
    """, params)
    return jsonify({"total": int(count) if count else 0})

@compat_bp.route("/api/stores/low_completion")
def stores_low_completion():
    """低完成率门店统计。"""
    bc, params = _bc_cond(request)
    count = query_scalar(f"""
        SELECT COUNT(*) FROM (
            SELECT store_id, COUNT(*) AS cnt,
                   SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS done
            FROM fact_activity WHERE store_id IS NOT NULL{bc}
            GROUP BY store_id HAVING cnt >= 5 AND done * 100.0 / cnt < 5
        )
    """, params)
    return jsonify({"total": int(count) if count else 0})

@compat_bp.route("/api/insights")
def insights_all():
    """完整洞察（bi_platform 格式适配）。"""
    from analysis.insight_engine import generate_insights
    bc = request.args.get("business_category", "")
    raw = generate_insights(business_category=bc)
    # Adapt field names for bi_platform
    problems = [{"severity": p.get("impact","medium"), "title": p.get("issue",""), "detail": p.get("detail",""), "action": ""} for p in raw.get("problems", [])]
    opportunities = [{"severity": "info", "title": o.get("opportunity",""), "detail": o.get("detail",""), "action": ""} for o in raw.get("opportunities", [])]
    risks = [{"severity": r.get("level","medium"), "title": r.get("risk",""), "detail": r.get("detail",""), "action": ""} for r in raw.get("risks", [])]
    recommendations = [{"priority": i+1, "title": r if isinstance(r, str) else r.get("title",""), "detail": "", "owner": "-", "timeline": "-"} for i, r in enumerate(raw.get("recommendations", []))]
    return jsonify({"problems": problems, "opportunities": opportunities, "risks": risks, "recommendations": recommendations, "replication": []})

@compat_bp.route("/api/diagnostics")
def diagnostics():
    """诊断数据（从规则引擎适配）。"""
    from scoring.rules_engine import run_rules_engine
    bc = request.args.get("business_category", "")
    raw = run_rules_engine(business_category=bc)
    findings = raw.get("findings", [])
    return jsonify({
        "inactive_stores": [{"severity": f["severity"], "description": f["detail"]} for f in findings if f["category"] == "low_activity_stores"],
        "low_completion": [{"severity": f["severity"], "description": f["detail"]} for f in findings if f["category"] == "low_completion_rate"],
        "single_activity_type": [],
        "low_sales_activities": [{"severity": f["severity"], "description": f["detail"]} for f in findings if f["category"] == "low_efficiency_activities"],
        "region_gaps": [],
        "activity_quality": [],
        "excellent_activities": [{"severity": "info", "description": f["detail"]} for f in findings if f["category"] == "excellent_pattern"],
    })


# ── Template compat endpoints ────────────────────

@compat_bp.route("/api/snapshot")
def snapshot():
    """Bulk snapshot data for filtered view."""
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    bc_cond, bc_params = _bc_cond(request) if bc else ("", {})
    if bc and not bc_params:
        bc_params = {"bc": bc}
    df = query_df(f"""
        SELECT COUNT(*) AS count,
               COALESCE(ROUND(SUM(sales_clean),0),0) AS total_sales,
               COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat
        FROM fact_activity WHERE 1=1{bc_cond}
    """, bc_params)
    return jsonify({
        "count": int(df["count"].iloc[0]),
        "total_sales": float(df["total_sales"].iloc[0]),
        "total_wechat": int(df["total_wechat"].iloc[0]),
        "empty": int(df["count"].iloc[0]) == 0,
        "stores": [],
    })


@compat_bp.route("/api/analysis/daily")
def analysis_daily():
    """每日经营分析。"""
    from analysis.daily_analysis import daily_analysis
    target = request.args.get("date")
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    # If no date specified, find the most recent date with activities
    if not target:
        latest = query("SELECT MAX(date(activity_date)) AS d FROM fact_activity WHERE activity_date <= date('now')", {}).iloc[0]
        if latest["d"]:
            target = str(latest["d"])
    result = daily_analysis(target)
    s = result.get("summary", {})
    # Flatten summary into data with frontend-expected key names
    data = {
        "today_count": s.get("activity_count", 0),
        "today_sales": s.get("total_sales", 0),
        "today_participants": s.get("total_participants", 0),
        "today_wechat": s.get("total_wechat", 0),
        "today_hosts": s.get("total_hosts", 0),
        "pending_review_count": s.get("pending_recap", 0),
        "anomaly_count": s.get("anomaly_count", 0),
        "inactive_store_count": s.get("inactive_store_count", 0),
        "today_activities": result.get("today_activities", []),
        "pending_review": result.get("pending_recap", []),
        "anomaly_activities": result.get("anomalies", []),
        "inactive_stores": [s2.get("store_name", "") for s2 in (result.get("inactive_stores") or [])],
        "suggestions": result.get("suggestions", []),
    }
    ds = generate_dealer_store_analysis(date_from=target or "", dealer_type=bc)
    data.update(ds)
    return jsonify({"label": target or "今日", "data": data, "findings": [], "recommendations": []})


@compat_bp.route("/api/analysis/weekly")
def analysis_weekly():
    """每周经营分析。"""
    from analysis.weekly_analysis import weekly_analysis
    target = request.args.get("date")
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    import datetime as dt
    if target:
        ref = dt.date.fromisoformat(target)
    else:
        # Find the most recent week with activities
        latest = query("SELECT MAX(date(activity_date)) AS d FROM fact_activity WHERE activity_date <= date('now')", {}).iloc[0]
        if latest["d"]:
            target = str(latest["d"])
            ref = dt.date.fromisoformat(target)
        else:
            ref = dt.date.today()
    result = weekly_analysis(target)
    s = result.get("summary", {})
    week_start = ref - dt.timedelta(days=ref.weekday())
    week_end = week_start + dt.timedelta(days=6)
    # Extra metrics from DB
    bc_cond_w = " AND business_category = :bc" if bc else ""
    wparams = {"bc": bc} if bc else {}
    wparams["ws"] = week_start.isoformat()
    wparams["we"] = week_end.isoformat()
    extra = query(f"""
        SELECT COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
               COUNT(DISTINCT store_id) AS stores_covered,
               ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(*),0),4) AS completion_rate
        FROM fact_activity WHERE activity_date >= :ws AND activity_date <= :we{bc_cond_w}
    """, wparams).iloc[0].to_dict()
    data = {
        "activity_count": s.get("activity_count", 0),
        "total_sales": s.get("total_sales", 0),
        "total_participants": s.get("total_participants", 0),
        "total_wechat": s.get("total_wechat", 0),
        "valid_activities": s.get("valid_activities", 0),
        "total_hosts": int(extra.get("total_hosts", 0) or 0),
        "stores_covered": int(extra.get("stores_covered", 0) or 0),
        "dealers_covered": s.get("dealer_count", 0),
        "completion_rate": extra.get("completion_rate", 0),
        "excellent_count": s.get("excellent_count", 0),
        "anomaly_count": s.get("anomaly_count", 0),
        "risk_store_count": s.get("risk_store_count", 0),
        "changes": {},
        "dealer_ranking": result.get("dealer_performance", []),
        "excellent_activities": result.get("excellent_activities", []),
        "risk_stores": result.get("risk_stores", []),
        "suggestions": result.get("suggestions", []),
    }
    ds = generate_dealer_store_analysis(
        date_from=week_start.isoformat(),
        date_to=week_end.isoformat(),
        dealer_type=bc
    )
    data.update(ds)
    return jsonify({"label": s.get("week_label", "本周"), "data": data, "findings": [], "recommendations": []})


@compat_bp.route("/api/analysis/monthly")
def analysis_monthly():
    """每月经营分析。"""
    from analysis.monthly_analysis import monthly_analysis
    import datetime as dt
    import calendar
    now = dt.date.today()
    year = request.args.get("year", type=int, default=now.year)
    month = request.args.get("month", type=int, default=now.month)
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    result = monthly_analysis(year, month)
    s = result.get("summary", {})
    ym = s.get("year_month", "")
    if ym:
        date_from = ym + "-01"
        last_day = calendar.monthrange(year, month)[1]
        date_to = f"{ym}-{last_day:02d}"
    else:
        date_from = ""
        date_to = ""
    # Extra metrics from DB
    bc_cond_m = " AND business_category = :bc" if bc else ""
    mparams = {"bc": bc} if bc else {}
    mparams["df"] = date_from
    mparams["dt"] = date_to
    extra = {}
    if date_from:
        extra = query(f"""
            SELECT COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
                   COUNT(DISTINCT store_id) AS stores_covered,
                   COUNT(DISTINCT dealer) AS dealers_covered,
                   ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(*),0),4) AS completion_rate
            FROM fact_activity WHERE activity_date >= :df AND activity_date <= :dt{bc_cond_m}
        """, mparams).iloc[0].to_dict()
    # Map product_performance: product_line -> product, total_qty -> total_sales
    product_perf = []
    for p in (result.get("product_performance") or []):
        product_perf.append({
            "product": p.get("product_line", ""),
            "total_sales": p.get("total_qty", 0),
            "activity_count": p.get("activity_count", 0),
        })
    # Map region_performance fields
    region_perf = result.get("region_performance") or []
    data = {
        "activity_count": s.get("activity_count", 0),
        "total_sales": s.get("total_sales", 0),
        "total_participants": s.get("total_participants", 0),
        "total_wechat": s.get("total_wechat", 0),
        "total_hosts": s.get("total_hosts", int(extra.get("total_hosts", 0) or 0)),
        "stores_covered": int(extra.get("stores_covered", 0) or 0),
        "dealers_covered": int(extra.get("dealers_covered", 0) or 0),
        "completion_rate": extra.get("completion_rate", 0),
        "valid_activities": s.get("valid_activities", 0),
        "drone_activities": s.get("drone_activities", 0),
        "health_score": s.get("health_score", 0),
        "efficiency": result.get("efficiency", {}),
        "funnel": result.get("funnel", {}),
        "changes": {},
        "daily_trend": result.get("daily_trend", []),
        "store_ranking": result.get("top_stores", []),
        "dealer_ranking": result.get("top_dealers", []),
        "product_perf": product_perf,
        "region_perf": region_perf,
    }
    ds = generate_dealer_store_analysis(date_from=date_from, date_to=date_to, dealer_type=bc)
    data.update(ds)
    return jsonify({"label": ym or "本月", "data": data, "findings": [], "recommendations": []})


@compat_bp.route("/api/channel/comparison")
def channel_comparison():
    """Mall商 vs 照材商对比，返回结构化对象。"""
    def _stats(where, params):
        row = query(f"""
            SELECT
                COUNT(*) AS count,
                COALESCE(ROUND(SUM(sales_clean),0),0) AS sales,
                COALESCE(ROUND(SUM(converted_hosts),0),0) AS hosts,
                COALESCE(ROUND(SUM(participants),0),0) AS participants,
                COALESCE(ROUND(SUM(wechat_adds),0),0) AS wechat,
                SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS completed,
                ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS avg_sales,
                COUNT(DISTINCT store_id) AS stores,
                COALESCE(ROUND(SUM(luna_sales),0),0) AS luna,
                COALESCE(ROUND(SUM(go_series_sales),0),0) AS go,
                COALESCE(ROUND(SUM(ace_series_sales),0),0) AS ace,
                ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(*),0)*100,1) AS conv_rate
            FROM fact_activity WHERE {where}
        """, params).iloc[0].to_dict()
        return {k: (int(v) if isinstance(v, float) and v == int(v) else v) for k, v in row.items()}

    return jsonify({
        "mall": _stats("business_category = 'Mall商'", {}),
        "material": _stats("business_category = '照材商'", {}),
    })


@compat_bp.route("/api/channel/drone")
def channel_drone():
    """无人机 vs 非无人机对比，返回结构化对象。"""
    def _stats(where, params):
        row = query(f"""
            SELECT
                COUNT(*) AS count,
                COALESCE(ROUND(SUM(sales_clean),0),0) AS sales,
                COALESCE(ROUND(SUM(converted_hosts),0),0) AS hosts,
                COALESCE(ROUND(SUM(participants),0),0) AS participants,
                COALESCE(ROUND(SUM(wechat_adds),0),0) AS wechat,
                SUM(CASE WHEN is_valid_activity=1 THEN 1 ELSE 0 END) AS completed,
                ROUND(SUM(sales_clean)/NULLIF(COUNT(*),0),0) AS avg_sales,
                COUNT(DISTINCT store_id) AS stores,
                COALESCE(ROUND(SUM(luna_sales),0),0) AS luna,
                COALESCE(ROUND(SUM(go_series_sales),0),0) AS go,
                COALESCE(ROUND(SUM(ace_series_sales),0),0) AS ace,
                ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)/NULLIF(COUNT(*),0)*100,1) AS conv_rate
            FROM fact_activity WHERE {where}
        """, params).iloc[0].to_dict()
        return {k: (int(v) if isinstance(v, float) and v == int(v) else v) for k, v in row.items()}

    return jsonify({
        "drone": _stats("is_drone_activity = 1", {}),
        "normal": _stats("is_drone_activity = 0", {}),
    })


@compat_bp.route("/api/channel/brands")
def channel_brands():
    """异业合作品牌排行。"""
    df = query_df("""
        SELECT COALESCE(partner_brands, '未知') AS brand,
               COUNT(*) AS count,
               COALESCE(ROUND(SUM(sales_clean),0),0) AS sales
        FROM fact_activity
        WHERE is_crossbrand_activity = 1 AND partner_brands IS NOT NULL AND partner_brands != ''
        GROUP BY partner_brands
        ORDER BY count DESC
    """, {})
    return json_response(df)


@compat_bp.route("/api/scores/regions")
def scores_regions():
    """区域评分。"""
    df = query_df("""
        SELECT s.region,
               COUNT(*) AS activity_count,
               ROUND(SUM(f.sales_clean),0) AS total_sales,
               COUNT(DISTINCT f.store_id) AS stores,
               COUNT(DISTINCT f.dealer) AS dealers,
               ROUND(SUM(f.sales_clean)/NULLIF(COUNT(DISTINCT f.store_id),0),0) AS sales_per_store
        FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
        WHERE s.region IS NOT NULL AND s.region != ''
        GROUP BY s.region ORDER BY total_sales DESC
    """, {})
    # Simple grading
    if not df.empty:
        median = df["total_sales"].median()
        df["region_grade"] = df["total_sales"].apply(lambda x: "A" if x >= median*1.5 else ("B" if x >= median else ("C" if x >= median*0.5 else "D")))
    return json_response(df)


@compat_bp.route("/api/insights/summary")
def insights_summary_compat():
    """洞察摘要（适配模板格式）。"""
    from analysis.insight_engine import generate_insights
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    raw = generate_insights(business_category=bc)
    return jsonify([{"severity": p.get("impact", "medium"), "title": p.get("issue", ""), "detail": p.get("detail", ""), "action": ""} for p in raw.get("problems", [])])


@compat_bp.route("/api/insights/recommendations")
def insights_recommendations_compat():
    """运营建议（适配模板格式）。"""
    from analysis.insight_engine import generate_insights
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    raw = generate_insights(business_category=bc)
    return jsonify([{"priority": i+1, "title": r if isinstance(r, str) else r.get("title", ""), "detail": "", "owner": "-", "timeline": "-"} for i, r in enumerate(raw.get("recommendations", []))])


@compat_bp.route("/api/review/q2")
def review_q2():
    """Q2 季度经营复盘数据（实时生成）。"""
    from api.review_generator import generate_q2_review
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    try:
        return jsonify(generate_q2_review(bc))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@compat_bp.route("/api/review/luna")
def review_luna():
    """Luna 上市经营复盘数据（实时生成）。"""
    from api.review_generator import generate_luna_review
    bc = request.args.get("dealer_type", "")
    if bc == "all":
        bc = ""
    try:
        return jsonify(generate_luna_review(bc))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@compat_bp.route("/api/scores/stores")
def scores_stores_compat():
    """门店评分（兼容路由，代理到 insight_bp）。"""
    from api.insight_api import store_scores
    return store_scores()

@compat_bp.route("/api/scores/dealers")
def scores_dealers_compat():
    """代理商评分（兼容路由，代理到 insight_bp）。"""
    from api.insight_api import dealer_scores
    return dealer_scores()

@compat_bp.route("/api/product/monthly")
def product_monthly_compat():
    """产品月度趋势（兼容路由，代理到 product_bp）。"""
    from api.product_api import monthly_trend
    return monthly_trend()

@compat_bp.route("/api/product/type_cross")
def product_type_cross_compat():
    """产品 x 活动类型交叉表（兼容路由）。"""
    bc, params = _bc_cond(request)
    bc_fa = bc.replace("business_category", "fa.business_category")
    df = query_df(f"""
        SELECT fa.activity_type,
               fap.product_line,
               SUM(fap.sales_qty) AS qty
        FROM fact_activity_product fap
        JOIN fact_activity fa ON fap.activity_id = fa.activity_id
        WHERE fa.activity_type IS NOT NULL{bc_fa}
        GROUP BY fa.activity_type, fap.product_line
        ORDER BY fa.activity_type, fap.product_line
    """, params)
    # Pivot: each row has activity_type + product columns
    if df.empty:
        return jsonify({"data": []})
    pivot = df.pivot_table(index="activity_type", columns="product_line", values="qty", fill_value=0).reset_index()
    records = pivot.to_dict("records")
    return jsonify({"data": records})
