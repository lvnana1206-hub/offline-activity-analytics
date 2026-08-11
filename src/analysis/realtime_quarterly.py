"""季度实时追踪分析 (Real-time Quarterly Tracking)。

在季度复盘基础上增加：
  - 月度进度追踪（季度内每月完成情况）
  - 周度节奏追踪（零售周维度活动量趋势）
  - 季度进度指标（已过天数/周数/目标达成率）
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime

from .common import prepare, safe_num, compute_health_score
from ..review_engine import quarterly_review


def realtime_quarterly_analysis(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame | None = None,
    dim_dealer: pd.DataFrame | None = None,
    year: int | None = None,
    quarter: int | None = None,
) -> dict:
    """生成季度实时追踪分析。

    自动取当前季度，也可手动指定。
    返回 quarterly_review 的 10 个 section + monthly_tracking + weekly_tracking + quarter_progress。
    """
    df = prepare(merged)

    # 自动确定当前季度
    now = datetime.now()
    if year is None:
        year = now.year
    if quarter is None:
        quarter = (now.month - 1) // 3 + 1

    # 季度日期范围
    q_start_month = (quarter - 1) * 3 + 1
    q_start = pd.Timestamp(year=year, month=q_start_month, day=1)
    q_end = q_start + pd.DateOffset(months=3)
    q_label = f"{year} Q{quarter}"

    # 调用季度复盘引擎获取 10 个 section
    review = quarterly_review(merged, year=year, quarter=quarter)
    if isinstance(review, dict) and review.get("error"):
        return review

    # ── 月度进度追踪 ─────────────────────────
    monthly_tracking = _monthly_tracking(df, year, quarter, q_start, q_end)

    # ── 周度节奏追踪 ─────────────────────────
    weekly_tracking = _weekly_tracking(df, year, quarter, q_start, q_end)

    # ── 季度进度指标 ─────────────────────────
    quarter_progress = _quarter_progress(df, year, quarter, q_start, q_end, now)

    # ── 上季度对比 ───────────────────────────
    prev_quarter = quarter - 1 if quarter > 1 else 4
    prev_year = year if quarter > 1 else year - 1
    prev_review = quarterly_review(merged, year=prev_year, quarter=prev_quarter)
    prev_comparison = _prev_comparison(review, prev_review) if not prev_review.get("error") else {}

    return {
        "label": q_label,
        "year": year,
        "quarter": quarter,
        "is_realtime": True,
        "quarter_progress": quarter_progress,
        "monthly_tracking": monthly_tracking,
        "weekly_tracking": weekly_tracking,
        "prev_comparison": prev_comparison,
        # 透传 quarterly_review 的 10 个 section
        "section_1_overview": review.get("section_1_overview", {}),
        "section_2_trend": review.get("section_2_trend", {}),
        "section_3_funnel": review.get("section_3_funnel", {}),
        "section_4_type": review.get("section_4_type", {}),
        "section_5_products": review.get("section_5_products", {}),
        "section_6_dealers": review.get("section_6_dealers", {}),
        "section_7_stores": review.get("section_7_stores", {}),
        "section_8_regions": review.get("section_8_regions", {}),
        "section_9_comparisons": review.get("section_9_comparisons", {}),
        "section_10_conclusion": review.get("section_10_conclusion", {}),
    }


def _monthly_tracking(df: pd.DataFrame, year: int, quarter: int,
                      q_start: pd.Timestamp, q_end: pd.Timestamp) -> list:
    """季度内每月进度追踪。"""
    months = []
    for i in range(3):
        m = (quarter - 1) * 3 + 1 + i
        ms = pd.Timestamp(year=year, month=m, day=1)
        me = ms + pd.DateOffset(months=1)
        m_df = df[(df["activity_date"] >= ms) & (df["activity_date"] < me)].copy()

        is_current = ms.month == datetime.now().month and ms.year == datetime.now().year
        is_future = ms > pd.Timestamp.now()

        months.append({
            "month": m,
            "month_name": f"{m}月",
            "is_current": is_current,
            "is_future": is_future,
            "activity_count": int(len(m_df)),
            "total_sales": float(m_df["sales"].sum()),
            "total_participants": int(m_df["participants"].sum()),
            "total_wechat": int(m_df["wechat"].sum()),
            "total_hosts": int(m_df["hosts"].sum()),
            "stores_covered": int(m_df["store_name"].nunique()),
            "dealers_active": int(m_df["dealer"].nunique()) if "dealer" in m_df.columns else 0,
            "health_score": compute_health_score(m_df),
        })
    return months


def _weekly_tracking(df: pd.DataFrame, year: int, quarter: int,
                     q_start: pd.Timestamp, q_end: pd.Timestamp) -> list:
    """季度内每周节奏追踪（零售周：周六到周五）。"""
    weeks = []
    now = pd.Timestamp.now()

    # 从季度第一个周六开始
    first_saturday = q_start
    while first_saturday.weekday() != 5:  # 5 = Saturday
        first_saturday += pd.Timedelta(days=1)

    current = first_saturday
    week_idx = 1
    while current < q_end:
        week_end = current + pd.Timedelta(days=6)
        w_df = df[(df["activity_date"] >= current) & (df["activity_date"] <= week_end)].copy()

        is_current = current <= now <= week_end
        is_past = week_end < now

        weeks.append({
            "week_idx": week_idx,
            "week_start": current.strftime("%m/%d"),
            "week_end": week_end.strftime("%m/%d"),
            "is_current": is_current,
            "is_past": is_past,
            "activity_count": int(len(w_df)),
            "total_sales": float(w_df["sales"].sum()),
            "total_participants": int(w_df["participants"].sum()),
            "total_wechat": int(w_df["wechat"].sum()),
            "total_hosts": int(w_df["hosts"].sum()),
            "stores_covered": int(w_df["store_name"].nunique()),
            "health_score": compute_health_score(w_df),
        })

        current = week_end + pd.Timedelta(days=1)
        week_idx += 1

    return weeks


def _quarter_progress(df: pd.DataFrame, year: int, quarter: int,
                      q_start: pd.Timestamp, q_end: pd.Timestamp,
                      now: datetime) -> dict:
    """季度进度指标。"""
    total_days = (q_end - q_start).days
    elapsed_days = min((now - q_start.to_pydatetime()).days, total_days)
    remaining_days = max(total_days - elapsed_days, 0)
    progress_pct = round(elapsed_days / total_days * 100, 1) if total_days else 0

    # 当前季度数据
    q_df = df[(df["activity_date"] >= q_start) & (df["activity_date"] < q_end)]
    now_ts = pd.Timestamp(now)
    completed_df = q_df[q_df["activity_date"] <= now_ts]

    # 季度总目标估算（基于上季度 + 10%增长）
    total_activities = int(len(completed_df))
    # 预估全季度 = 已完成 / 进度百分比
    projected_activities = int(total_activities / (progress_pct / 100)) if progress_pct > 0 else 0

    return {
        "total_days": total_days,
        "elapsed_days": elapsed_days,
        "remaining_days": remaining_days,
        "progress_pct": progress_pct,
        "elapsed_weeks": elapsed_days // 7,
        "total_weeks": total_days // 7,
        "current_activities": total_activities,
        "projected_activities": projected_activities,
        "current_sales": float(completed_df["sales"].sum()),
        "current_participants": int(completed_df["participants"].sum()),
        "current_wechat": int(completed_df["wechat"].sum()),
        "current_hosts": int(completed_df["hosts"].sum()),
        "current_stores": int(completed_df["store_name"].nunique()),
        "current_dealers": int(completed_df["dealer"].nunique()) if "dealer" in completed_df.columns else 0,
        "health_score": compute_health_score(completed_df),
    }


def _prev_comparison(curr: dict, prev: dict) -> dict:
    """与上季度对比。"""
    curr_k = (curr.get("section_1_overview", {}) or {}).get("kpis", {})
    prev_k = (prev.get("section_1_overview", {}) or {}).get("kpis", {})

    def _diff(c, p):
        if p and p > 0:
            return round((c - p) / p * 100, 1)
        return None

    return {
        "prev_label": prev.get("label", ""),
        "activities_diff": _diff(curr_k.get("total_activities", 0), prev_k.get("total_activities", 0)),
        "sales_diff": _diff(curr_k.get("total_sales", 0), prev_k.get("total_sales", 0)),
        "participants_diff": _diff(curr_k.get("total_participants", 0), prev_k.get("total_participants", 0)),
        "wechat_diff": _diff(curr_k.get("total_wechat", 0), prev_k.get("total_wechat", 0)),
        "hosts_diff": _diff(curr_k.get("total_hosts", 0), prev_k.get("total_hosts", 0)),
    }
