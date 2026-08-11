"""统一指标中心 (Metrics Center)。

所有页面、所有引擎调用指标的唯一入口。
不直接计算，而是委托 metrics.py 并做标准化封装：
  - 统一命名
  - 统一数据类型
  - 缓存管理
  - 指标元信息（名称、单位、说明）

这样前端永远不需要自己算指标，只需要调 /api/metrics_center/<name>。
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from .metrics import compute_all_metrics
from .diagnostics import run_full_diagnosis
from .data_model import build_all_models
from .feishu_loader import load_activity_from_feishu
from .filter_engine import filter_merged, get_filter_options
from .scoring import compute_all_scores
from .insight_engine import get_engine_insight
from .analysis.common import compute_health_score, safe_num
from .channel_metrics import (
    channel_comparison, drone_comparison, brand_ranking,
    conversion_funnel, product_type_cross, type_month_cross,
    product_monthly, monthly_multi_trend,
)


# ── 指标元信息 ──────────────────────────────────────────────

METRIC_CATALOG = {
    # 活动指标
    "total_activities": {"name": "活动总数", "unit": "场", "category": "activity", "desc": "全量活动记录数"},
    "completed_activities": {"name": "已完成活动", "unit": "场", "category": "activity", "desc": "状态为已完成的活动"},
    "completion_rate": {"name": "活动完成率", "unit": "%", "category": "activity", "desc": "已完成/总数"},
    "total_sales": {"name": "总销售额", "unit": "元", "category": "activity", "desc": "清洗后销售总额"},
    "avg_sales_per_activity": {"name": "场均销售额", "unit": "元", "category": "activity", "desc": "已完成活动场均销售"},
    "total_participants": {"name": "总参与人数", "unit": "人", "category": "activity", "desc": "累计参与"},
    "total_wechat_adds": {"name": "企微添加总数", "unit": "人", "category": "activity", "desc": "累计企微"},
    "avg_conversion_rate": {"name": "平均成交率", "unit": "%", "category": "activity", "desc": "当场成交率均值"},
    "wechat_add_rate": {"name": "企微加微率", "unit": "%", "category": "activity", "desc": "企微新增/参与人数"},
    "host_conversion_rate": {"name": "主机转化率", "unit": "%", "category": "activity", "desc": "转化主机/参与人数"},
    "sales_per_participant": {"name": "人均销售额", "unit": "元", "category": "activity", "desc": "销售额/参与人数"},
    "sales_per_host": {"name": "单台销售额", "unit": "元", "category": "activity", "desc": "销售额/转化主机数"},
    "wechat_per_activity": {"name": "场均企微", "unit": "人", "category": "activity", "desc": "企微新增/活动场次"},
    "participants_per_activity": {"name": "场均参与", "unit": "人", "category": "activity", "desc": "参与人数/活动场次"},
    "hosts_per_activity": {"name": "场均主机", "unit": "台", "category": "activity", "desc": "转化主机/活动场次"},
    # 门店指标
    "active_stores": {"name": "有活动门店", "unit": "家", "category": "store", "desc": "至少有1场活动的门店"},
    "total_stores": {"name": "门店总数", "unit": "家", "category": "store", "desc": "门店维度表总数"},
    "store_coverage_rate": {"name": "门店覆盖率", "unit": "%", "category": "store", "desc": "有活动/总门店"},
    "inactive_store_count": {"name": "无活动门店", "unit": "家", "category": "store", "desc": "从未或超30天无活动"},
    # 代理商指标
    "total_dealers": {"name": "代理商总数", "unit": "家", "category": "dealer", "desc": "覆盖代理商"},
    "avg_dealer_coverage": {"name": "代理商平均覆盖率", "unit": "%", "category": "dealer", "desc": "门店覆盖率均值"},
    # 产品指标
    "top_product": {"name": "销量最高产品", "unit": "", "category": "product", "desc": "活动中销量最高的产品系列"},
    # 区域指标
    "top_region": {"name": "活动量最高区域", "unit": "", "category": "region", "desc": "活动数最多的省区单元"},
}


class MetricsCenter:
    """统一指标中心。单例模式，启动时初始化，所有模块共享。"""

    def __init__(self):
        self._models = None
        self._metrics = None
        self._diagnosis = None
        self._use_feishu = False

    @staticmethod
    def _health_score(merged: pd.DataFrame) -> float:
        """健康度 = 有效活动(蓄水率>5%或转化主机>0) / 总活动 * 100。"""
        if len(merged) == 0:
            return 0.0
        wechat = safe_num(merged.get("wechat_adds", merged.get("wechat", 0)))
        participants = safe_num(merged.get("participants", 0))
        hosts = safe_num(merged.get("converted_hosts", merged.get("hosts", 0)))
        rate = np.where(participants > 0, wechat / participants, 0.0)
        valid = (rate > 0.05) | (hosts > 0)
        return round(float(valid.sum()) / len(merged) * 100, 1)

    def initialize(self, use_feishu: bool = False):
        """构建数据模型并计算全部指标。"""
        if self._models is not None:
            return
        self._use_feishu = use_feishu
        if use_feishu:
            activities = load_activity_from_feishu()
            self._models = build_all_models(activities=activities)
        else:
            self._models = build_all_models()
        self._metrics = compute_all_metrics(
            self._models["merged_activity_store"],
            self._models["dim_store"],
            self._models["dim_dealer"],
        )
        self._diagnosis = run_full_diagnosis(
            self._models["merged_activity_store"],
            self._models["dim_store"],
            self._models["dim_dealer"],
        )

    @property
    def models(self):
        self.initialize()
        return self._models

    @property
    def metrics(self):
        self.initialize()
        return self._metrics

    @property
    def diagnosis(self):
        self.initialize()
        return self._diagnosis

    @property
    def merged(self):
        return self.models["merged_activity_store"]

    @property
    def dim_store(self):
        return self.models["dim_store"]

    @property
    def dim_dealer(self):
        return self.models["dim_dealer"]

    # ── 指标获取 ────────────────────────────────────────────

    def get_overview(self) -> dict:
        """获取全局概览指标。"""
        ov = dict(self.metrics["activity_overview"])
        ov["total_stores"] = len(self.dim_store)
        ov["active_stores"] = int(self.merged["store_name"].nunique())
        ov["total_dealers"] = len(self.dim_dealer)
        ov["store_coverage_rate"] = ov["active_stores"] / ov["total_stores"] if ov["total_stores"] else 0
        # 健康度: 有效活动(蓄水率>5%或转化主机) / 总活动 * 100
        ov["health_score"] = self._health_score(self.merged)
        # 代理商平均覆盖率
        dm = self.metrics["dealer_metrics"]
        ov["avg_dealer_coverage"] = float(dm["store_coverage_rate"].mean()) if "store_coverage_rate" in dm.columns else 0
        # 无活动门店
        inactive = self.diagnosis.get("inactive_stores", [])
        ov["inactive_store_count"] = len(inactive) if isinstance(inactive, list) else 0
        # Top 产品和区域
        pm = self.metrics["product_metrics"]
        if len(pm) > 0:
            ov["top_product"] = pm.iloc[0]["product"]
        rm = self.metrics["region_metrics"]
        if len(rm) > 0:
            ov["top_region"] = rm.iloc[0]["region"]
        return ov

    def get_catalog(self) -> list:
        """返回指标目录。"""
        return [{"key": k, **v} for k, v in METRIC_CATALOG.items()]

    def get_metric(self, key: str):
        """获取单个指标值。"""
        overview = self.get_overview()
        if key in overview:
            return overview[key]
        return None

    def get_metrics_by_category(self, category: str) -> dict:
        """按类别获取指标。"""
        overview = self.get_overview()
        keys = [k for k, v in METRIC_CATALOG.items() if v["category"] == category]
        return {k: overview.get(k) for k in keys if k in overview}

    def get_filtered_snapshot(self, **filters) -> dict:
        """在筛选后的 merged 上重算全部指标/评分/洞察，返回完整快照。

        filters 关键字参数: store_type, dealer_type, period, date_from,
        date_to, period_value。空值表示不筛选。
        """
        import numpy as _np
        merged = self.merged
        dim_store = self.dim_store
        dim_dealer = self.dim_dealer

        fmerged = filter_merged(merged, dim_dealer, **filters)
        if len(fmerged) == 0:
            return {"empty": True, "count": 0}

        fm = compute_all_metrics(fmerged, dim_store, dim_dealer)
        scores = compute_all_scores(fmerged, dim_store, dim_dealer)
        insights = get_engine_insight().generate_insights(
            fmerged, dim_store, dim_dealer, scores
        )

        # overview
        ov = dict(fm["activity_overview"])
        ov["total_stores"] = len(dim_store)
        ov["active_stores"] = int(fmerged["store_name"].nunique())
        ov["total_dealers"] = len(dim_dealer)
        ov["store_coverage_rate"] = (
            ov["active_stores"] / ov["total_stores"] if ov["total_stores"] else 0
        )
        ov["health_score"] = self._health_score(fmerged)
        ov["avg_dealer_coverage"] = float(
            fm["dealer_metrics"]["store_coverage_rate"].mean()
        ) if "store_coverage_rate" in fm["dealer_metrics"].columns else 0

        # 优秀活动 Top (按销售额)
        excellent = fmerged[fmerged["sales_clean"] > 0].nlargest(50, "sales_clean")
        excellent_records = excellent[[
            "activity_desc", "store_name", "activity_type", "activity_date",
            "sales_clean", "participants", "wechat_adds",
        ]].copy()
        excellent_records["rank"] = range(1, len(excellent_records) + 1)
        excellent_records = excellent_records.rename(columns={"sales_clean": "sales"})
        # 补 province_unit
        if "province_unit_final" in fmerged.columns:
            excellent_records = excellent_records.merge(
                fmerged[["activity_desc", "store_name", "province_unit_final"]].drop_duplicates("activity_desc"),
                on=["activity_desc", "store_name"], how="left"
            )
            excellent_records["province_unit"] = excellent_records["province_unit_final"]

        def _df_records(df):
            df = df.replace([_np.inf, -_np.inf], None)
            records = df.to_dict("records")
            for rec in records:
                for k, v in rec.items():
                    if isinstance(v, float) and v != v:
                        rec[k] = None
            return records

        return {
            "empty": False,
            "count": len(fmerged),
            "overview": ov,
            "activity_by_type": _df_records(fm["activity_by_type"]),
            "activity_trend": _df_records(fm["activity_monthly_trend"]),
            "dealers": _df_records(fm["dealer_metrics"]),
            "stores": _df_records(fm["store_metrics"]),
            "stores_total": len(fm["store_metrics"]),
            "products": _df_records(fm["product_metrics"]),
            "regions": _df_records(fm["region_metrics"]),
            "provinces": _df_records(fm["province_metrics"]),
            "scores_stores": _df_records(scores["store_scores"]) if "store_scores" in scores else [],
            "scores_dealers": _df_records(scores["dealer_scores"]) if "dealer_scores" in scores else [],
            "scores_regions": _df_records(scores["region_scores"]) if "region_scores" in scores else [],
            "insights": insights,
            "insights_summary": insights.get("summary", []),
            "insights_recommendations": insights.get("recommendations", []),
            "excellent": _df_records(excellent_records),
            "funnel": conversion_funnel(fmerged),
            "channel": channel_comparison(fmerged),
            "drone": drone_comparison(fmerged),
            "brands": _df_records(brand_ranking(fmerged, 50)),
            "product_type_cross": _df_records(product_type_cross(fmerged)),
            "type_month_cross": _df_records(type_month_cross(fmerged)),
            "product_monthly": _df_records(product_monthly(fmerged)),
            "monthly_multi_trend": _df_records(monthly_multi_trend(fmerged)),
            "filter_options": get_filter_options(dim_dealer, merged),
        }


# 全局单例
_center = MetricsCenter()

def get_center() -> MetricsCenter:
    return _center
