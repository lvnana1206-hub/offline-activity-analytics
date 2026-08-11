"""每周经营分析 (Weekly Analysis)。

自然周分析，输出本周经营总结与下周行动建议。
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import timedelta

from .common import prepare, safe_num, finding, rec, today_str
from .common import (
    zero_activity_stores, zero_activity_dealers,
    low_conversion_stores, low_conversion_dealers,
    low_wechat_stores, low_wechat_dealers,
    activity_count_stores, activity_count_dealers,
)
from .common import compute_health_score

def _chg_text(chg):
    """环比变化转中文描述。"""
    if chg is None:
        return "持平"
    if chg > 0:
        return "环比增长" + str(round(chg * 100)) + "%"
    if chg < 0:
        return "环比下降" + str(round(-chg * 100)) + "%"
    return "持平"


def weekly_analysis(merged: pd.DataFrame, target_date: str | None = None,
                    dim_store: pd.DataFrame | None = None,
                    dim_dealer: pd.DataFrame | None = None) -> dict:
    """生成本周（自然周）经营分析。

    Args:
        merged: merged_activity_store 宽表
        target_date: 目标日期，None 则取数据最新日期所在周
    """
    df = prepare(merged)
    ref = pd.Timestamp(target_date) if target_date else pd.Timestamp(today_str(df))
    ref = pd.Timestamp(ref)
    # 自然周：周一为起始
    week_start = ref - pd.Timedelta(days=ref.weekday())
    week_start = week_start.normalize()
    week_end = week_start + pd.Timedelta(days=7)
    label = f"{week_start.strftime('%m-%d')} ~ {(week_end - pd.Timedelta(days=1)).strftime('%m-%d')}"

    week_df = df[(df["activity_date"] >= week_start) & (df["activity_date"] < week_end)].copy()

    # 上一周对比
    prev_start = week_start - pd.Timedelta(days=7)
    prev_end = week_start
    prev_df = df[(df["activity_date"] >= prev_start) & (df["activity_date"] < prev_end)].copy()

    # ── 经营数据 ─────────────────────────────
    data = {
        "week_label": label,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": (week_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "activity_count": int(len(week_df)),
        "total_sales": float(week_df["sales"].sum()),
        "total_participants": int(week_df["participants"].sum()),
        "total_wechat": int(week_df["wechat"].sum()),
        "total_hosts": int(week_df["hosts"].sum()),
        "stores_covered": int(week_df["store_name"].nunique()),
        "dealers_covered": int(week_df["dealer_final"].nunique()) if "dealer_final" in week_df.columns else int(week_df["dealer"].nunique()),
        "completed_count": int(week_df["is_completed"].sum()),
        "health_score": compute_health_score(week_df),
    }

    def _stats(d):
        return {
            "count": int(len(d)),
            "sales": float(d["sales"].sum()),
            "participants": int(d["participants"].sum()),
            "stores": int(d["store_name"].nunique()),
        }
    cur = _stats(week_df)
    prev = _stats(prev_df)
    changes = {}
    for k in cur:
        changes[k] = (cur[k] - prev[k]) / prev[k] if prev[k] else None
    data["prev_stats"] = prev
    data["changes"] = changes

    dealer_col = "dealer_final" if "dealer_final" in week_df.columns else "dealer"
    data["dealer_perf"] = _dealer_perf(week_df, dealer_col)
    data["excellent_activities"] = _excellent(week_df)
    anomaly = week_df[
        (week_df["sales_anomaly"] == True)  # noqa: E712
        | ((week_df["is_completed"]) & (week_df["participants"] <= 0))
        | ((week_df["is_completed"]) & (week_df["sales"] <= 0))
    ].sort_values("sales", ascending=False)
    data["anomaly_activities"] = anomaly[
        ["record_id", "activity_desc", "activity_type", "store_name",
         "sales", "participants", "anomaly_reason"]
    ].head(20).to_dict("records")
    risk = week_df[week_df["sales"] <= 0].groupby("store_name").agg(
        count=("record_id", "count"),
    ).reset_index().sort_values("count", ascending=False)
    data["risk_stores"] = risk.head(20).to_dict("records")
    data["risk_store_count"] = int(len(risk))

    # ── 活动量与转化分析 ─────────────────────
    data["activity_count_store"] = activity_count_stores(week_df)
    data["activity_count_dealer"] = activity_count_dealers(week_df, dealer_col)
    data["zero_activity_stores"] = zero_activity_stores(week_df, dim_store) if dim_store is not None else []
    data["zero_activity_dealers"] = zero_activity_dealers(week_df, dim_dealer, dealer_col) if dim_dealer is not None else []
    data["low_conversion_stores"] = low_conversion_stores(week_df)
    data["low_conversion_dealers"] = low_conversion_dealers(week_df, dealer_col)
    data["low_wechat_stores"] = low_wechat_stores(week_df)
    data["low_wechat_dealers"] = low_wechat_dealers(week_df, dealer_col)

    # ── 经营结论 ─────────────────────────────
    findings = []
    if cur["count"] == 0:
        findings.append(finding(
            "本周无活动记录",
            "活动提报停滞或数据未同步",
            "本周经营节奏中断，影响月度达成",
            "立即排查原因，督促各区域恢复活动提报",
            severity="high",
        ))
    else:
        chg_txt = _chg_text(changes["count"])
        findings.append(finding(
            f"本周 {cur['count']} 场活动，销售额 {cur['sales']:.0f} 元，覆盖 {cur['stores']} 家门店，{chg_txt}",
            "本周经营节奏" + ("正常" if cur["count"] >= prev["count"] else "放缓"),
            "直接影响月度经营达成进度",
            "保持活动节奏，对下降区域专项跟进",
            severity="medium",
        ))

    avg_sales = cur["sales"] / cur["count"] if cur["count"] else 0
    findings.append(finding(
        f"本周场均销售额 {avg_sales:.0f} 元",
        "场均销售反映活动转化质量",
        "场均偏低说明活动转化能力不足",
        "对标优秀活动打法，提升单场转化",
        severity="low",
    ))

    if data["risk_store_count"] > 0:
        findings.append(finding(
            f"{data['risk_store_count']} 家门店本周活动零销售",
            "活动执行流于形式或销售未录入",
            "消耗资源无产出，拉低区域评分",
            "风险门店逐一复盘，必要时暂停无效活动",
            severity="medium",
        ))

    # ── 经营建议 ─────────────────────────────
    recommendations = []
    summary_text = f"本周 {cur['count']} 场活动，销售 {cur['sales']:.0f} 元，参与 {cur['participants']} 人。"
    cnt_chg = changes["count"]
    if cnt_chg is not None and cnt_chg < 0:
        summary_text += "环比下降，需加强节奏。"
    else:
        summary_text += "环比稳定。"
    recommendations.append(rec(
        "本周经营总结",
        summary_text,
        owner="运营部", priority=1, timeline="本周",
    ))
    if data["excellent_activities"]:
        top = data["excellent_activities"][0]
        recommendations.append(rec(
            "复制本周优秀活动打法",
            f"标杆活动：{str(top.get('activity_desc',''))[:30]}，销售 {top.get('sales',0):.0f} 元，提炼模式推广",
            owner="运营部", priority=2, timeline="下周",
        ))
    if data["risk_store_count"] > 0:
        recommendations.append(rec(
            "本周风险门店整改",
            f"{data['risk_store_count']} 家门店零销售，省区负责人本周内完成整改或暂停",
            owner="省区负责人", priority=1, timeline="本周",
        ))
    recommendations.append(rec(
        "下周行动规划",
        "基于本周达成缺口，分配下周活动场次与销售目标，重点覆盖无活动门店",
        owner="运营部", priority=2, timeline="下周",
    ))

    return {
        "label": label,
        "type": "weekly",
        "data": data,
        "findings": findings,
        "recommendations": recommendations,
    }


def _dealer_perf(df: pd.DataFrame, col: str) -> list:
    if len(df) == 0 or col not in df.columns:
        return []
    g = df.groupby(col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index().sort_values("total_sales", ascending=False).head(10)
    g = g.rename(columns={col: "dealer"})
    return g.to_dict("records")


def _excellent(df: pd.DataFrame) -> list:
    if len(df) == 0:
        return []
    e = df[df["sales"] > 0].sort_values("sales", ascending=False).head(10)
    return e[["record_id", "activity_desc", "activity_type", "store_name",
              "sales", "participants", "wechat", "activity_date"]].to_dict("records")
