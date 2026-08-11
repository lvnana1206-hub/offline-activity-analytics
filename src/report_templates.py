"""双模板周报引擎：代理商版（晾晒）+ 共享工具函数。"""
from __future__ import annotations

import numpy as np


def _fmt_num(n) -> str:
    if n is None:
        return "-"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if abs(n) >= 10000:
        return f"{n/10000:.1f}万"
    return f"{n:,.0f}"


def _fmt_pct(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v)*100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_wan(n) -> str:
    if n is None:
        return "-"
    try:
        return f"{float(n)/10000:.1f}万"
    except (TypeError, ValueError):
        return "-"


def _dealer_short(name: str, n: int = 10) -> str:
    if not name:
        return "-"
    return str(name)[:n]


def format_dealer_report(report: dict, analysis: dict | None = None) -> str:
    """代理商版：对标+激励+提醒。不含销售额。"""
    s = report["summary"]
    label = report["label"]
    ranking = report.get("dealer_ranking", [])
    zero_d = report.get("zero_dealers", [])
    low_c = report.get("low_conversion", [])
    low_w = report.get("low_wechat", [])

    zero_conv = [r for r in low_c if int(r.get("hosts", 0)) == 0]
    low_w_real = [r for r in low_w if float(r.get("wechat_rate", 0)) < 0.02]
    cov_rate = s["total_stores_active"] / s["total_stores"] if s["total_stores"] else 0
    diff = s["total_activities"] - s["prev_activities"]
    arrow = "+" if diff > 0 else "" if diff == 0 else str(diff)
    avg_act = s["total_activities"] / s["total_dealers"] if s["total_dealers"] else 0

    L: list[str] = []
    L.append(f"**\U0001f4ca 全国线下活动经营周报（{label}）**\n")
    L.append(f"**统计周期：{report['week_start']} ~ {report['week_end']}**\n---\n")

    # 一、本周概况
    L.append("## 一、本周概况\n")
    L.append(f"- 活动总场次：**{s['total_activities']} 场**"
             f"（环比 **+{diff}**）\n" if diff > 0
             else f"- 活动总场次：**{s['total_activities']} 场**\n")
    L.append(f"- 活跃代理商：**{s['total_dealers_active']} / {s['total_dealers']}**\n")
    L.append(f"- 活跃门店：**{s['total_stores_active']} / {s['total_stores']}**\n")
    L.append(f"- 参与人数：**{_fmt_num(s['total_participants'])}**\n")
    L.append(f"- 企微新增：**{_fmt_num(s['total_wechat'])}**\n")
    L.append(f"- 转化主机：**{_fmt_num(s['total_hosts'])}**\n")

    # 二、全国参考值
    L.append("\n## 二、全国参考值\n")
    L.append(f"- 代理商场均活动：**{avg_act:.1f} 场**\n")
    L.append(f"- 门店覆盖率：**{_fmt_pct(cov_rate)}**\n")

    # 三、本周标杆
    L.append("\n## 三、本周标杆\n")
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    for i, r in enumerate(ranking[:3]):
        L.append(
            f"{medals[i]} {_dealer_short(r['dealer'], 8)}"
            f"｜{int(r['activity_count'])} 场"
            f"｜覆盖率 {_fmt_pct(r.get('coverage_rate'))}"
            f"｜健康度 {r.get('health_score', 0):.0f}\n"
        )
    L.append("\n**参考点：**活动节奏稳定、门店覆盖较高、执行质量持续保持。\n")

    # 四、重点关注
    L.append("\n## 四、重点关注\n")

    if zero_d:
        L.append(f"**零活动代理商（{len(zero_d)} 家）**\n")
        names = "、".join(_dealer_short(d["dealer"], 6) for d in zero_d)
        L.append(names + "。\n")

    if zero_conv:
        L.append("\n**低转化活动（0 成交）**\n")
        for r in zero_conv[:5]:
            L.append(
                f"- {_dealer_short(r.get('dealer',''), 6)}"
                f"｜{str(r.get('store_name',''))[:10]}"
                f"｜参与 {int(r.get('participants',0))} 人\n"
            )

    if low_w_real:
        L.append("\n**低企微蓄水活动**\n")
        for r in low_w_real[:5]:
            L.append(
                f"- {_dealer_short(r.get('dealer',''), 6)}"
                f"｜{str(r.get('store_name',''))[:10]}"
                f"｜{_fmt_pct(r.get('wechat_rate'))}\n"
            )

    # 五、本周提醒
    L.append("\n## 五、本周提醒\n")
    L.append("- 零活动代理商完成活动规划并开展活动。\n")
    L.append("- 活动结束后及时录入数据、完成复盘。\n")
    L.append("- 对照标杆案例，提升活动覆盖率、企微蓄水率及成交转化。\n")
    target_cov = min(cov_rate * 100 + 5, 30)
    L.append(f"- 下周目标：**全国门店覆盖率提升至 {target_cov:.0f}%+。**\n")

    L.append("\n**数据来源：飞书多维表格（实时同步）｜统计周期：每周六至周五**")
    return "\n".join(L)
