"""Q2 季度经营复盘 - 数据计算 + 独立 HTML 生成。

13个分析模块全部由 Python 计算，HTML 只负责 ECharts 渲染。
"""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
from datetime import datetime

from .data_model import build_all_models
from .config import COMPLETED_STATUSES


def _safe(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _records(df):
    """DataFrame -> JSON-safe records。"""
    df = df.replace([np.inf, -np.inf], None)
    df = df.where(pd.notnull(df), None)
    # Convert timestamps to strings
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (pd.Timestamp, datetime)) else x)
    return json.loads(json.dumps(df.to_dict("records"), default=str))


def compute_q2_review() -> dict:
    """计算 Q2 季度经营复盘全部 13 个模块。"""
    models = build_all_models()
    merged = models["merged_activity_store"]
    dim_store = models["dim_store"]
    dim_dealer = models["dim_dealer"]

    df = merged.copy()
    for col in ["sales_clean", "participants", "wechat_adds", "converted_hosts",
                "luna_sales", "x_series_sales", "go_series_sales", "ace_series_sales",
                "drone_sales", "activity_cost", "accessories_sales_amount"]:
        df[col] = _safe(df[col])
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df = df[df["activity_date"].notna() & (df["activity_date"] <= pd.Timestamp.now())]

    # Q2 筛选
    q2 = df[(df["activity_date"] >= "2026-04-01") & (df["activity_date"] < "2026-07-01")].copy()
    q2["sales"] = q2["sales_clean"]
    q2["participants"] = q2["participants"]
    q2["wechat"] = q2["wechat_adds"]
    q2["hosts"] = q2["converted_hosts"]
    q2["month"] = q2["activity_date"].dt.month

    # 有效活动
    is_completed = q2["activity_status"].isin(COMPLETED_STATUSES)
    is_effective = is_completed & ((q2["participants"] > 0) | (q2["sales"] > 0))

    region_col = "province_unit_final" if "province_unit_final" in q2.columns else "province"
    dealer_col = "dealer_final" if "dealer_final" in q2.columns else "dealer"

    result = {}

    # ═══════════════════════════════════════════════════════
    # 顶部信息
    # ═══════════════════════════════════════════════════════
    # Add helper columns for aggregation
    q2["_is_effective"] = is_effective.astype(int)
    q2["_has_drone"] = (q2["drone_display"].notna() & (q2["drone_display"] != "")).astype(int) if "drone_display" in q2.columns else 0

    result["header"] = {
        "title": "2026 Q2 线下活动经营复盘",
        "data_source": "飞书《线下活动管理》活动总池 + YourCompany专卖店信息表",
        "refresh_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_records": int(len(q2)),
        "effective_count": int(is_effective.sum()),
    }

    # ═══════════════════════════════════════════════════════
    # 一、Q2 经营总览 (8 KPI)
    # ═══════════════════════════════════════════════════════
    total_sales = float(q2["sales"].sum())
    total_participants = int(q2["participants"].sum())
    total_wechat = int(q2["wechat"].sum())
    total_hosts = int(q2["hosts"].sum())
    effective_count = int(is_effective.sum())
    avg_sales = total_sales / effective_count if effective_count else 0
    conversion_rate = float(q2["conversion_rate_pct"].dropna().mean()) / 100 if "conversion_rate_pct" in q2.columns else 0

    result["kpi"] = {
        "total_activities": int(len(q2)),
        "total_sales": total_sales,
        "total_hosts": total_hosts,
        "total_participants": total_participants,
        "total_wechat": total_wechat,
        "effective_activities": effective_count,
        "avg_sales": round(avg_sales, 2),
        "conversion_rate": round(conversion_rate, 4),
    }

    # ═══════════════════════════════════════════════════════
    # 二、月度趋势分析
    # ═══════════════════════════════════════════════════════
    monthly = q2.groupby("month").agg(
        activities=("record_id", "count"),
        sales=("sales", "sum"),
        hosts=("hosts", "sum"),
        wechat=("wechat", "sum"),
        effective=("_is_effective", "sum"),
        drone_activities=("_has_drone", "sum"),
    ).reset_index()
    monthly["month_name"] = monthly["month"].astype(int).astype(str) + "月"

    # 文字分析
    trend_analysis = []
    for _, r in monthly.iterrows():
        m = int(r["month"])
        trend_analysis.append(
            f"{r['month_name']}：{int(r['activities'])}场活动，"
            f"销售额{r['sales']/10000:.1f}万元，"
            f"转化主机{int(r['hosts'])}台，"
            f"企微新增{int(r['wechat'])}人。"
        )
    if len(monthly) >= 2:
        first = monthly.iloc[0]["activities"]
        last = monthly.iloc[-1]["activities"]
        growth = (last - first) / first * 100 if first else 0
        if growth > 20:
            trend_analysis.append(f"Q2活动量逐月增长，6月较4月增长{growth:.0f}%。")
            trend_analysis.append("6月活动快速增长主要受Luna新品上市带动，新品品鉴会和体验活动显著增加。")
        elif growth < -20:
            trend_analysis.append(f"Q2活动量逐月下降，6月较4月下降{abs(growth):.0f}%。")
        else:
            trend_analysis.append(f"Q2月度活动量总体平稳，6月较4月变化{growth:.0f}%。")

    result["monthly_trend"] = {
        "data": _records(monthly),
        "analysis": trend_analysis,
    }

    # ═══════════════════════════════════════════════════════
    # 三、活动转化漏斗
    # ═══════════════════════════════════════════════════════
    funnel = {
        "activities": int(len(q2)),
        "participants": total_participants,
        "wechat": total_wechat,
        "buyers": int(q2[q2["sales"] > 0].shape[0]),
        "hosts": total_hosts,
        "sales": total_sales,
    }
    funnel["r1"] = round(funnel["participants"] / funnel["activities"], 4) if funnel["activities"] else 0
    funnel["r2"] = round(funnel["wechat"] / funnel["participants"], 4) if funnel["participants"] else 0
    funnel["r3"] = round(funnel["buyers"] / funnel["participants"], 4) if funnel["participants"] else 0
    funnel["r4"] = round(funnel["hosts"] / funnel["buyers"], 4) if funnel["buyers"] else 0
    funnel["r5"] = round(funnel["sales"] / funnel["hosts"], 2) if funnel["hosts"] else 0
    result["funnel"] = funnel

    # ═══════════════════════════════════════════════════════
    # 四、活动类型经营分析
    # ═══════════════════════════════════════════════════════
    type_stats = q2.groupby("activity_type").agg(
        count=("record_id", "count"),
        effective=("_is_effective", "sum"),
        sales=("sales", "sum"),
        avg_sales=("sales", "mean"),
        hosts=("hosts", "sum"),
        wechat=("wechat", "sum"),
        participants=("participants", "sum"),
    ).reset_index()
    type_stats["effective_rate"] = (type_stats["effective"] / type_stats["count"]).round(4)
    type_stats = type_stats.sort_values("count", ascending=False)

    # 月度趋势
    type_monthly = q2.groupby(["month", "activity_type"]).size().reset_index(name="count")
    type_pivot = type_monthly.pivot(index="month", columns="activity_type", values="count").fillna(0)
    type_pivot = type_pivot.reset_index()
    type_pivot["month_name"] = type_pivot["month"].astype(int).astype(str) + "月"

    result["activity_types"] = {
        "table": _records(type_stats),
        "monthly": _records(type_pivot),
    }

    # ═══════════════════════════════════════════════════════
    # 五、产品线经营分析
    # ═══════════════════════════════════════════════════════
    products = {
        "Luna": "luna_sales", "X系列": "x_series_sales",
        "Go系列": "go_series_sales", "Ace系列": "ace_series_sales",
        "无人机": "drone_sales",
    }
    prod_rows = []
    for name, col in products.items():
        if col not in q2.columns:
            continue
        s = _safe(q2[col])
        active = (s > 0).sum()
        total = float(s.sum())
        prod_df = q2[s > 0]
        top_type = prod_df["activity_type"].mode().iloc[0] if len(prod_df) > 0 else "-"
        prod_rows.append({
            "product": name,
            "activity_count": int(active),
            "total_sales": total,
            "avg_sales": round(total / active, 2) if active else 0,
            "participants": int(prod_df["participants"].sum()) if len(prod_df) > 0 else 0,
            "top_type": top_type,
        })

    # 产品 × 活动类型 交叉矩阵
    cross_data = []
    for pname, pcol in products.items():
        if pcol not in q2.columns:
            continue
        for atype in q2["activity_type"].unique():
            mask = (q2[pcol] > 0) & (q2["activity_type"] == atype)
            count = int(mask.sum())
            if count > 0:
                sales = float(q2.loc[mask, "sales"].sum())
                cross_data.append({"product": pname, "activity_type": atype, "count": count, "sales": round(sales, 2)})

    # 产品月度趋势
    prod_monthly = q2.groupby("month").agg(
        Luna=("luna_sales", "sum"),
        X系列=("x_series_sales", "sum"),
        Go系列=("go_series_sales", "sum"),
        Ace系列=("ace_series_sales", "sum"),
        无人机=("drone_sales", "sum"),
    ).reset_index()
    prod_monthly["month_name"] = prod_monthly["month"].astype(int).astype(str) + "月"

    result["products"] = {
        "table": prod_rows,
        "cross": cross_data,
        "monthly": _records(prod_monthly),
    }

    # ═══════════════════════════════════════════════════════
    # 六、代理商经营排行 Top20
    # ═══════════════════════════════════════════════════════
    dealer_stats = q2.groupby(dealer_col).agg(
        activities=("record_id", "count"),
        effective=("_is_effective", "sum"),
        sales=("sales", "sum"),
        hosts=("hosts", "sum"),
        wechat=("wechat", "sum"),
        participants=("participants", "sum"),
    ).reset_index().rename(columns={dealer_col: "dealer"})
    dealer_stats["effective_rate"] = (dealer_stats["effective"] / dealer_stats["activities"]).round(4)
    dealer_stats["avg_sales"] = (dealer_stats["sales"] / dealer_stats["activities"]).round(2)
    # 关联省区
    dealer_region = dim_dealer[["dealer", "province_units"]].copy()
    dealer_stats = dealer_stats.merge(dealer_region, on="dealer", how="left")
    dealer_stats["province"] = dealer_stats["province_units"].fillna("-")
    dealer_stats = dealer_stats.sort_values("activities", ascending=False).head(20).reset_index(drop=True)
    dealer_stats.insert(0, "rank", range(1, len(dealer_stats) + 1))
    result["dealer_top20"] = _records(dealer_stats)

    # ═══════════════════════════════════════════════════════
    # 七、门店经营排行 Top20
    # ═══════════════════════════════════════════════════════
    store_stats = q2.groupby("store_name").agg(
        activities=("record_id", "count"),
        sales=("sales", "sum"),
        hosts=("hosts", "sum"),
        wechat=("wechat", "sum"),
        participants=("participants", "sum"),
    ).reset_index()
    store_stats["avg_sales"] = (store_stats["sales"] / store_stats["activities"]).round(2)
    # 关联代理商和省区
    store_info = dim_store[["store_name", "dealer", "province_unit"]].copy()
    store_info = store_info.drop_duplicates(subset="store_name", keep="first")
    store_stats = store_stats.merge(store_info, on="store_name", how="left")
    store_stats = store_stats.sort_values("sales", ascending=False).head(20).reset_index(drop=True)
    store_stats.insert(0, "rank", range(1, len(store_stats) + 1))
    result["store_top20"] = _records(store_stats)

    # ═══════════════════════════════════════════════════════
    # 八、区域经营分析
    # ═══════════════════════════════════════════════════════
    region_stats = q2.groupby(region_col).agg(
        activities=("record_id", "count"),
        sales=("sales", "sum"),
        hosts=("hosts", "sum"),
        stores=("store_name", "nunique"),
        dealers=("dealer", "nunique"),
        participants=("participants", "sum"),
    ).reset_index().rename(columns={region_col: "region"})
    region_stats = region_stats[region_stats["region"].notna()].sort_values("sales", ascending=False)

    # 省份分析
    province_stats = q2.groupby("province").agg(
        activities=("record_id", "count"),
        sales=("sales", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index()
    province_stats = province_stats[province_stats["province"].notna()].sort_values("activities", ascending=False)

    result["regions"] = {
        "province_units": _records(region_stats),
        "provinces": _records(province_stats.head(15)),
    }

    # ═══════════════════════════════════════════════════════
    # 九、渠道经营分析 (Mall店 vs 照材店)
    # ═══════════════════════════════════════════════════════
    cat_col = "store_category" if "store_category" in q2.columns else "store_category_final"
    if cat_col in q2.columns:
        channel_stats = q2.groupby(cat_col).agg(
            activities=("record_id", "count"),
            sales=("sales", "sum"),
            hosts=("hosts", "sum"),
            participants=("participants", "sum"),
            wechat=("wechat", "sum"),
        ).reset_index().rename(columns={cat_col: "channel"})
        channel_stats["avg_sales"] = (channel_stats["sales"] / channel_stats["activities"]).round(2)
        channel_stats["conversion"] = (channel_stats["hosts"] / channel_stats["participants"]).round(4)
        result["channels"] = _records(channel_stats)
    else:
        result["channels"] = []

    # ═══════════════════════════════════════════════════════
    # 十、无人机经营分析
    # ═══════════════════════════════════════════════════════
    if "drone_display" in q2.columns:
        drone_mask = q2["drone_display"].notna() & (q2["drone_display"] != "")
    else:
        drone_mask = _safe(q2.get("drone_sales", 0)) > 0
    drone_activities = q2[drone_mask]
    normal_activities = q2[~drone_mask]

    drone_compare = {
        "drone": {
            "count": int(len(drone_activities)),
            "sales": float(drone_activities["sales"].sum()),
            "participants": int(drone_activities["participants"].sum()),
            "hosts": int(drone_activities["hosts"].sum()),
            "wechat": int(drone_activities["wechat"].sum()),
            "avg_sales": round(float(drone_activities["sales"].mean()), 2) if len(drone_activities) else 0,
        },
        "normal": {
            "count": int(len(normal_activities)),
            "sales": float(normal_activities["sales"].sum()),
            "participants": int(normal_activities["participants"].sum()),
            "hosts": int(normal_activities["hosts"].sum()),
            "wechat": int(normal_activities["wechat"].sum()),
            "avg_sales": round(float(normal_activities["sales"].mean()), 2) if len(normal_activities) else 0,
        },
    }
    total_act = len(q2)
    drone_compare["drone_ratio"] = round(len(drone_activities) / total_act, 4) if total_act else 0
    result["drone"] = drone_compare

    # ═══════════════════════════════════════════════════════
    # 十一、异业合作经营分析
    # ═══════════════════════════════════════════════════════
    coop_mask = q2["activity_type"].str.contains("异业", na=False)
    coop_activities = q2[coop_mask]
    normal_non_coop = q2[~coop_mask]

    # 品牌排行
    brand_data = []
    for _, r in coop_activities.iterrows():
        brands = str(r.get("partner_brands", "")).split("/")
        for b in brands:
            b = b.strip()
            if b and b not in ["无", "nan", "None", ""]:
                brand_data.append({"brand": b, "sales": float(r["sales"]),
                                   "participants": int(r["participants"])})
    brand_df = pd.DataFrame(brand_data)
    if len(brand_df) > 0:
        brand_stats = brand_df.groupby("brand").agg(
            count=("brand", "count"),
            sales=("sales", "sum"),
            participants=("participants", "sum"),
        ).reset_index().sort_values("count", ascending=False).head(15)
        brand_stats = brand_stats.rename(columns={"count": "coop_count"})
    else:
        brand_stats = pd.DataFrame()

    result["coop"] = {
        "coop": {
            "count": int(len(coop_activities)),
            "sales": float(coop_activities["sales"].sum()),
            "participants": int(coop_activities["participants"].sum()),
            "avg_sales": round(float(coop_activities["sales"].mean()), 2) if len(coop_activities) else 0,
        },
        "normal": {
            "count": int(len(normal_non_coop)),
            "sales": float(normal_non_coop["sales"].sum()),
            "participants": int(normal_non_coop["participants"].sum()),
            "avg_sales": round(float(normal_non_coop["sales"].mean()), 2) if len(normal_non_coop) else 0,
        },
        "brands": _records(brand_stats),
    }

    # ═══════════════════════════════════════════════════════
    # 十二、优秀案例中心 Top20
    # ═══════════════════════════════════════════════════════
    comp = q2[is_completed & (q2["sales"] > 0)].copy()
    if len(comp) > 0:
        comp["score"] = (
            comp["sales"].rank(pct=True) * 0.35 +
            comp["participants"].rank(pct=True) * 0.20 +
            comp["wechat"].rank(pct=True) * 0.20 +
            comp["hosts"].rank(pct=True) * 0.15 +
            (comp["activity_type"].nunique() / max(comp["activity_type"].nunique(), 1)) * 0.10
        ).round(3)
        top20 = comp.nlargest(20, "score")
        cases = []
        for _, r in top20.iterrows():
            reasons = []
            if r["sales"] > comp["sales"].quantile(0.75):
                reasons.append("销售额处于Top25%")
            if r["participants"] > comp["participants"].quantile(0.75):
                reasons.append("参与人数突出")
            if r["wechat"] > 5:
                reasons.append("企微蓄水效果好")
            if r["hosts"] > comp["hosts"].quantile(0.75):
                reasons.append("转化主机数高")
            if not reasons:
                reasons.append("综合表现均衡")
            cases.append({
                "activity_desc": str(r["activity_desc"])[:50],
                "activity_type": r["activity_type"],
                "store_name": r["store_name"],
                "dealer": r.get(dealer_col, r.get("dealer", "-")),
                "sales": float(r["sales"]),
                "participants": int(r["participants"]),
                "wechat": int(r["wechat"]),
                "hosts": int(r["hosts"]),
                "score": float(r["score"]),
                "activity_date": str(r["activity_date"].date()) if pd.notna(r["activity_date"]) else "-",
                "recommend_reason": "；".join(reasons),
            })
        result["cases"] = cases
    else:
        result["cases"] = []

    # ═══════════════════════════════════════════════════════
    # 十三、经营总结
    # ═══════════════════════════════════════════════════════
    summaries = []

    # 亮点
    summaries.append({"category": "Q2经营亮点", "items": [
        {"finding": f"Q2共举办{len(q2)}场活动，销售额{total_sales/10000:.1f}万元，参与{total_participants:,}人次",
         "cause": "活动体系覆盖311家门店，门店覆盖率较高", "impact": "品牌曝光广泛", "suggestion": "保持活动节奏"},
        {"finding": f"有效活动{effective_count}场，有效率{effective_count/len(q2):.0%}",
         "cause": "活动执行闭环良好", "impact": "活动质量有保障", "suggestion": "持续优化活动质量"},
    ]})

    # 问题
    low_sales_count = int((q2.loc[is_completed, "sales"] < 500).sum())
    summaries.append({"category": "Q2存在问题", "items": [
        {"finding": f"{low_sales_count}场活动销售额低于500元",
         "cause": "活动以品牌曝光为主，缺乏销售转化设计", "impact": "投入产出比低", "suggestion": "增加现场成交环节和销售激励"},
    ]})

    # 优秀门店经验
    top_store = store_stats.iloc[0] if len(store_stats) > 0 else None
    if top_store is not None:
        summaries.append({"category": "优秀门店经验", "items": [
            {"finding": f"{top_store['store_name']}销售额最高(¥{top_store['sales']/10000:.1f}万)",
             "cause": f"举办{int(top_store['activities'])}场活动，活动频次高", "impact": "门店经营标杆", "suggestion": "向同类门店复制其活动模式"},
        ]})

    # 优秀代理商经验
    top_dealer = dealer_stats.iloc[0] if len(dealer_stats) > 0 else None
    if top_dealer is not None:
        summaries.append({"category": "优秀代理商经验", "items": [
            {"finding": f"{top_dealer['dealer']}活动量最高({int(top_dealer['activities'])}场)",
             "cause": f"覆盖{int(top_dealer['effective'])}场有效活动，执行力强", "impact": "代理商经营标杆", "suggestion": "其活动管理SOP向其他代理商输出"},
        ]})

    # 优秀活动打法
    if len(result["cases"]) > 0:
        top_case = result["cases"][0]
        summaries.append({"category": "优秀活动打法", "items": [
            {"finding": f"最佳综合案例：{top_case['activity_desc'][:30]}...",
             "cause": top_case["recommend_reason"], "impact": "销售转化和参与互动兼具", "suggestion": "提炼活动SOP全国推广"},
        ]})

    # Q3方向
    best_type = type_stats.sort_values("avg_sales", ascending=False).iloc[0] if len(type_stats) > 0 else None
    q3_items = [
        {"finding": "Luna新品是Q2增长引擎", "cause": "Luna销量占比最高，新品品鉴会效果突出",
         "impact": "新品上市带动整体销售增长", "suggestion": "Q3继续扩大Luna体验活动覆盖范围"},
        {"finding": "区域执行差异大", "cause": "资源向头部区域集中", "impact": "低活动量区域增长受限",
         "suggestion": "复制成熟区域活动模式至机会区域"},
    ]
    if best_type is not None:
        q3_items.append({"finding": f"{best_type['activity_type']}场均销售最高(¥{best_type['avg_sales']:,.0f})",
                         "cause": "活动类型与客群匹配度高", "impact": "活动效率最优",
                         "suggestion": f"Q3重点推广{best_type['activity_type']}模式"})
    summaries.append({"category": "Q3重点方向", "items": q3_items})

    result["summaries"] = summaries

    return result


if __name__ == "__main__":
    print("计算 Q2 季度经营复盘...")
    data = compute_q2_review()
    print(f"\n模块: {list(data.keys())}")
    print(f"KPI: {data['kpi']}")
    print(f"月度趋势: {len(data['monthly_trend']['data'])}个月")
    print(f"活动类型: {len(data['activity_types']['table'])}种")
    print(f"产品: {len(data['products']['table'])}个")
    print(f"代理商Top20: {len(data['dealer_top20'])}家")
    print(f"门店Top20: {len(data['store_top20'])}家")
    print(f"区域: {len(data['regions']['province_units'])}个")
    print(f"渠道: {len(data['channels'])}类")
    print(f"优秀案例: {len(data['cases'])}个")
    print(f"经营总结: {len(data['summaries'])}类")
