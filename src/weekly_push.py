"""代理商周报晾晒推送模块。

周期：上周六到本周五（零售自然周）。
功能：
  1. 生成代理商维度周报数据
  2. 格式化 markdown 报告
  3. 通过 lark-cli 推送到飞书群聊
  4. 可选写入飞书多维表格
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .analysis.common import safe_num
from .config import COMPLETED_STATUSES

LARK_CLI = "lark-cli"
BASE_TOKEN = "YOUR_FEISHU_BASE_TOKEN"
# 默认推送群：国内门店线下活动群
DEFAULT_CHAT_ID = "YOUR_FEISHU_CHAT_ID"

_CLI_ENV = {
    "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
    "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
    "PATH": os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin",
    "HOME": os.environ.get("HOME", ""),
}


def get_week_range(target_date: str | None = None) -> tuple[str, str, str]:
    """获取零售周范围（周六到周五）。

    返回 (week_start_str, week_end_str, label)。
    如果不传 target_date，默认取最近完成的零售周（上一个周五所在周）。
    """
    if target_date:
        ref = pd.Timestamp(target_date)
    else:
        ref = pd.Timestamp.now()
        # 回溯到最近周五
        days_since_fri = (ref.weekday() - 4) % 7
        ref = ref - pd.Timedelta(days=days_since_fri)

    # 周六 = 周五 + 1 天
    week_end = ref
    week_start = week_end - pd.Timedelta(days=6)  # 周六

    label = f"{week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}"
    return week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"), label


def generate_weekly_report(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame,
    dim_dealer: pd.DataFrame,
    target_date: str | None = None,
) -> dict:
    """生成代理商周报数据。

    返回包含完整周报数据的字典。
    """
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = safe_num(df["sales_clean"])
    df["participants"] = safe_num(df["participants"])
    df["wechat"] = safe_num(df["wechat_adds"])
    df["hosts"] = safe_num(df["converted_hosts"])
    dealer_col = "dealer_final" if "dealer_final" in df.columns else "dealer"
    df["dealer"] = df[dealer_col]

    week_start, week_end, label = get_week_range(target_date)
    ws = pd.Timestamp(week_start)
    we = pd.Timestamp(week_end) + pd.Timedelta(days=1)

    mask = (df["activity_date"] >= ws) & (df["activity_date"] < we)
    week_df = df[mask].copy()

    # 上周对比
    prev_we = ws - pd.Timedelta(days=1)
    prev_ws = prev_we - pd.Timedelta(days=6)
    prev_df = df[(df["activity_date"] >= prev_ws) & (df["activity_date"] <= prev_we)].copy()

    # 按代理商聚合
    def _dealer_agg(d: pd.DataFrame) -> pd.DataFrame:
        if len(d) == 0:
            return pd.DataFrame()
        d = d.copy()
        d["is_weekend"] = d["activity_date"].dt.weekday >= 5
        # 蓄水率
        d["wechat_rate"] = np.where(
            d["participants"] > 0, d["wechat"] / d["participants"], 0
        )
        d["is_valid"] = (d["wechat_rate"] > 0.05) | (d["hosts"] > 0)

        g = d.groupby("dealer").agg(
            activity_count=("record_id", "count"),
            weekend_count=("is_weekend", "sum"),
            weekday_count=("record_id", lambda x: (~d.loc[x.index, "is_weekend"]).sum()),
            total_sales=("sales", "sum"),
            total_participants=("participants", "sum"),
            total_wechat=("wechat", "sum"),
            total_hosts=("hosts", "sum"),
            stores_covered=("store_name", "nunique"),
            valid_count=("is_valid", "sum"),
            completed_count=("activity_status", lambda x: x.isin(COMPLETED_STATUSES).sum()),
        ).reset_index()
        g["health_score"] = (g["valid_count"] / g["activity_count"] * 100).round(1)
        g["completion_rate"] = (g["completed_count"] / g["activity_count"]).round(3)
        return g

    curr_g = _dealer_agg(week_df)
    prev_g = _dealer_agg(prev_df)

    # 关联门店总数
    if len(curr_g) > 0:
        curr_g = curr_g.merge(
            dim_dealer[["dealer", "store_count"]], on="dealer", how="left"
        )
        curr_g["store_count"] = curr_g["store_count"].fillna(0).astype(int)
        curr_g["coverage_rate"] = (
            curr_g["stores_covered"] / curr_g["store_count"]
        ).round(3)
        curr_g = curr_g.sort_values("activity_count", ascending=False)

    # 零活动代理商
    all_dealers = set(dim_dealer["dealer"].unique())
    active_dealers = set(week_df["dealer"].unique()) if len(week_df) > 0 else set()
    zero_dealers = sorted(all_dealers - active_dealers)
    zero_dealer_info = []
    for d in zero_dealers:
        row = dim_dealer[dim_dealer["dealer"] == d].iloc[0]
        zero_dealer_info.append({
            "dealer": d,
            "store_count": int(row.get("store_count", 0)),
        })

    # 低转化活动（转化率最低 Top10）
    low_conv = []
    if len(week_df) > 0:
        wd = week_df.copy()
        wd["conv_rate"] = np.where(
            wd["participants"] > 0, wd["hosts"] / wd["participants"], 0
        )
        low_df = wd[wd["activity_count"] > 0] if "activity_count" in wd.columns else wd
        low_df = wd.nsmallest(10, "conv_rate")[
            ["dealer", "activity_desc", "store_name", "conv_rate", "hosts", "participants"]
        ]
        low_conv = low_df.to_dict("records")

    # 低企微蓄水（蓄水率最低 Top10）
    low_wechat = []
    if len(week_df) > 0:
        wd = week_df.copy()
        wd["wechat_rate"] = np.where(
            wd["participants"] > 0, wd["wechat"] / wd["participants"], 0
        )
        low_w_df = wd.nsmallest(10, "wechat_rate")[
            ["dealer", "activity_desc", "store_name", "wechat_rate", "wechat", "participants"]
        ]
        low_wechat = low_w_df.to_dict("records")

    # 零活动门店
    all_stores = set(dim_store["store_name"].unique())
    active_stores = set(week_df["store_name"].unique()) if len(week_df) > 0 else set()
    zero_stores = sorted(s for s in (all_stores - active_stores) if s and isinstance(s, str))
    zero_stores = [s for s in zero_stores if s]

    return {
        "label": label,
        "week_start": week_start,
        "week_end": week_end,
        "summary": {
            "total_activities": int(len(week_df)),
            "total_dealers_active": int(len(active_dealers)),
            "total_dealers": int(len(all_dealers)),
            "total_stores_active": int(len(active_stores)),
            "total_stores": int(len(all_stores)),
            "total_sales": float(week_df["sales"].sum()),
            "total_participants": int(week_df["participants"].sum()),
            "total_wechat": int(week_df["wechat"].sum()),
            "total_hosts": int(week_df["hosts"].sum()),
            "zero_dealer_count": len(zero_dealers),
            "zero_store_count": len(zero_stores),
            "prev_activities": int(len(prev_df)),
        },
        "dealer_ranking": curr_g.to_dict("records") if len(curr_g) > 0 else [],
        "zero_dealers": zero_dealer_info,
        "low_conversion": [_clean(r) for r in low_conv],
        "low_wechat": [_clean(r) for r in low_wechat],
        "zero_store_count": len(zero_stores),
    }


def _clean(record: dict) -> dict:
    """清理 NaN/inf 等不可 JSON 序列化的值。"""
    for k, v in record.items():
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            record[k] = 0
        elif isinstance(v, (np.integer,)):
            record[k] = int(v)
        elif isinstance(v, (np.floating,)):
            record[k] = round(float(v), 4) if v == v else 0
    return record


def format_markdown_report(report: dict) -> str:
    """将周报数据格式化为飞书 markdown。"""
    s = report["summary"]
    label = report["label"]

    lines = [
        f"**📊 代理商周报晾晒 ({label})**\n",
        f"周期：{report['week_start']} ~ {report['week_end']}\n",
        "---\n",
        "**一、本周总览**\n",
        f"- 活动总场次：**{s['total_activities']}** 场"
        f"（上周 {s['prev_activities']} 场，"
        f"{'↑' if s['total_activities'] > s['prev_activities'] else '↓'}"
        f"{abs(s['total_activities']-s['prev_activities'])}）\n",
        f"- 活跃代理商：**{s['total_dealers_active']}**/{s['total_dealers']}"
        f"（零活动 {s['zero_dealer_count']} 家）\n",
        f"- 活跃门店：**{s['total_stores_active']}**/{s['total_stores']}"
        f"（零活动 {s['zero_store_count']} 家）\n",
        f"- 总销售额：**¥{fmt_num(s['total_sales'])}**\n",
        f"- 参与人数：{fmt_num(s['total_participants'])} | "
        f"企微新增：{fmt_num(s['total_wechat'])} | "
        f"转化主机：{fmt_num(s['total_hosts'])}\n",
        "---\n",
    ]

    # 代理商排行
    ranking = report["dealer_ranking"]
    if ranking:
        lines.append("**二、🏆 代理商活动量排行**\n")
        lines.append("| 排名 | 代理商 | 活动数 | 工作日 | 周末 | 覆盖率 | 健康度 | 销售额 |")
        lines.append("|:---:|:---|---:|---:|---:|---:|---:|---:|")
        for i, r in enumerate(ranking[:15], 1):
            lines.append(
                f"| {i} | {r['dealer'][:12]} | {int(r['activity_count'])} | "
                f"{int(r['weekday_count'])} | {int(r['weekend_count'])} | "
                f"{fmt_pct(r['coverage_rate'])} | {r['health_score']:.1f} | "
                f"¥{fmt_num(r['total_sales'])} |"
            )
        lines.append("")

    # 零活动代理商
    zero_d = report["zero_dealers"]
    if zero_d:
        lines.append("**三、⚠️ 零活动代理商（需跟进）**\n")
        lines.append("| 代理商 | 门店数 |")
        lines.append("|:---|---:|")
        for d in zero_d:
            lines.append(f"| {d['dealer'][:15]} | {d['store_count']} |")
        lines.append("")

    # 低转化
    low_c = report["low_conversion"]
    if low_c:
        lines.append("**四、📉 低转化活动 Top5（需复盘）**\n")
        lines.append("| 代理商 | 活动 | 门店 | 转化率 | 主机/参与 |")
        lines.append("|:---|:---|:---|---:|---:|")
        for r in low_c[:5]:
            lines.append(
                f"| {str(r.get('dealer',''))[:10]} | "
                f"{str(r.get('activity_desc',''))[:15]} | "
                f"{str(r.get('store_name',''))[:10]} | "
                f"{fmt_pct(r.get('conv_rate',0))} | "
                f"{int(r.get('hosts',0))}/{int(r.get('participants',0))} |"
            )
        lines.append("")

    # 低企微
    low_w = report["low_wechat"]
    if low_w:
        lines.append("**五、📱 企微蓄水低 Top5（需加强）**\n")
        lines.append("| 代理商 | 活动 | 门店 | 蓄水率 | 企微/参与 |")
        lines.append("|:---|:---|:---|---:|---:|")
        for r in low_w[:5]:
            lines.append(
                f"| {str(r.get('dealer',''))[:10]} | "
                f"{str(r.get('activity_desc',''))[:15]} | "
                f"{str(r.get('store_name',''))[:10]} | "
                f"{fmt_pct(r.get('wechat_rate',0))} | "
                f"{int(r.get('wechat',0))}/{int(r.get('participants',0))} |"
            )
        lines.append("")

    lines.append("---\n")
    lines.append("💡 请各代理商运营周末前追一下活动数据录入，零活动代理商请尽快补报。")

    return "\n".join(lines)


def fmt_num(n) -> str:
    if n is None:
        return "-"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if abs(n) >= 10000:
        return f"{n/10000:.1f}万"
    return f"{n:,.0f}"


def fmt_pct(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v)*100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def push_to_feishu(
    markdown: str,
    chat_id: str = DEFAULT_CHAT_ID,
    dry_run: bool = False,
) -> dict:
    """通过 lark-cli 发送 markdown 消息到飞书群聊。"""
    chat_id = chat_id or DEFAULT_CHAT_ID
    cmd = [
        LARK_CLI, "im", "+messages-send",
        "--chat-id", chat_id,
        "--as", "bot",
        "--markdown", markdown,
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd, capture_output=True, text=True, env=_CLI_ENV, timeout=60
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr or result.stdout}

    try:
        resp = json.loads(result.stdout)
        return {"ok": resp.get("ok", False), "data": resp.get("data", {})}
    except json.JSONDecodeError:
        return {"ok": True, "raw": result.stdout[:500]}


def run_weekly_push(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame,
    dim_dealer: pd.DataFrame,
    target_date: str | None = None,
    chat_id: str = DEFAULT_CHAT_ID,
    dry_run: bool = False,
) -> dict:
    """完整执行：生成周报 -> 格式化 -> 推送飞书。"""
    report = generate_weekly_report(merged, dim_store, dim_dealer, target_date)
    md = format_markdown_report(report)
    push_result = push_to_feishu(md, chat_id, dry_run)
    return {
        "report": report,
        "markdown": md,
        "push": push_result,
    }
