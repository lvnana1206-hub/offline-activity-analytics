"""每日经营分析 (Daily Analysis)。

运营每天使用，回答：今天发生了什么？哪些需要关注？下一步怎么办？
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import timedelta

from .common import prepare, safe_num, finding, rec, today_str


def daily_analysis(merged: pd.DataFrame, target_date: str | None = None) -> dict:
    """生成每日经营分析。

    Args:
        merged: merged_activity_store 宽表
        target_date: 目标日期字符串，None 则取数据最新日期
    Returns: 包含 data / findings / recommendations 的字典
    """
    df = prepare(merged)
    today = pd.Timestamp(target_date) if target_date else pd.Timestamp(today_str(df))
    label = today.strftime("%Y-%m-%d")

    today_df = df[df["activity_date"].dt.normalize() == today.normalize()]

    # ── 经营数据 ─────────────────────────────
    today_activities = today_df[["record_id", "activity_desc", "activity_type",
                                 "activity_status", "store_name", "dealer",
                                 "sales", "participants", "wechat", "hosts",
                                 "activity_date"]].copy()
    today_activities["activity_date"] = today_activities["activity_date"].dt.strftime("%Y-%m-%d")

    data = {
        "date": label,
        "today_count": int(len(today_df)),
        "today_sales": float(safe_num(today_df["sales"]).sum()),
        "today_participants": int(safe_num(today_df["participants"]).sum()),
        "today_wechat": int(safe_num(today_df["wechat"]).sum()),
        "today_hosts": int(safe_num(today_df["hosts"]).sum()),
        "today_activities": today_activities.head(50).to_dict("records"),
        "today_by_type": _by_type(today_df),
        "today_by_region": _by_region(today_df),
    }

    # ── 待复盘活动：已完成但无销售/无参与记录 ──
    pending_review = df[
        df["is_completed"]
        & (df["activity_date"] <= today)
        & ((df["sales"] <= 0) | (df["participants"] <= 0))
    ].copy()
    pending_review = pending_review.sort_values("activity_date", ascending=False).head(20)
    data["pending_review"] = pending_review[
        ["record_id", "activity_desc", "activity_type", "store_name",
         "dealer", "activity_date", "sales", "participants", "wechat"]
    ].to_dict("records")
    data["pending_review_count"] = int(len(df[
        df["is_completed"] & (df["activity_date"] <= today)
        & ((df["sales"] <= 0) | (df["participants"] <= 0))
    ]))

    # ── 异常活动：销售额异常标记 / 零参与已完成 / 高费用零产出 ──
    anomaly = df[
        df["activity_date"].dt.normalize() == today.normalize()
    ]
    anomaly_mask = (
        (anomaly["sales_anomaly"] == True)  # noqa: E712
        | ((anomaly["is_completed"]) & (anomaly["participants"] <= 0))
    )
    anomaly_today = anomaly[anomaly_mask]
    data["anomaly_activities"] = anomaly_today[
        ["record_id", "activity_desc", "activity_type", "store_name",
         "sales", "participants", "anomaly_reason"]
    ].head(20).to_dict("records")
    data["anomaly_count"] = int(len(anomaly_today))

    # ── 连续无活动门店：30 天内无活动 ──────
    recent_cutoff = today - timedelta(days=30)
    recent_active = df[df["activity_date"] >= recent_cutoff]["store_name"].unique()
    all_stores = df[df["has_store_dim"]]["matched_store_name"].dropna().unique()
    inactive_stores = sorted(set(all_stores) - set(recent_active))
    data["inactive_store_count"] = int(len(inactive_stores))
    data["inactive_stores"] = inactive_stores[:30]

    # ── 经营结论（发现/原因/影响/建议）──────
    findings = []
    if len(today_df) == 0:
        findings.append(finding(
            f"{label} 无新增活动记录",
            "今日活动总池未提报新活动，或数据尚未同步",
            "当日无经营动作，可能影响月度活动节奏",
            "确认区域经理是否已安排今日活动，必要时督促提报",
            severity="high",
        ))
    else:
        avg_sales = data["today_sales"] / max(len(today_df), 1)
        findings.append(finding(
            f"今日新增 {len(today_df)} 场活动，销售额 {data['today_sales']:.0f} 元，场均 {avg_sales:.0f} 元",
            "活动提报节奏正常" if avg_sales > 0 else "今日活动尚未产生销售",
            "直接影响当月经营达成进度",
            "关注高场次低销售区域，推动复盘转化",
            severity="medium",
        ))

    if data["pending_review_count"] > 0:
        findings.append(finding(
            f"{data['pending_review_count']} 场已完成活动待复盘（无销售/无参与记录）",
            "店长未及时录入销售或参与数据，复盘流程未闭环",
            "导致真实经营成效无法量化，影响月度评分准确性",
            "建立 7 天复盘闭环制度，区域经理每日跟进未复盘活动",
            severity="high",
        ))

    if data["anomaly_count"] > 0:
        findings.append(finding(
            f"今日 {data['anomaly_count']} 场异常活动",
            "销售异常标记或零参与已完成，数据质量存疑",
            "异常活动可能虚增或漏报经营数据",
            "逐一核实异常活动，修正数据后归档",
            severity="high",
        ))

    if data["inactive_store_count"] > 0:
        findings.append(finding(
            f"{data['inactive_store_count']} 家门店连续 30 天以上无活动",
            "门店经营停滞或活动提报缺失",
            "覆盖盲区扩大，影响区域经营达成",
            "省区负责人推动无活动门店首场活动落地",
            severity="medium",
        ))

    # ── 经营建议（下一步怎么办）────────────
    recommendations = []
    if data["pending_review_count"] > 0:
        recommendations.append(rec(
            "启动待复盘活动闭环",
            f"今日有 {data['pending_review_count']} 场已完成活动缺销售/参与数据，需在 7 天内完成复盘",
            owner="区域经理+店长", priority=1, timeline="7天内",
        ))
    if data["inactive_store_count"] > 0:
        recommendations.append(rec(
            "推动无活动门店破零",
            f"{data['inactive_store_count']} 家门店超 30 天无活动，按省区分配首场活动指标",
            owner="省区负责人", priority=2, timeline="本周",
        ))
    if len(today_df) > 0:
        recommendations.append(rec(
            "跟进今日活动转化",
            f"今日 {len(today_df)} 场活动，重点跟进销售转化与企微蓄水",
            owner="店长", priority=2, timeline="当日",
        ))
    if not recommendations:
        recommendations.append(rec(
            "维持日常经营节奏",
            "今日无异常项，保持活动提报与复盘闭环",
            owner="运营部", priority=3, timeline="持续",
        ))

    return {
        "label": label,
        "type": "daily",
        "data": data,
        "findings": findings,
        "recommendations": recommendations,
    }


def _by_type(df: pd.DataFrame) -> list:
    if len(df) == 0:
        return []
    g = df.groupby("activity_type").agg(
        count=("record_id", "count"),
        sales=("sales", "sum"),
        participants=("participants", "sum"),
    ).reset_index().sort_values("count", ascending=False)
    return g.to_dict("records")


def _by_region(df: pd.DataFrame) -> list:
    if len(df) == 0:
        return []
    region_col = "dim_province_unit" if "dim_province_unit" in df.columns else "province_unit_final"
    col = region_col if region_col in df.columns else "province"
    if col not in df.columns:
        return []
    g = df.groupby(col).agg(
        count=("record_id", "count"),
        sales=("sales", "sum"),
    ).reset_index().sort_values("count", ascending=False)
    return g.to_dict("records")
