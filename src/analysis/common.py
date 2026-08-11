"""经营分析引擎 - 公共工具。

所有周期分析模块共享的清洗与汇总逻辑。
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from ..config import COMPLETED_STATUSES


def safe_num(s) -> pd.Series:
    """将序列安全转为数值，空值填 0。"""
    return pd.to_numeric(s, errors="coerce").fillna(0)


def compute_health_score(df: pd.DataFrame) -> float:
    """健康度 = 有效活动数 / 活动总数 * 100。

    有效活动 = 蓄水率(wechat/participants) > 5% 或 转化主机(converted_hosts) > 0。
    要求 df 已经过 prepare() 预处理（含 wechat/participants/hosts 列）。
    """
    if len(df) == 0:
        return 0.0
    wechat = df["wechat"] if "wechat" in df.columns else 0
    participants = df["participants"] if "participants" in df.columns else 0
    hosts = df["hosts"] if "hosts" in df.columns else 0
    # 蓄水率 = 企微添加 / 参与人数
    rate = np.where(participants > 0, wechat / participants, 0.0)
    valid = (rate > 0.05) | (hosts > 0)
    return round(float(valid.sum()) / len(df) * 100, 1)


def compute_health_score_by_group(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """按分组列计算每组的健康度，返回 DataFrame(dealer/store_name, health_score)。"""
    if len(df) == 0 or group_col not in df.columns:
        return pd.DataFrame(columns=[group_col, "health_score"])
    wechat = df["wechat"] if "wechat" in df.columns else 0
    participants = df["participants"] if "participants" in df.columns else 0
    hosts = df["hosts"] if "hosts" in df.columns else 0
    rate = np.where(participants > 0, wechat / participants, 0.0)
    df = df.copy()
    df["_valid"] = (rate > 0.05) | (hosts > 0)
    g = df.groupby(group_col).agg(
        total=("record_id", "count"),
        valid=("_valid", "sum"),
    ).reset_index()
    g["health_score"] = (g["valid"] / g["total"] * 100).round(1)
    return g[[group_col, "health_score"]]


def prepare(merged: pd.DataFrame) -> pd.DataFrame:
    """统一预处理 merged_activity_store，返回可分析的副本。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = safe_num(df["sales_clean"])
    df["participants"] = safe_num(df["participants"])
    df["wechat"] = safe_num(df["wechat_adds"])
    df["hosts"] = safe_num(df["converted_hosts"])
    df["luna"] = safe_num(df["luna_sales"])
    df["drone"] = safe_num(df["drone_sales"])
    df["x_series"] = safe_num(df["x_series_sales"])
    df["go_series"] = safe_num(df["go_series_sales"])
    df["ace_series"] = safe_num(df["ace_series_sales"])
    df["is_completed"] = df["activity_status"].isin(COMPLETED_STATUSES)
    return df


def kpi_row(row) -> dict:
    """把一个聚合行的核心字段转成可 JSON 序列化的字典。"""
    out = {}
    for k, v in row.items():
        if isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        else:
            out[k] = v if pd.notna(v) else None
    return out


def finding(finding: str, cause: str, impact: str, action: str,
            severity: str = "medium") -> dict:
    """构造一条经营结论（发现/原因/影响/建议）。"""
    return {
        "finding": finding,
        "cause": cause,
        "impact": impact,
        "action": action,
        "severity": severity,
    }


def rec(title: str, detail: str, owner: str = "-", priority: int = 2,
        timeline: str = "-") -> dict:
    """构造一条经营建议。"""
    return {
        "title": title,
        "detail": detail,
        "owner": owner,
        "priority": priority,
        "timeline": timeline,
    }


def today_str(df: pd.DataFrame) -> str:
    """取数据中最新活动日期作为"今日"，便于演示。

    过滤掉异常未来日期（如脏数据 2031），以最近真实日期为准。
    """
    now = pd.Timestamp.now()
    dates = df["activity_date"].dropna()
    valid = dates[dates <= now]
    if len(valid) == 0:
        return now.strftime("%Y-%m-%d")
    return valid.max().strftime("%Y-%m-%d")


def zero_activity_stores(df_period: pd.DataFrame, dim_store: pd.DataFrame) -> list:
    """返回在指定周期内零活动的门店列表。"""
    if dim_store is None or len(dim_store) == 0:
        return []
    active = set(df_period["store_name"].dropna().unique()) if len(df_period) else set()
    all_stores = dim_store[dim_store["store_name"].notna()].drop_duplicates(subset="store_name")
    inactive = all_stores[~all_stores["store_name"].isin(active)]
    cols = ["store_name", "dealer", "province_unit", "region", "store_category"]
    return inactive[[c for c in cols if c in inactive.columns]].head(50).to_dict("records")


def zero_activity_dealers(df_period: pd.DataFrame, dim_dealer: pd.DataFrame, dealer_col: str) -> list:
    """返回在指定周期内零活动的代理商列表。"""
    if dim_dealer is None or len(dim_dealer) == 0 or "dealer" not in dim_dealer.columns:
        return []
    active = set(df_period[dealer_col].dropna().unique()) if len(df_period) and dealer_col in df_period.columns else set()
    all_dealers = dim_dealer[dim_dealer["dealer"].notna()]
    inactive = all_dealers[~all_dealers["dealer"].isin(active)]
    cols = ["dealer", "store_count", "province_units"]
    return inactive[[c for c in cols if c in inactive.columns]].head(50).to_dict("records")


def _compute_rates(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """按 group_col 聚合并计算转化率、企微蓄水率。"""
    g = df.groupby(group_col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        total_hosts=("hosts", "sum"),
    ).reset_index()
    g["conversion_rate"] = g.apply(
        lambda r: r["total_hosts"] / r["total_participants"] if r["total_participants"] > 0 else 0, axis=1
    )
    g["wechat_rate"] = g.apply(
        lambda r: r["total_wechat"] / r["total_participants"] if r["total_participants"] > 0 else 0, axis=1
    )
    return g


def low_conversion_stores(df_period: pd.DataFrame) -> list:
    """活动转化率最低的门店 Top20（参与人数>0 才参与排序）。"""
    if len(df_period) == 0:
        return []
    g = _compute_rates(df_period, "store_name")
    g = g.rename(columns={"store_name": "store"})
    low = g[g["total_participants"] > 0].sort_values("conversion_rate")
    return low.head(20).to_dict("records")


def low_conversion_dealers(df_period: pd.DataFrame, dealer_col: str) -> list:
    """活动转化率最低的代理商 Top20。"""
    if len(df_period) == 0 or dealer_col not in df_period.columns:
        return []
    g = _compute_rates(df_period, dealer_col)
    g = g.rename(columns={dealer_col: "dealer"})
    low = g[g["total_participants"] > 0].sort_values("conversion_rate")
    return low.head(20).to_dict("records")


def low_wechat_stores(df_period: pd.DataFrame) -> list:
    """企微蓄水率最低的门店 Top20。"""
    if len(df_period) == 0:
        return []
    g = _compute_rates(df_period, "store_name")
    g = g.rename(columns={"store_name": "store"})
    low = g[g["total_participants"] > 0].sort_values("wechat_rate")
    return low.head(20).to_dict("records")


def low_wechat_dealers(df_period: pd.DataFrame, dealer_col: str) -> list:
    """企微蓄水率最低的代理商 Top20。"""
    if len(df_period) == 0 or dealer_col not in df_period.columns:
        return []
    g = _compute_rates(df_period, dealer_col)
    g = g.rename(columns={dealer_col: "dealer"})
    low = g[g["total_participants"] > 0].sort_values("wechat_rate")
    return low.head(20).to_dict("records")


def activity_count_stores(df_period: pd.DataFrame) -> list:
    """门店活动量排名 Top20。"""
    if len(df_period) == 0:
        return []
    g = df_period.groupby("store_name").agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
    ).reset_index().sort_values("activity_count", ascending=False).head(20)
    return g.to_dict("records")


def activity_count_dealers(df_period: pd.DataFrame, dealer_col: str) -> list:
    """代理商活动量排名 Top20。"""
    if len(df_period) == 0 or dealer_col not in df_period.columns:
        return []
    g = df_period.groupby(dealer_col).agg(
        activity_count=("record_id", "count"),
        total_sales=("sales", "sum"),
        total_participants=("participants", "sum"),
        total_wechat=("wechat", "sum"),
        stores=("store_name", "nunique"),
    ).reset_index().sort_values("activity_count", ascending=False).head(20)
    g = g.rename(columns={dealer_col: "dealer"})
    return g.to_dict("records")
