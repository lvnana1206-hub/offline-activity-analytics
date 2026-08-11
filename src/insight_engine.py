"""运营洞察引擎 (Insight Engine)。

自动分析经营数据，生成结构化洞察和建议。

四类洞察：
  1. 经营问题     - 当前存在什么问题
  2. 增长机会     - 哪里有增长空间
  3. 优秀案例     - 哪些经验值得复制
  4. 风险预警     - 哪些门店/代理商需要关注

最终回答管理层四个问题：
  - 今天发生了什么？
  - 为什么发生？
  - 哪里需要关注？
  - 下一步如何运营？
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime

from .config import COMPLETED_STATUSES
from .rules_engine import get_engine


def _safe(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


# ── 洞察引擎 ────────────────────────────────────────────────

class InsightEngine:
    """运营洞察引擎。"""

    def __init__(self):
        self.engine = get_engine()

    def generate_insights(self, merged: pd.DataFrame, dim_store: pd.DataFrame,
                          dim_dealer: pd.DataFrame, scores: dict) -> dict:
        """生成全部洞察。"""
        print("运行运营洞察引擎...")
        return {
            "summary": self._executive_summary(merged, dim_store, dim_dealer, scores),
            "problems": self._identify_problems(merged, scores),
            "opportunities": self._identify_opportunities(merged, dim_store, scores),
            "replication": self._replication_candidates(merged, scores),
            "risks": self._risk_alerts(merged, scores),
            "recommendations": self._generate_recommendations(merged, scores),
        }

    # ── 经营摘要：今天发生了什么 ────────────────────────────

    def _executive_summary(self, merged, dim_store, dim_dealer, scores) -> list:
        """生成经营摘要洞察。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        df["participants"] = _safe(df["participants"])
        insights = []

        # 活动概况
        total = len(df)
        completed = (df["activity_status"].isin(COMPLETED_STATUSES)).sum()
        completion_rate = completed / total if total else 0
        total_sales = df["sales"].sum()
        total_participants = int(df["participants"].sum())

        insights.append({
            "category": "经营概况",
            "type": "summary",
            "severity": "info",
            "title": f"累计 {total} 场活动，完成 {completed} 场，销售额 {total_sales/10000:.1f} 万元",
            "detail": f"活动完成率 {completion_rate:.1%}，参与 {total_participants:,} 人次。"
                     f"{'完成率偏低，大部分活动处于待评估状态，建议推动活动闭环管理。' if completion_rate < 0.15 else '活动完成率正常。'}",
        })

        # 活动趋势
        df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
        df["ym"] = df["activity_date"].dt.to_period("M").astype(str)
        # Filter valid months (exclude NaT and unreasonable future dates)
        valid = df[df["activity_date"].notna()].copy()
        valid = valid[valid["activity_date"] <= pd.Timestamp.now()]
        monthly = valid.groupby("ym").size()
        if len(monthly) >= 2:
            recent = monthly.iloc[-1]
            prev = monthly.iloc[-2]
            if prev > 0:
                change = (recent - prev) / prev
                if change > 0.2:
                    insights.append({
                        "category": "趋势",
                        "type": "positive",
                        "severity": "info",
                        "title": f"活动量环比增长 {change:.0%}（{monthly.index[-2]} → {monthly.index[-1]}）",
                        "detail": f"最近月份 {recent} 场活动，较上月 {prev} 场显著增长，经营活跃度提升。",
                    })
                elif change < -0.2:
                    insights.append({
                        "category": "趋势",
                        "type": "warning",
                        "severity": "medium",
                        "title": f"活动量环比下降 {abs(change):.0%}（{monthly.index[-2]} → {monthly.index[-1]}）",
                        "detail": f"最近月份 {recent} 场活动，较上月 {prev} 场明显下降，需关注活动执行节奏。",
                    })

        # 门店覆盖
        active_stores = df["store_name"].nunique()
        total_stores = len(dim_store[dim_store["store_name"].notna()])
        coverage = active_stores / total_stores if total_stores else 0
        inactive = total_stores - active_stores
        insights.append({
            "category": "门店覆盖",
            "type": "summary",
            "severity": "medium" if coverage < 0.8 else "info",
            "title": f"门店覆盖率 {coverage:.1%}（{active_stores}/{total_stores}），{inactive} 家门店无活动",
            "detail": f"{'近三成门店无活动记录，存在覆盖盲区。' if coverage < 0.8 else '门店覆盖较充分。'}"
                     f"建议优先推动无活动门店的首场活动落地。",
        })

        # 评分概况
        store_scores = scores["store_scores"]
        grade_dist = store_scores["store_grade"].value_counts().to_dict()
        a_count = grade_dist.get("A", 0)
        b_count = grade_dist.get("B", 0)
        d_count = grade_dist.get("D", 0)
        insights.append({
            "category": "门店质量",
            "type": "summary",
            "severity": "info",
            "title": f"门店评分：A级 {a_count} 家，B级 {b_count} 家，D级 {d_count} 家",
            "detail": f"{'大部分门店评分偏低，活动经营能力有待提升。' if d_count > a_count + b_count else '门店经营质量分布较均衡。'}"
                     f"A/B级门店的经验可向 D 级门店输出。",
        })

        return insights

    # ── 经营问题：为什么发生 ────────────────────────────────

    def _identify_problems(self, merged, scores) -> list:
        """识别经营问题。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        df["participants"] = _safe(df["participants"])
        problems = []

        # 问题1: 活动完成率低
        completed = (df["activity_status"].isin(COMPLETED_STATUSES)).sum()
        total = len(df)
        rate = completed / total if total else 0
        if rate < 0.15:
            problems.append({
                "category": "活动闭环",
                "severity": "high",
                "title": f"活动完成率仅 {rate:.1%}，{total - completed} 场活动未完成闭环",
                "detail": "大量活动停留在待评估状态。根因可能是：活动复盘流程缺失、状态更新不及时、活动执行后缺乏跟踪机制。"
                         "建议建立活动闭环管理制度，活动结束后 7 天内必须完成状态更新和复盘。",
                "action": "建立活动 7 天闭环制度，指定复盘责任人",
            })

        # 问题2: 已完成活动销售低
        completed_df = df[df["activity_status"].isin(COMPLETED_STATUSES)]
        if len(completed_df) > 0:
            low_sales = (completed_df["sales"] < 500).sum()
            low_ratio = low_sales / len(completed_df)
            if low_ratio > 0.5:
                problems.append({
                    "category": "活动转化",
                    "severity": "high",
                    "title": f"{low_ratio:.0%} 的已完成活动销售额低于 500 元",
                    "detail": f"已完成活动中有 {low_sales} 场销售转化极低。"
                             "可能原因：活动以品牌曝光为主缺乏销售转化设计、参与人群不精准、"
                             "现场缺乏成交引导、活动类型与门店客群不匹配。",
                    "action": "优化活动转化设计，增加现场成交环节和销售激励",
                })

        # 问题3: 活动类型集中
        type_dist = df["activity_type"].value_counts()
        top_type_ratio = type_dist.iloc[0] / len(df) if len(df) else 0
        if top_type_ratio > 0.25:
            problems.append({
                "category": "活动多样性",
                "severity": "medium",
                "title": f"活动类型集中，{type_dist.index[0]} 占比 {top_type_ratio:.0%}",
                "detail": f"活动类型过于集中可能导致触达客群单一。"
                         f"Top3 类型：{', '.join(type_dist.head(3).index.tolist())}。"
                         "建议增加外拍活动、workshop 课堂等体验型活动，拓宽客群覆盖。",
                "action": "丰富活动类型组合，每月至少 2 种不同类型活动",
            })

        # 问题4: D级门店占比高
        store_scores = scores["store_scores"]
        d_ratio = (store_scores["store_grade"] == "D").mean()
        if d_ratio > 0.5:
            problems.append({
                "category": "门店经营",
                "severity": "high",
                "title": f"{d_ratio:.0%} 的门店评分为 D 级",
                "detail": f"共 {(store_scores['store_grade']=='D').sum()} 家门店评分低于 50 分。"
                         "主要问题集中在活动完成率低、销售转化弱。"
                         "建议对 D 级门店进行专项辅导，重点提升活动闭环和成交能力。",
                "action": "D 级门店专项辅导计划，月度跟踪评分提升",
            })

        # 问题5: 异常活动
        classified = self.engine.classify_activities_batch(df)
        anomaly_count = (classified["activity_class"] == "anomaly").sum()
        if anomaly_count > 0:
            problems.append({
                "category": "数据质量",
                "severity": "medium",
                "title": f"{anomaly_count} 场活动存在异常标记",
                "detail": "异常包括：销售额标记异常、已完成但零参与、高费用零产出。"
                         "建议人工复核异常活动，修正数据并优化活动提报流程。",
                "action": "人工复核异常活动，完善提报校验规则",
            })

        return problems

    # ── 增长机会 ────────────────────────────────────────────

    def _identify_opportunities(self, merged, dim_store, scores) -> list:
        """识别增长机会。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        opps = []

        # 机会1: 高潜力 D 级门店（活动量多但评分低）
        store_scores = scores["store_scores"]
        high_potential = store_scores[
            (store_scores["store_grade"] == "D") &
            (store_scores["activity_count"] >= 10)
        ].sort_values("activity_count", ascending=False)
        if len(high_potential) > 0:
            top_hp = high_potential.head(5)
            opps.append({
                "category": "门店提升",
                "severity": "info",
                "title": f"{len(high_potential)} 家 D 级门店活动量充足但转化弱，提升空间大",
                "detail": f"Top5：{', '.join(top_hp['store_name'].tolist()[:3])}等。"
                         "这些门店已有活动基础，核心问题是完成率和销售转化。"
                         "通过提升单场活动质量（而非增加数量），评分有望快速提升。",
                "action": "针对高活动量 D 级门店，优化活动质量而非增加数量",
            })

        # 机会2: 优秀活动类型可复制
        completed = df[df["activity_status"].isin(COMPLETED_STATUSES)]
        if len(completed) > 0:
            type_sales = completed.groupby("activity_type")["sales"].agg(["mean", "count"]).sort_values("mean", ascending=False)
            best_type = type_sales.index[0]
            best_avg = type_sales.iloc[0]["mean"]
            opps.append({
                "category": "活动类型",
                "severity": "info",
                "title": f"{best_type} 场均销售 {best_avg:.0f} 元，表现最优",
                "detail": f"已完成活动中，{best_type} 的场均销售额最高。"
                         f"Top3：{', '.join([f'{r[0]}({r[1]:.0f}元)' for r in type_sales.head(3).values])}。"
                         "建议将高表现活动类型向更多门店推广。",
                "action": f"将 {best_type} 活动模式标准化，向低表现门店推广",
            })

        # 机会3: 无活动门店的首场活动机会
        active = set(df["store_name"].dropna().unique())
        all_stores = set(dim_store[dim_store["store_name"].notna()]["store_name"].unique())
        inactive = all_stores - active
        if len(inactive) > 0:
            opps.append({
                "category": "门店拓展",
                "severity": "info",
                "title": f"{len(inactive)} 家门店从未举办活动，首场活动是增量机会",
                "detail": "无活动门店中包含已开业门店，首场活动即可带来增量曝光和销售。"
                         "建议优先选择高等级（S/A级）无活动门店启动活动。",
                "action": "优先推动 S/A 级无活动门店的首场活动",
            })

        # 机会4: 企微添加转化
        df["wechat"] = _safe(df["wechat_adds"])
        total_wechat = int(df["wechat"].sum())
        if total_wechat > 0:
            wechat_per_activity = total_wechat / len(df)
            opps.append({
                "category": "私域沉淀",
                "severity": "info",
                "title": f"累计企微添加 {total_wechat:,} 人，场均 {wechat_per_activity:.1f} 人",
                "detail": "企微是私域运营的核心触点。当前场均企微添加较低，"
                         "建议在活动中设置企微添加环节，配合专属优惠提升转化。",
                "action": "活动标配企微添加环节，设置添加激励",
            })

        return opps

    # ── 优秀案例：哪些经验值得复制 ──────────────────────────

    def _replication_candidates(self, merged, scores) -> list:
        """筛选可复制案例。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        df["participants"] = _safe(df["participants"])
        df["wechat"] = _safe(df["wechat_adds"])
        cases = []

        # 优秀门店模式
        store_scores = scores["store_scores"]
        top_stores = store_scores[store_scores["store_grade"].isin(["A", "B"])].head(5)
        for _, s in top_stores.iterrows():
            cases.append({
                "category": "优秀门店",
                "title": f"{s['store_name']}（{s['store_grade']}级 {s['store_score']}分）",
                "name": s["store_name"],
                "grade": s["store_grade"],
                "score": s["store_score"],
                "metrics": f"活动{s['activity_count']}场，销售¥{s['total_sales']:,.0f}，完成率{s['completion_rate']:.0%}",
                "replication": f"活动执行力强，完成率{s['completion_rate']:.0%}。"
                              f"{'活动类型多样（'+str(int(s['activity_types']))+'种）' if s['activity_types'] >= 3 else '活动专注度高'}。"
                              "建议其活动 SOP 向同级门店输出。",
            })

        # 优秀活动模式
        activity_scores = scores["activity_scores"]
        excellent = activity_scores[
            (activity_scores["activity_class"] == "excellent") |
            (activity_scores["activity_grade"].isin(["A", "B"]))
        ].sort_values("sales", ascending=False) if "activity_class" in activity_scores.columns else activity_scores[activity_scores["activity_grade"] == "A"].sort_values("sales", ascending=False)
        for _, a in excellent.head(3).iterrows():
            cases.append({
                "category": "优秀活动",
                "title": f"{str(a['activity_desc'])[:30]}... ({a['activity_type']})" if len(str(a.get('activity_desc',''))) > 30 else f"{a.get('activity_desc','')} ({a['activity_type']})",
                "name": str(a["activity_desc"])[:40] + ("..." if len(str(a["activity_desc"])) > 40 else ""),
                "grade": "A",
                "score": a.get("activity_score", 0),
                "metrics": f"销售¥{a['sales']:,.0f}，参与{int(a['participants'])}人，企微{int(a['wechat'])}人",
                "replication": f"活动类型：{a['activity_type']}，门店：{a['store_name']}。"
                              f"高销售+高互动的标杆活动，活动流程和话术值得标准化推广。",
            })

        # 优秀代理商模式
        dealer_scores = scores["dealer_scores"]
        top_dealers = dealer_scores[dealer_scores["dealer_grade"].isin(["A", "B"])].head(3)
        for _, d in top_dealers.iterrows():
            cases.append({
                "category": "优秀代理商",
                "title": f"{d['dealer']}（{d['dealer_grade']}级 {d['dealer_score']}分）",
                "name": d["dealer"],
                "grade": d["dealer_grade"],
                "score": d["dealer_score"],
                "metrics": f"活动{d['activity_count']}场，销售¥{d['total_sales']:,.0f}，覆盖率{d['coverage_rate']:.0%}",
                "replication": f"代理商评分{d['dealer_score']:.1f}（{d['dealer_grade']}级）。"
                              "其活动管理和门店辅导体系可作为其他代理商的参考模板。",
            })

        return cases

    # ── 风险预警：哪里需要关注 ──────────────────────────────

    def _risk_alerts(self, merged, scores) -> list:
        """风险预警。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
        risks = []

        # 风险门店：D 级 + 活动量少
        store_scores = scores["store_scores"]
        risk_stores = store_scores[
            (store_scores["store_grade"] == "D") &
            (store_scores["activity_count"] <= 3)
        ].sort_values("store_score")
        if len(risk_stores) > 0:
            risks.append({
                "category": "风险门店",
                "severity": "high",
                "title": f"{len(risk_stores)} 家门店评分 D 级且活动量≤3场",
                "detail": "Top5：" + ", ".join(risk_stores["store_name"].head(5).tolist()) +
                         "。这些门店活动极少且质量低，存在经营停滞风险。",
                "action": "区域经理 1 对 1 沟通，制定月度活动计划",
            })

        # 风险代理商
        dealer_scores = scores["dealer_scores"]
        risk_dealers = dealer_scores[dealer_scores["dealer_grade"] == "D"].sort_values("dealer_score")
        if len(risk_dealers) > 0:
            risks.append({
                "category": "风险代理商",
                "severity": "high",
                "title": f"{len(risk_dealers)} 家代理商评分为 D 级",
                "detail": "Top5：" + ", ".join(risk_dealers["dealer"].head(5).tolist()) +
                         "。代理商活动执行力和覆盖率偏低，需要运营辅导。",
                "action": "制定代理商提升计划，季度评估淘汰机制",
            })

        # 连续无活动
        latest = df["activity_date"].max()
        threshold = latest - pd.Timedelta(days=30)
        last_activity = df.groupby("store_name")["activity_date"].max()
        long_inactive = last_activity[last_activity < threshold]
        risks.append({
            "category": "活动断档",
            "severity": "medium",
            "title": f"{len(long_inactive)} 家门店连续 30 天以上无活动",
            "detail": "活动断档会导致品牌曝光下降和客群流失。"
                     "建议对断档超过 60 天的门店启动专项活动计划。",
            "action": "30 天无活动门店纳入月度督办清单",
        })

        # 销售下滑趋势
        df["ym"] = df["activity_date"].dt.to_period("M").astype(str)
        monthly_sales = df[df["activity_status"].isin(COMPLETED_STATUSES)].groupby("ym")["sales"].sum()
        if len(monthly_sales) >= 3:
            recent_3 = monthly_sales.iloc[-3:].mean()
            prev_3 = monthly_sales.iloc[-6:-3].mean() if len(monthly_sales) >= 6 else monthly_sales.iloc[:-3].mean()
            if prev_3 > 0 and recent_3 < prev_3 * 0.7:
                risks.append({
                    "category": "销售下滑",
                    "severity": "high",
                    "title": f"近 3 个月已完成活动销售额较前期下降 {(1-recent_3/prev_3)*100:.0f}%",
                    "detail": f"前期月均 ¥{prev_3:,.0f}，近期月均 ¥{recent_3:,.0f}。"
                             "销售下滑可能反映活动质量下降或市场需求变化，需深入分析。",
                    "action": "分析下滑根因，调整活动策略和资源投入",
                })

        return risks

    # ── 经营建议：下一步如何运营 ────────────────────────────

    def _generate_recommendations(self, merged, scores) -> list:
        """生成具体运营建议。"""
        df = merged.copy()
        df["sales"] = _safe(df["sales_clean"])
        df["participants"] = _safe(df["participants"])
        df["wechat"] = _safe(df["wechat_adds"])
        recs = []

        # 建议1: 活动闭环管理
        recs.append({
            "priority": 1,
            "category": "活动管理",
            "severity": "high",
            "title": "建立活动 7 天闭环制度",
            "detail": "当前活动完成率偏低，核心原因是活动后缺乏跟踪。"
                     "建议活动结束后 7 天内完成状态更新、数据回填和复盘。"
                     "由门店店长负责，区域经理督办。",
            "timeline": "1 个月内落地",
            "owner": "区域经理 + 店长",
        })

        # 建议2: D 级门店提升
        store_scores = scores["store_scores"]
        d_count = (store_scores["store_grade"] == "D").sum()
        recs.append({
            "priority": 2,
            "category": "门店提升",
            "severity": "medium",
            "title": f"启动 {d_count} 家 D 级门店专项提升计划",
            "detail": "D 级门店的核心问题是活动完成率和销售转化。"
                     "建议：①每月至少 1 场活动；②活动配置销售转化环节；"
                     "③A/B 级门店结对帮扶。月度跟踪评分变化。",
            "timeline": "本季度启动",
            "owner": "省区负责人",
        })

        # 建议3: 优秀活动复制
        classified = self.engine.classify_activities_batch(df)
        excellent = classified[classified["activity_class"] == "excellent"]
        if len(excellent) > 0:
            top_type = excellent["activity_type"].mode().iloc[0] if len(excellent) else "外拍活动"
            recs.append({
                "priority": 3,
                "category": "经验复制",
                "title": f"将 {top_type} 等优秀活动模式标准化推广",
                "detail": f"优秀活动中 {top_type} 占比最高。"
                         "建议提炼活动 SOP（筹备-执行-复盘全流程），"
                         "制作活动手册向全国门店推广。",
                "timeline": "2 个月内完成",
                "owner": "运营部",
            })

        # 建议4: 私域沉淀
        avg_wechat = df["wechat"].mean()
        recs.append({
            "priority": 4,
            "category": "私域运营",
            "severity": "medium",
            "title": "活动标配企微添加环节，提升私域沉淀",
            "detail": f"当前场均企微添加仅 {avg_wechat:.1f} 人。"
                     "建议每场活动设置企微添加环节，配合添加专属优惠（如配件折扣），"
                     "目标提升到场均 5 人以上。",
            "timeline": "立即执行",
            "owner": "店长",
        })

        # 建议5: 无活动门店启动
        active = df["store_name"].nunique()
        recs.append({
            "priority": 5,
            "category": "门店拓展",
            "severity": "medium",
            "title": "推动无活动门店首场活动落地",
            "detail": "优先选择 S/A 级无活动门店，配置标准活动方案。"
                     "首场活动以新品品鉴会或 workshop 课堂为主，降低执行门槛。",
            "timeline": "1 个月内启动",
            "owner": "省区负责人",
        })

        return recs


# 全局单例
_engine = InsightEngine()

def get_engine_insight() -> InsightEngine:
    return _engine
