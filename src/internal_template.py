"""内部版经营周报：六段结构。

结论->亮点->风险->督办->数据摘要->目标。
每一块回答一个管理问题。
"""
from __future__ import annotations

import numpy as np

from .report_templates import _fmt_num, _fmt_pct, _fmt_wan, _dealer_short


def format_internal_report(report: dict, analysis: dict | None = None) -> str:
    """六段结构内部版周报。"""
    s = report["summary"]
    label = report["label"]
    ranking = report.get("dealer_ranking", [])
    zero_d = report.get("zero_dealers", [])
    low_c = report.get("low_conversion", [])
    low_w = report.get("low_wechat", [])
    ana = analysis or {}
    weekly = ana.get("weekly", {})
    wdata = weekly.get("data", weekly) if weekly else {}

    zero_conv = [r for r in low_c if int(r.get("hosts", 0)) == 0]
    low_w_real = [r for r in low_w if float(r.get("wechat_rate", 0)) < 0.02]
    cov_rate = s["total_stores_active"] / s["total_stores"] if s["total_stores"] else 0
    diff = s["total_activities"] - s["prev_activities"]

    L: list[str] = []
    L.append(f"**\U0001f4ca 全国线下活动经营周报（{label}）**\n")
    L.append(f"周期：{report['week_start']} ~ {report['week_end']}\n---\n")

    _sec1_summary(L, s, diff, ranking, cov_rate)
    _sec2_highlights(L, s, diff, ranking, wdata)
    _sec3_risks(L, s, zero_d, zero_conv, low_w_real, cov_rate)
    _sec4_actions(L, s, zero_d, zero_conv, low_w_real, ranking)
    _sec5_data(L, ranking, zero_d, zero_conv, low_w_real, s)
    _sec6_goals(L, s, zero_d, cov_rate, ranking)

    L.append("\n---\n*内部使用 | 周期：周六至周五 | 数据来源：飞书多维表格*")
    return "\n".join(L)


# === 一、经营结论（3句话）===

def _sec1_summary(L, s, diff, ranking, cov_rate):
    L.append("**① 本周经营结论**\n")
    top3 = ranking[:3] if ranking else []
    top3_count = sum(int(r["activity_count"]) for r in top3)
    share = top3_count / s["total_activities"] * 100 if s["total_activities"] else 0

    # 第一句：发生了什么
    arrow = "增加" if diff > 0 else "减少" if diff < 0 else "持平"
    L.append(f"> 本周共{s['total_activities']}场活动，环比{arrow}{abs(diff) if diff else 0}场。")

    # 第二句：关键特征
    if share > 35 and len(top3) >= 2:
        names = "、".join(_dealer_short(r["dealer"], 4) for r in top3[:2])
        L.append(f"> 增长集中于{names}等头部代理商，全国门店覆盖率仅{_fmt_pct(cov_rate)}。")
    else:
        L.append(f"> 全国门店覆盖率{_fmt_pct(cov_rate)}，零活动门店{s['zero_store_count']}家。")

    # 第三句：下一步
    if diff > 0 and cov_rate < 0.25:
        L.append(f"> 下周重点转向扩大门店覆盖及提升活动质量。\n")
    else:
        L.append(f"> 下周持续推进门店覆盖及零活动代理商整改。\n")


# === 二、经营亮点（TOP3）===

def _sec2_highlights(L, s, diff, ranking, wdata):
    L.append("\n**② 经营亮点**\n")

    # ① 活动规模
    arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
    L.append(
        f"- **活动规模**：{s['total_activities']}场（环比{arrow}{abs(diff)}），"
        f"活跃代理商{s['total_dealers_active']}/{s['total_dealers']}\n"
    )

    # ② 优秀代理商
    if ranking:
        r = ranking[0]
        wd = int(r.get("weekday_count", 0))
        we = int(r.get("weekend_count", 0))
        if wd > 0 and we > 0:
            rhythm = "工作日及周末节奏稳定"
        elif we > wd:
            rhythm = "周末集中发力"
        else:
            rhythm = "工作日持续输出"
        L.append(
            f"- **优秀代理商**：{_dealer_short(r['dealer'], 8)}"
            f"（{int(r['activity_count'])}场，健康度{r.get('health_score', 0):.0f}），"
            f"{rhythm}\n"
        )

    # ③ 优秀门店案例
    excellent = wdata.get("excellent_activities", [])
    if excellent:
        ex = excellent[0]
        sales = ex.get("sales", 0)
        parts = []
        if sales and sales > 0:
            parts.append(f"成交¥{_fmt_num(sales)}")
        parts.append(f"企微{int(ex.get('wechat', 0))}人")
        L.append(
            f"- **优秀案例**：{ex.get('store_name', '')}"
            f"（{'、'.join(parts)}），可参考复制。\n"
        )
    else:
        L.append("- **优秀案例**：本周暂无突出案例。\n")


# === 三、风险预警（TOP3）===

def _sec3_risks(L, s, zero_d, zero_conv, low_w_real, cov_rate):
    L.append("\n**③ 风险预警**\n")
    risks = []
    if zero_d:
        risks.append(("\U0001f6a8", f"{len(zero_d)}家代理商零活动",
                       "活动覆盖缺失", "区域运营跟进"))
    if s["zero_store_count"] > 50:
        risks.append(("\U0001f6a8", f"{s['zero_store_count']}家门店零活动",
                       f"覆盖率仅{_fmt_pct(cov_rate)}", "推动复制"))
    if zero_conv:
        risks.append(("\U000026a0\ufe0f", f"{len(zero_conv)}场活动零成交",
                       "活动转化失效", "完成复盘"))
    if low_w_real:
        risks.append(("\U000026a0\ufe0f", f"{len(low_w_real)}场企微蓄水率<2%",
                       "现场引流不足", "加强蓄水"))

    for i, (emoji, desc, impact, action) in enumerate(risks[:3], 1):
        L.append(f"{emoji} {desc}\n> 影响：{impact}｜建议：{action}\n")

    if not risks:
        L.append("本周无明显经营风险。\n")


# === 四、本周督办（Action）===

def _sec4_actions(L, s, zero_d, zero_conv, low_w_real, ranking):
    L.append("\n**④ 本周督办**\n")
    L.append("| 事项 | 对象 | 原因 | 完成时间 |")
    L.append("|:---|:---|:---|:---|")
    actions = []
    if zero_d:
        actions.append(("零活动代理商跟进", "区域运营", f"{len(zero_d)}家零活动", "下周五"))
    if zero_conv:
        conv_d = set()
        for r in zero_conv:
            conv_d.add(_dealer_short(r.get("dealer", ""), 6))
        actions.append(("活动复盘", "区域运营", f"{len(conv_d)}家零成交", "周三"))
    if low_w_real:
        w_d = set()
        for r in low_w_real:
            w_d.add(_dealer_short(r.get("dealer", ""), 6))
        actions.append(("企微整改", "区域运营", f"{len(w_d)}家企微率低", "周五"))
    low_hs = [r for r in ranking if r.get("health_score", 100) < 60]
    if low_hs:
        actions.append(("质量复盘", "区域运营", f"{len(low_hs)}家健康度低", "周五"))
    for a in actions[:5]:
        L.append(f"| {a[0]} | {a[1]} | {a[2]} | {a[3]} |")
    if not actions:
        L.append("| 暂无重点督办 | - | - | - |")
    L.append("")


# === 五、数据摘要（排行榜+异常）===

def _sec5_data(L, ranking, zero_d, zero_conv, low_w_real, s):
    L.append("\n**⑤ 数据摘要**\n")

    # 排行榜
    L.append("*代理商排行 TOP10：*\n")
    L.append("| 排名 | 代理商 | 活动数 | 覆盖率 | 健康度 | 销售额 |")
    L.append("|:---:|:---|---:|---:|---:|---:|")
    for i, r in enumerate(ranking[:10], 1):
        L.append(
            f"| {i} | {_dealer_short(r['dealer'], 10)} | "
            f"{int(r['activity_count'])} | {_fmt_pct(r.get('coverage_rate'))} | "
            f"{r.get('health_score', 0):.0f} | \u00a5{_fmt_wan(r.get('total_sales'))} |"
        )
    L.append("")

    # 异常：零活动代理商
    if zero_d:
        L.append(f"\n*零活动代理商（{len(zero_d)}家）：*\n")
        names = "、".join(
            f"{_dealer_short(d['dealer'], 6)}（{d.get('store_count', 0)}店）" for d in zero_d
        )
        L.append(names + "\n")

    # 异常：零成交
    if zero_conv:
        L.append(f"\n*零成交活动（{len(zero_conv)}场）：*\n")
        for r in zero_conv[:5]:
            L.append(
                f"- {_dealer_short(r.get('dealer',''), 6)} | "
                f"{str(r.get('activity_desc',''))[:12]} | "
                f"参与{int(r.get('participants',0))}人"
            )
        L.append("")

    # 异常：低企微
    if low_w_real:
        L.append(f"\n*低企微蓄水（{len(low_w_real)}场）：*\n")
        for r in low_w_real[:5]:
            L.append(
                f"- {_dealer_short(r.get('dealer',''), 6)} | "
                f"{str(r.get('store_name',''))[:10]} | "
                f"{_fmt_pct(r.get('wechat_rate'))}"
            )
        L.append("")


# === 六、下周目标（3-5个指标）===

def _sec6_goals(L, s, zero_d, cov_rate, ranking):
    L.append("\n**⑥ 下周目标**\n")
    L.append("```")
    dealer_cov = s["total_dealers_active"] / s["total_dealers"] * 100 if s["total_dealers"] else 0
    L.append(f"目标1  代理商活动覆盖率  {dealer_cov:.0f}%  ->  85%")
    L.append(f"目标2  门店覆盖率        {_fmt_pct(cov_rate)}  ->  {min(cov_rate*100+5, 30):.0f}%")
    L.append(f"目标3  零活动代理商      {len(zero_d)}  ->  {max(len(zero_d)-3, 0)}")
    L.append(f"目标4  零活动门店        {s['zero_store_count']}  ->  {max(s['zero_store_count']-30, 0)}")
    avg_hs = sum(r.get("health_score", 0) for r in ranking) / len(ranking) if ranking else 0
    L.append(f"目标5  活动健康度        {avg_hs:.0f}  ->  {min(avg_hs+5, 100):.0f}")
    L.append("```")
    L.append(f"\n> 下周重点关注门店覆盖率提升及零活动代理商整改。\n")
