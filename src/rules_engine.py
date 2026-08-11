"""运营规则中心 (Rules Engine)。

统一定义经营判断规则：
  - 有效活动判定
  - 优秀活动判定
  - 异常活动判定
  - 门店评分规则
  - 代理商评分规则
  - 活动评分规则
  - 区域评分规则

所有规则集中管理，前端和后端共享同一套定义。
规则变更只需修改本文件。
"""

from __future__ import annotations

import pandas as pd
from .config import COMPLETED_STATUSES
import numpy as np


# ── 规则定义 ────────────────────────────────────────────────

RULES = {
    # 活动判定规则
    "effective_activity": {
        "desc": "有效活动：已完成且有实际产出（参与人数>0 或 销售>0）",
        "conditions": {
            "status": "已完成",
            "min_participants": 1,
            "min_sales": 0,
        },
    },
    "excellent_activity": {
        "desc": "优秀活动：有效活动且销售额达到 Top 10% 分位，或企微添加≥10",
        "conditions": {
            "status": "已完成",
            "min_participants": 1,
            "sales_percentile": 90,
            "alt_min_wechat": 10,
        },
    },
    "anomaly_activity": {
        "desc": "异常活动：销售额被标记异常、零参与已完成、高费用零产出",
        "conditions": {
            "sales_anomaly_flag": True,
            "zero_participant_completed": True,
            "high_cost_zero_sales_threshold": 1000,
        },
    },
    "inactive_store_days": {
        "desc": "风险门店：连续超过 30 天无活动",
        "conditions": {"days": 30},
    },
    "low_completion_threshold": {
        "desc": "完成率低：5场以上活动完成率低于 5%",
        "conditions": {"min_activities": 5, "max_rate": 0.05},
    },
    "single_type_min_activities": {
        "desc": "类型单一：5场以上活动全部为同一类型",
        "conditions": {"min_activities": 5},
    },
    "low_dealer_coverage": {
        "desc": "代理商覆盖率低：10家门店以上但覆盖率低于 30%",
        "conditions": {"min_stores": 10, "max_coverage": 0.3},
    },
    # 评分规则
    "scoring": {
        "desc": "四维评分体系（0-100分），加权计算",
        "weights": {
            "activity_volume": 0.20,      # 活动量
            "completion_quality": 0.25,    # 完成质量
            "sales_performance": 0.35,    # 销售表现
            "engagement": 0.20,           # 互动参与
        },
        "grade_thresholds": {
            "A": 80,   # A 级：≥80
            "B": 65,   # B 级：65-79
            "C": 50,   # C 级：50-64
            "D": 0,    # D 级：<50
        },
    },
}


# ── 规则引擎 ────────────────────────────────────────────────

class RulesEngine:
    """运营规则引擎。基于 RULES 定义执行判定。"""

    def __init__(self):
        self.rules = RULES

    def get_rules(self) -> dict:
        """返回全部规则定义。"""
        return self.rules

    def get_rule(self, name: str) -> dict:
        return self.rules.get(name, {})

    # ── 活动判定 ────────────────────────────────────────────

    def classify_activity(self, row) -> str:
        """对单条活动记录分类：excellent / effective / anomaly / normal / pending。
        
        返回值含义：
          excellent  - 优秀活动
          effective  - 有效活动（已完成有产出但不优秀）
          anomaly    - 异常活动
          normal     - 普通活动（非已完成状态）
          pending    - 待评估
        """
        status = row.get("activity_status", "")
        sales = _safe_val(row.get("sales_clean"))
        participants = _safe_val(row.get("participants"))
        wechat = _safe_val(row.get("wechat_adds"))
        anomaly_flag = row.get("sales_anomaly")
        cost = _safe_val(row.get("activity_cost"))

        # 异常检测（优先级最高）
        is_anomaly = False
        if anomaly_flag is True or str(anomaly_flag).lower() == "true":
            is_anomaly = True
        if status in COMPLETED_STATUSES and participants == 0:
            is_anomaly = True
        if status in COMPLETED_STATUSES and cost > 1000 and sales == 0:
            is_anomaly = True
        if is_anomaly:
            return "anomaly"

        # 非已完成 -> normal
        if status != "已完成":
            return "pending" if status == "待评估" else "normal"

        # 有效活动判定
        if participants < 1 and sales <= 0:
            return "normal"

        # 优秀活动判定：销售额达到 90 分位 或 企微≥10
        # 注意：分位阈值在 batch 方法中计算，这里用绝对阈值
        if sales >= 10000 or wechat >= 10:
            return "excellent"

        return "effective"

    def classify_activities_batch(self, merged: pd.DataFrame) -> pd.DataFrame:
        """批量分类活动，计算优秀活动的分位阈值。"""
        df = merged.copy()
        df["sales"] = pd.to_numeric(df["sales_clean"], errors="coerce").fillna(0)
        df["participants"] = pd.to_numeric(df["participants"], errors="coerce").fillna(0)
        df["wechat"] = pd.to_numeric(df["wechat_adds"], errors="coerce").fillna(0)
        df["cost"] = pd.to_numeric(df["activity_cost"], errors="coerce").fillna(0)

        # 计算优秀活动的销售额分位阈值
        completed = df[df["activity_status"].isin(COMPLETED_STATUSES)]
        if len(completed) > 0:
            sales_p90 = completed["sales"].quantile(0.90)
        else:
            sales_p90 = 10000

        # 逐行分类
        def _classify(row):
            status = row["activity_status"]
            sales = row["sales"]
            participants = row["participants"]
            wechat = row["wechat"]
            cost = row["cost"]
            anomaly_flag = row.get("sales_anomaly")

            # 异常
            if anomaly_flag is True or str(anomaly_flag).lower() == "true":
                return "anomaly"
            if status in COMPLETED_STATUSES and participants == 0:
                return "anomaly"
            if status in COMPLETED_STATUSES and cost > 1000 and sales == 0:
                return "anomaly"

            # 非已完成
            if status != "已完成":
                return "pending" if status == "待评估" else "normal"

            # 有效但不够优秀
            if participants < 1 and sales <= 0:
                return "normal"

            # 优秀
            if sales >= sales_p90 or wechat >= 10:
                return "excellent"

            return "effective"

        df["activity_class"] = df.apply(_classify, axis=1)
        return df

    # ── 评分规则 ────────────────────────────────────────────

    def get_scoring_weights(self) -> dict:
        return self.rules["scoring"]["weights"]

    def get_grade(self, score: float) -> str:
        """根据分数返回等级。"""
        thresholds = self.rules["scoring"]["grade_thresholds"]
        if score >= thresholds["A"]:
            return "A"
        elif score >= thresholds["B"]:
            return "B"
        elif score >= thresholds["C"]:
            return "C"
        else:
            return "D"

    def get_grade_color(self, grade: str) -> str:
        """等级对应的颜色。"""
        return {"A": "#10b981", "B": "#0ea5e9", "C": "#f59e0b", "D": "#ef4444"}.get(grade, "#94a3b8")


def _safe_val(v) -> float:
    if v is None:
        return 0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0


# 全局单例
_engine = RulesEngine()

def get_engine() -> RulesEngine:
    return _engine
