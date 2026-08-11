"""Flask Web 应用 - 中国区专卖店线下活动经营分析平台。

第五阶段升级：接入统一指标中心 + 规则引擎 + 评分体系 + 洞察引擎。
启动后访问 http://127.0.0.1:8080
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

from ..config import COMPLETED_STATUSES
from ..metrics_center import get_center
from ..rules_engine import get_engine as get_rules_engine
from ..scoring import compute_all_scores
from ..insight_engine import get_engine_insight
from ..review_engine import quarterly_review, product_launch_review
from ..analysis import daily_analysis, weekly_analysis, monthly_analysis

app = Flask(__name__, template_folder="templates", static_folder="static")

_center = get_center()
_rules = get_rules_engine()
_insights = get_engine_insight()

_scores = None
_insight_data = None
_review_cache = {}
_analysis_cache = {}


def _ensure_data():
    global _scores, _insight_data
    if _scores is None:
        _center.initialize(use_feishu=True)
        _scores = compute_all_scores(
            _center.merged, _center.dim_store, _center.dim_dealer
        )
        _insight_data = _insights.generate_insights(
            _center.merged, _center.dim_store, _center.dim_dealer, _scores
        )


def _jsonify_df(df: pd.DataFrame, **extra) -> "flask.Response":
    df = df.replace([np.inf, -np.inf], None)
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S').where(df[col].notna(), None)
    df = df.where(pd.notnull(df), None)
    records = df.to_dict("records")
    return jsonify({"data": records, **extra})


# ── 页面路由 ─────────────────────────────────

@app.route("/")
def index():
    _ensure_data()
    return render_template("index.html")

@app.route("/api/snapshot")
def api_snapshot():
    """筛选快照：按门店类型/代理商类型/时间段筛选后重算全部指标。"""
    _ensure_data()
    filters = {
        "store_type": request.args.get("store_type", ""),
        "dealer_type": request.args.get("dealer_type", ""),
        "period": request.args.get("period", "all"),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", ""),
        "period_value": request.args.get("period_value", ""),
    }
    return jsonify(_center.get_filtered_snapshot(**filters))

@app.route("/api/filter_options")
def api_filter_options():
    """返回可用筛选选项。"""
    _ensure_data()
    from ..filter_engine import get_filter_options
    return jsonify(get_filter_options(_center.dim_dealer, _center.merged))

# ── 效率指标 API ───────────────────────────

@app.route("/api/efficiency")
def api_efficiency():
    """相对值效率指标：活动效率、区域质量、代理商效率。"""
    _ensure_data()
    import numpy as np
    import pandas as pd
    
    merged = _center.merged
    df = merged.copy()
    df["sales"] = pd.to_numeric(df["sales_clean"], errors="coerce").fillna(0)
    df["participants"] = pd.to_numeric(df["participants"], errors="coerce").fillna(0)
    df["wechat"] = pd.to_numeric(df.get("wechat_adds", df.get("wechat", 0)), errors="coerce").fillna(0)
    df["hosts"] = pd.to_numeric(df.get("converted_hosts", df.get("hosts", 0)), errors="coerce").fillna(0)
    
    total = len(df)
    total_sales = df["sales"].sum()
    total_participants = df["participants"].sum()
    total_wechat = df["wechat"].sum()
    total_hosts = df["hosts"].sum()
    
    # 1. 全局效率指标
    global_eff = {
        "sales_per_activity": round(total_sales / total, 2) if total else 0,
        "participants_per_activity": round(total_participants / total, 1) if total else 0,
        "wechat_per_activity": round(total_wechat / total, 1) if total else 0,
        "hosts_per_activity": round(total_hosts / total, 2) if total else 0,
        "wechat_add_rate": round(total_wechat / total_participants, 4) if total_participants else 0,
        "host_conversion_rate": round(total_hosts / total_participants, 4) if total_participants else 0,
        "sales_per_participant": round(total_sales / total_participants, 2) if total_participants else 0,
        "sales_per_host": round(total_sales / total_hosts, 2) if total_hosts else 0,
    }
    
    # 2. 活动类型效率
    type_eff = df.groupby("activity_type").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
    ).reset_index()
    type_eff["sales_per_activity"] = (type_eff["total_sales"] / type_eff["activity_count"]).round(2)
    type_eff["participants_per_activity"] = (type_eff["total_participants"] / type_eff["activity_count"]).round(1)
    type_eff["wechat_per_activity"] = (type_eff["total_wechat"] / type_eff["activity_count"]).round(1)
    type_eff["wechat_add_rate"] = (type_eff["total_wechat"] / type_eff["total_participants"]).round(4)
    type_eff["host_conversion_rate"] = (type_eff["total_hosts"] / type_eff["total_participants"]).round(4)
    type_eff["sales_per_participant"] = (type_eff["total_sales"] / type_eff["total_participants"]).round(2)
    type_eff = type_eff.sort_values("sales_per_activity", ascending=False)
    
    # 3. 代理商效率
    dealer_col = "dealer_final" if "dealer_final" in df.columns else "dealer"
    dealer_eff = df.groupby(dealer_col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        active_stores=("store_name", "nunique"),
    ).reset_index().rename(columns={dealer_col: "dealer"})
    
    # Add store count from dim_dealer
    dd = _center.dim_dealer[["dealer", "store_count"]].drop_duplicates("dealer")
    dealer_eff = dealer_eff.merge(dd, on="dealer", how="left")
    dealer_eff["store_count"] = dealer_eff["store_count"].fillna(1)
    
    dealer_eff["sales_per_activity"] = (dealer_eff["total_sales"] / dealer_eff["activity_count"]).round(2)
    dealer_eff["sales_per_store"] = (dealer_eff["total_sales"] / dealer_eff["active_stores"]).round(2)
    dealer_eff["wechat_add_rate"] = (dealer_eff["total_wechat"] / dealer_eff["total_participants"]).round(4)
    dealer_eff["host_conversion_rate"] = (dealer_eff["total_hosts"] / dealer_eff["total_participants"]).round(4)
    dealer_eff["activity_per_store"] = (dealer_eff["activity_count"] / dealer_eff["store_count"]).round(2)
    dealer_eff["store_coverage_rate"] = (dealer_eff["active_stores"] / dealer_eff["store_count"]).round(4)
    dealer_eff = dealer_eff.sort_values("sales_per_activity", ascending=False)
    
    # 4. 区域效率
    region_col = "province_unit_final" if "province_unit_final" in df.columns else "province"
    region_eff = df.groupby(region_col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
        active_stores=("store_name", "nunique"),
        dealers=("dealer", "nunique"),
    ).reset_index().rename(columns={region_col: "region"})
    region_eff = region_eff[region_eff["region"].notna()]
    region_eff["sales_per_activity"] = (region_eff["total_sales"] / region_eff["activity_count"]).round(2)
    region_eff["sales_per_store"] = (region_eff["total_sales"] / region_eff["active_stores"]).round(2)
    region_eff["participants_per_activity"] = (region_eff["total_participants"] / region_eff["activity_count"]).round(1)
    region_eff["wechat_add_rate"] = (region_eff["total_wechat"] / region_eff["total_participants"]).round(4)
    region_eff["host_conversion_rate"] = (region_eff["total_hosts"] / region_eff["total_participants"]).round(4)
    region_eff["activity_per_dealer"] = (region_eff["activity_count"] / region_eff["dealers"]).round(1)
    region_eff = region_eff.sort_values("sales_per_activity", ascending=False)
    
    def _clean(df):
        df = df.replace([np.inf, -np.inf], None)
        df = df.where(pd.notnull(df), None)
        return df.to_dict("records")
    
    return jsonify({
        "global": global_eff,
        "by_type": _clean(type_eff),
        "by_dealer": _clean(dealer_eff),
        "by_region": _clean(region_eff),
    })

# ── 原有 API（指标中心统一输出） ───────────────────────────

@app.route("/api/overview")
def api_overview():
    _ensure_data()
    return jsonify(_center.get_overview())

@app.route("/api/activity/by_type")
def api_activity_by_type():
    _ensure_data()
    return _jsonify_df(_center.metrics["activity_by_type"])

@app.route("/api/activity/trend")
def api_activity_trend():
    _ensure_data()
    return _jsonify_df(_center.metrics["activity_monthly_trend"])

@app.route("/api/stores")
def api_stores():
    _ensure_data()
    df = _center.metrics["store_metrics"].copy()
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 50))
    search = request.args.get("search", "")
    if search:
        df = df[df["store_name"].str.contains(search, na=False)]
    total = len(df)
    pages = (total + size - 1) // size
    df = df.iloc[(page - 1) * size : page * size]
    return _jsonify_df(df, total=total, page=page, size=size, pages=pages)

@app.route("/api/dealers")
def api_dealers():
    _ensure_data()
    return _jsonify_df(_center.metrics["dealer_metrics"])

@app.route("/api/products")
def api_products():
    _ensure_data()
    return _jsonify_df(_center.metrics["product_metrics"])

@app.route("/api/regions")
def api_regions():
    _ensure_data()
    return _jsonify_df(_center.metrics["region_metrics"])

@app.route("/api/provinces")
def api_provinces():
    _ensure_data()
    return _jsonify_df(_center.metrics["province_metrics"])

@app.route("/api/diagnostics")
def api_diagnostics():
    _ensure_data()
    result = {}
    for key, items in _center.diagnosis.items():
        if isinstance(items, list):
            clean = []
            for item in items:
                if isinstance(item, dict):
                    clean.append({k: (float(v) if isinstance(v, (np.integer, np.floating)) else v)
                                  for k, v in item.items()})
                else:
                    clean.append(item)
            result[key] = clean
    return jsonify(result)

@app.route("/api/excellent")
def api_excellent():
    _ensure_data()
    items = _center.diagnosis.get("excellent_activities", [])
    return jsonify({"data": items})

@app.route("/api/stores/inactive")
def api_inactive_stores():
    _ensure_data()
    items = _center.diagnosis.get("inactive_stores", [])
    return jsonify({"data": items, "total": len(items)})

@app.route("/api/stores/low_completion")
def api_low_completion():
    _ensure_data()
    items = _center.diagnosis.get("low_completion", [])
    return jsonify({"data": items, "total": len(items)})

# ── 第五阶段新增 API ─────────────────────────

@app.route("/api/metrics_center/catalog")
def api_metrics_catalog():
    return jsonify({"data": _center.get_catalog()})

@app.route("/api/metrics_center/overview")
def api_metrics_overview():
    _ensure_data()
    return jsonify(_center.get_overview())

@app.route("/api/rules")
def api_rules():
    return jsonify(_rules.get_rules())

@app.route("/api/scores/stores")
def api_store_scores():
    _ensure_data()
    return _jsonify_df(_scores["store_scores"])

@app.route("/api/scores/dealers")
def api_dealer_scores():
    _ensure_data()
    return _jsonify_df(_scores["dealer_scores"])

@app.route("/api/scores/regions")
def api_region_scores():
    _ensure_data()
    return _jsonify_df(_scores["region_scores"])

@app.route("/api/scores/activities")
def api_activity_scores():
    _ensure_data()
    df = _scores["activity_scores"].copy()
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 50))
    df = df[df["activity_status"].isin(COMPLETED_STATUSES)]
    total = len(df)
    pages = (total + size - 1) // size
    df = df.iloc[(page - 1) * size : page * size]
    return _jsonify_df(df, total=total, page=page, size=size, pages=pages)

@app.route("/api/insights")
def api_insights():
    _ensure_data()
    return jsonify(_insight_data)

@app.route("/api/insights/summary")
def api_insights_summary():
    _ensure_data()
    return jsonify({"data": _insight_data["summary"]})

@app.route("/api/insights/recommendations")
def api_insights_recommendations():
    _ensure_data()
    return jsonify({"data": _insight_data["recommendations"]})

# ── 经营复盘中心 ─────────────────────────────

@app.route("/api/review/q2")
def api_review_q2():
    _ensure_data()
    if "q2" not in _review_cache:
        _review_cache["q2"] = quarterly_review(_center.merged, 2026, 2)
    return jsonify(_review_cache["q2"])

@app.route("/api/review/luna")
def api_review_luna():
    _ensure_data()
    if "luna" not in _review_cache:
        _review_cache["luna"] = product_launch_review(_center.merged)
    return jsonify(_review_cache["luna"])

# ── 经营分析引擎（每日/每周/每月）────────────

@app.route("/api/analysis/daily")
def api_analysis_daily():
    _ensure_data()
    target = request.args.get("date")
    dt = request.args.get("dealer_type", "")
    key = f"daily_{target}_{dt}"
    if key not in _analysis_cache:
        _analysis_cache[key] = daily_analysis(_center.merged, target)
    return jsonify(_analysis_cache[key])

@app.route("/api/analysis/weekly")
def api_analysis_weekly():
    _ensure_data()
    target = request.args.get("date")
    dt = request.args.get("dealer_type", "")
    key = f"weekly_{target}_{dt}"
    if key not in _analysis_cache:
        _analysis_cache[key] = weekly_analysis(_center.merged, target)
    return jsonify(_analysis_cache[key])

@app.route("/api/analysis/monthly")
def api_analysis_monthly():
    _ensure_data()
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    key = f"monthly_{year}_{month}"
    if key not in _analysis_cache or (year or month):
        _analysis_cache[key] = monthly_analysis(_center.merged, year, month, _center.dim_store, _center.dim_dealer)
    return jsonify(_analysis_cache[key])

# ── 渠道 & 产品分析 ───────────────────────────

@app.route("/api/channel/comparison")
def api_channel_comparison():
    _ensure_data()
    from ..channel_metrics import channel_comparison
    return jsonify(channel_comparison(_center.merged))

@app.route("/api/channel/drone")
def api_channel_drone():
    _ensure_data()
    from ..channel_metrics import drone_comparison
    return jsonify(drone_comparison(_center.merged))

@app.route("/api/channel/brands")
def api_channel_brands():
    _ensure_data()
    from ..channel_metrics import brand_ranking
    return _jsonify_df(brand_ranking(_center.merged, 50))

@app.route("/api/funnel")
def api_funnel():
    _ensure_data()
    from ..channel_metrics import conversion_funnel
    return jsonify(conversion_funnel(_center.merged))

@app.route("/api/product/type_cross")
def api_product_type_cross():
    _ensure_data()
    from ..channel_metrics import product_type_cross
    return _jsonify_df(product_type_cross(_center.merged))

@app.route("/api/product/monthly")
def api_product_monthly():
    _ensure_data()
    from ..channel_metrics import product_monthly
    return _jsonify_df(product_monthly(_center.merged))

@app.route("/api/type/month_cross")
def api_type_month_cross():
    _ensure_data()
    from ..channel_metrics import type_month_cross
    return _jsonify_df(type_month_cross(_center.merged))

@app.route("/api/trend/monthly_multi")
def api_trend_monthly_multi():
    _ensure_data()
    from ..channel_metrics import monthly_multi_trend
    return _jsonify_df(monthly_multi_trend(_center.merged))

# ── 周报推送 ─────────────────────────────────

@app.route("/api/weekly_report")
def api_weekly_report():
    """预览代理商周报数据（不推送）。"""
    _ensure_data()
    from ..weekly_push import generate_weekly_report, format_markdown_report
    target = request.args.get("date")
    report = generate_weekly_report(
        _center.merged, _center.dim_store, _center.dim_dealer, target
    )
    report["markdown"] = format_markdown_report(report)
    return jsonify(report)

@app.route("/api/weekly_report/push", methods=["POST"])
def api_weekly_report_push():
    """推送代理商周报到飞书群聊。"""
    _ensure_data()
    from ..weekly_push import run_weekly_push
    target = request.args.get("date")
    chat_id = request.args.get("chat_id", "")
    dry_run = request.args.get("dry_run", "0") == "1"
    result = run_weekly_push(
        _center.merged, _center.dim_store, _center.dim_dealer,
        target, chat_id or None, dry_run,
    )
    return jsonify({
        "push_ok": result["push"].get("ok", False),
        "push_error": result["push"].get("error"),
        "label": result["report"]["label"],
        "summary": result["report"]["summary"],
    })

@app.route("/api/weekly_report/preview")
def api_weekly_report_preview():
    """预览双模板周报：template=dealer|internal。"""
    _ensure_data()
    from ..weekly_push import generate_weekly_report
    from ..report_templates import format_dealer_report
    from ..internal_template import format_internal_report
    tpl = request.args.get("template", "dealer")
    target = request.args.get("date")
    report = generate_weekly_report(
        _center.merged, _center.dim_store, _center.dim_dealer, target
    )
    if tpl == "internal":
        ana = weekly_analysis(_center.merged, target, _center.dim_store, _center.dim_dealer)
        import pandas as _pd
        pm = _center.metrics.get("product_metrics", [])
        pm = pm.to_dict("records") if isinstance(pm, _pd.DataFrame) else pm
        md = format_internal_report(report, {"weekly": ana, "products": pm})
    else:
        md = format_dealer_report(report)
    return jsonify({"markdown": md, "label": report["label"], "template": tpl})

@app.route("/api/weekly_report/push_template", methods=["POST"])
def api_weekly_report_push_template():
    """推送指定模板周报到飞书：template=dealer|internal。"""
    _ensure_data()
    from ..weekly_push import generate_weekly_report, push_to_feishu
    from ..report_templates import format_dealer_report
    from ..internal_template import format_internal_report
    tpl = request.args.get("template", "dealer")
    target = request.args.get("date")
    chat_id = request.args.get("chat_id", "")
    dry_run = request.args.get("dry_run", "0") == "1"
    report = generate_weekly_report(
        _center.merged, _center.dim_store, _center.dim_dealer, target
    )
    if tpl == "internal":
        ana = weekly_analysis(_center.merged, target, _center.dim_store, _center.dim_dealer)
        import pandas as _pd
        pm = _center.metrics.get("product_metrics", [])
        pm = pm.to_dict("records") if isinstance(pm, _pd.DataFrame) else pm
        md = format_internal_report(report, {"weekly": ana, "products": pm})
    else:
        md = format_dealer_report(report)
    push_result = push_to_feishu(md, chat_id or None, dry_run)
    return jsonify({
        "push_ok": push_result.get("ok", False),
        "push_error": push_result.get("error"),
        "label": report["label"],
        "template": tpl,
        "summary": report["summary"],
    })

# ── 月报推送 ─────────────────────────────────

@app.route("/api/monthly_report/preview")
def api_monthly_report_preview():
    """预览双模板月报：template=dealer|internal。"""
    _ensure_data()
    from ..monthly_push import generate_monthly_report, format_dealer_monthly, format_internal_monthly
    tpl = request.args.get("template", "dealer")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    report = generate_monthly_report(
        _center.merged, _center.dim_store, _center.dim_dealer, year, month
    )
    if tpl == "internal":
        md = format_internal_monthly(report)
    else:
        md = format_dealer_monthly(report)
    return jsonify({"markdown": md, "label": report["label"], "template": tpl})

@app.route("/api/monthly_report/push_template", methods=["POST"])
def api_monthly_report_push_template():
    """推送指定模板月报到飞书：template=dealer|internal。"""
    _ensure_data()
    from ..monthly_push import generate_monthly_report, format_dealer_monthly, format_internal_monthly, push_to_feishu
    tpl = request.args.get("template", "dealer")
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    chat_id = request.args.get("chat_id", "")
    dry_run = request.args.get("dry_run", "0") == "1"
    report = generate_monthly_report(
        _center.merged, _center.dim_store, _center.dim_dealer, year, month
    )
    if tpl == "internal":
        md = format_internal_monthly(report)
    else:
        md = format_dealer_monthly(report)
    push_result = push_to_feishu(md, chat_id or None, dry_run)
    return jsonify({
        "push_ok": push_result.get("ok", False),
        "push_error": push_result.get("error"),
        "label": report["label"],
        "template": tpl,
        "summary": report["summary"],
    })


# ── 季度实时追踪 ─────────────────────────────

@app.route("/api/analysis/quarterly_realtime")
def api_quarterly_realtime():
    """季度实时追踪分析（不缓存，每次请求实时计算）。"""
    _ensure_data()
    from ..analysis import realtime_quarterly_analysis
    year = request.args.get("year", type=int)
    quarter = request.args.get("quarter", type=int)
    result = realtime_quarterly_analysis(
        _center.merged, _center.dim_store, _center.dim_dealer, year, quarter
    )
    return jsonify(result)


# ── 异业合作品牌分析 ─────────────────────────

@app.route("/api/brand/analysis")
def api_brand_analysis():
    """异业合作品牌全量分析（大类+品牌排行+对比+趋势）。"""
    _ensure_data()
    from ..brand_analysis import analyze_brand_partnerships
    result = analyze_brand_partnerships(_center.merged, _center.dim_store, _center.dim_dealer)
    return jsonify(result)

@app.route("/api/brand/detail")
def api_brand_detail():
    """单个品牌合作详情（下钻）。"""
    _ensure_data()
    from ..brand_analysis import get_brand_detail
    brand = request.args.get("brand", "")
    if not brand:
        return jsonify({"error": "缺少 brand 参数"})
    result = get_brand_detail(_center.merged, brand)
    return jsonify(result)


def run(host="127.0.0.1", port=8080):
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
