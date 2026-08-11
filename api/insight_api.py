"""洞察 API：经营分析 + 评分 + 规则引擎。"""

from __future__ import annotations
import json as json_lib
from flask import Blueprint, request
from .filters import json_response, json_single

insight_bp = Blueprint("insight", __name__, url_prefix="/api/insights")


@insight_bp.route("/daily")
def daily():
    """每日经营分析。"""
    from analysis.daily_analysis import daily_analysis
    target = request.args.get("date")
    result = daily_analysis(target)
    return json_single(result)


@insight_bp.route("/weekly")
def weekly():
    """每周经营分析。"""
    from analysis.weekly_analysis import weekly_analysis
    target = request.args.get("date")
    result = weekly_analysis(target)
    return json_single(result)


@insight_bp.route("/monthly")
def monthly():
    """每月经营分析。"""
    from analysis.monthly_analysis import monthly_analysis
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    result = monthly_analysis(year, month)
    return json_single(result)


@insight_bp.route("/quarterly")
def quarterly():
    """季度经营复盘。"""
    from analysis.quarterly_analysis import quarterly_analysis
    year = request.args.get("year", type=int)
    quarter = request.args.get("quarter", type=int)
    bc = request.args.get("business_category", "")
    result = quarterly_analysis(year, quarter, business_category=bc)
    return json_single(result)


@insight_bp.route("/overview")
def overview():
    """经营洞察总览。"""
    from analysis.insight_engine import generate_insights
    bc = request.args.get("business_category", "")
    return json_single(generate_insights(business_category=bc))


@insight_bp.route("/summary")
def summary():
    """经营摘要。"""
    from analysis.insight_engine import generate_insights
    return json_single(generate_insights()["summary"])


@insight_bp.route("/recommendations")
def recommendations():
    """运营建议。"""
    from analysis.insight_engine import generate_insights
    return json_single({"data": generate_insights()["recommendations"]})


@insight_bp.route("/rules")
def rules():
    """规则引擎发现。"""
    from scoring.rules_engine import run_rules_engine
    bc = request.args.get("business_category", "")
    return json_single(run_rules_engine(business_category=bc))


@insight_bp.route("/scores/activities")
def activity_scores():
    """活动评分。"""
    from scoring.activity_score import score_activities
    df = score_activities()
    return json_response(df, total=len(df))


@insight_bp.route("/scores/stores")
def store_scores():
    """门店评分。"""
    from scoring.store_score import score_stores
    df = score_stores()
    return json_response(df, total=len(df))


@insight_bp.route("/scores/dealers")
def dealer_scores():
    """代理商评分。"""
    from scoring.dealer_score import score_dealers
    df = score_dealers()
    return json_response(df, total=len(df))
