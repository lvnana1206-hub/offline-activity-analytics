"""经营规则引擎：自动发现低活动门店、低效活动、优秀模式、增长机会。

每条发现输出：发现、原因、影响、建议。
"""

from __future__ import annotations
from datetime import datetime
from metrics import activity_metrics, store_metrics, dealer_metrics, product_metrics
from .activity_score import score_activities
from .store_score import score_stores


def _finding(category, title, detail, severity, suggestion):
    return {
        "category": category,
        "title": title,
        "detail": detail,
        "severity": severity,
        "suggestion": suggestion,
    }


def run_rules_engine(business_category: str = "") -> dict:
    """执行全部经营规则，返回发现列表。"""
    findings: list[dict] = []

    # ── R1: 低活动门店 ──
    inactive = store_metrics.inactive_stores(30, business_category)
    if not inactive.empty:
        findings.append(_finding(
            "low_activity_stores",
            f"{len(inactive)} 家门店 30 天无活动",
            "已开业门店连续 30 天以上无活动记录，存在沉睡风险。",
            "high",
            "省区负责人牵头，30 天内推动每家门店至少 1 场活动。",
        ))

    never = store_metrics.never_active_stores(business_category)
    if not never.empty:
        findings.append(_finding(
            "zero_activity_stores",
            f"{len(never)} 家门店从未举办活动",
            "已开业但从未有活动记录，经营覆盖严重不足。",
            "high",
            "运营部制定零活动门店首场活动计划，限期 15 天落地。",
        ))

    # ── R2: 低效率活动 ──
    a_ov = activity_metrics.activity_overview(business_category)
    low_eff = activity_metrics.activity_by_type(business_category)
    if not low_eff.empty and a_ov["valid_activities"] > 0:
        avg_sales = float(low_eff["avg_sales"].mean())
        low_types = low_eff[low_eff["avg_sales"] < avg_sales * 0.5]
        if not low_types.empty:
            names = ", ".join(low_types["activity_type"].tolist())
            findings.append(_finding(
                "low_efficiency_activities",
                f"低效活动类型: {names}",
                f"以下活动类型场均销售低于平均的 50%，投入产出比低。",
                "medium",
                "减少低效活动频次，资源向高效活动倾斜。",
            ))

    # ── R3: 优秀活动模式 ──
    scores = score_activities(business_category)
    if not scores.empty:
        excellent = scores.head(10)
        best_type = excellent["activity_type"].mode()
        if not best_type.empty:
            findings.append(_finding(
                "excellent_pattern",
                f"优秀活动集中在 {best_type.iloc[0]}",
                f"Top10 评分活动中 {best_type.iloc[0]} 占比最高，销售和互动表现突出。",
                "info",
                f"将 {best_type.iloc[0]} 活动模式标准化，向其他门店推广。",
            ))

    # ── R4: 增长机会 ──
    store_scores = score_stores(business_category)
    if not store_scores.empty:
        potential = store_scores[(store_scores["grade"] == "D") & (store_scores["activity_count"] >= 5)]
        if not potential.empty:
            findings.append(_finding(
                "growth_opportunity",
                f"{len(potential)} 家 D 级门店活动量充足但转化弱",
                "活动频次不低但销售转化差，存在提升空间。",
                "medium",
                "运营部针对这些门店做活动质量诊断，优化活动类型和执行。",
            ))

    prod = product_metrics.product_metrics(business_category)
    if not prod.empty:
        low_pen = prod[prod["covered_stores"] < prod["covered_stores"].median()]
        if not low_pen.empty:
            findings.append(_finding(
                "product_penetration_gap",
                f"{len(low_pen)} 个产品线渗透不足",
                "覆盖门店数低于中位数，渠道渗透有提升空间。",
                "medium",
                "扩大低渗透产品的铺货和推广活动。",
            ))

    # ── R5: 完成率问题 ──
    if a_ov["completion_rate_pct"] < 50:
        findings.append(_finding(
            "low_completion_rate",
            f"活动完成率仅 {a_ov['completion_rate_pct']}%",
            f"超过一半的活动未完成闭环，复盘执行不到位。",
            "high",
            "建立活动 7 天闭环制度，区域经理 + 店长联动跟进。",
        ))

    return {
        "findings": findings,
        "finding_count": len(findings),
        "high_severity_count": sum(1 for f in findings if f["severity"] == "high"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
