"""飞书多维表格实时数据加载器。

通过 lark-cli 从飞书 Base《线下活动管理》实时拉取活动记录，
解析成与 data_loader.load_activity() 兼容的英文列名 DataFrame。
"""
from __future__ import annotations

import json
import os
import subprocess
import pandas as pd
import time

from .config import ACTIVITY_COLUMNS, NUMERIC_FIELDS, DATE_FIELDS

BASE_TOKEN = "YOUR_FEISHU_BASE_TOKEN"
TABLE_ID = "YOUR_FEISHU_TABLE_ID"
PAGE_SIZE = 200

# 飞书 Base 实际字段名（去「【必填】」前缀后）→ 英文列名
# 与 data_loader.load_activity() 输出对齐，可直接喂给 data_model
FEISHU_FIELD_MAP = {
    "活动简述": "activity_desc",
    "活动类型": "activity_type",
    "状态": "activity_status",
    "门店名称": "store_name",
    "代理商": "dealer",
    "门店类型": "store_type",
    "城市": "city",
    "提报人": "reporter",
    "提出日期": "report_date",
    "活动时间": "activity_date",
    "场景标签": "scene_tags",
    "活动来源": "activity_source",
    "合作品牌": "partner_brands",
    "是否长期合作": "long_term_coop",
    "客户负责人": "insta_manager",
    "店长": "store_manager",
    "门店管理群": "feishu_group",
    # 数值字段
    "相关转化销售": "conversion_sales_raw",
    "转化主机数量": "converted_hosts",
    "当场成交率": "conversion_rate_pct",
    "参与人数": "participants",
    "企微添加": "wechat_adds",
    "Luna销量": "luna_sales",
    "x系列销量": "x_series_sales",
    "Go系列销量": "go_series_sales",
    "Ace系列销量": "ace_series_sales",
    "无人机销售数量": "drone_sales",
    "无人机企微客户添加数量": "drone_wechat",
    "是否展示/体验做无人机": "drone_display",
    "我司承担活动费用预估": "activity_cost",
    "加微率": "wechat_add_rate",
}

_CLI_ENV = {
    "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
    "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
    "PATH": os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin",
    "HOME": os.environ.get("HOME", ""),
}


def _run_cli(offset: int) -> dict:
    """调 lark-cli 拉一页记录。"""
    cmd = [
        "lark-cli", "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--as", "user",
        "--limit", str(PAGE_SIZE),
        "--offset", str(offset),
        "--json",
    ]
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, env=_CLI_ENV, timeout=120)
            if r.returncode != 0:
                err_msg = r.stderr[:500]
                if attempt < max_retries - 1 and ("timeout" in err_msg or "TLS" in err_msg):
                    wait = 3 * (attempt + 1)
                    print(f"  lark-cli 超时(offset={offset})，{wait}s 后重试({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"lark-cli failed (offset={offset}): {err_msg}")
            return json.loads(r.stdout)
        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                print(f"  lark-cli 超时(offset={offset})，{wait}s 后重试({attempt+1}/{max_retries})...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"lark-cli failed after {max_retries} retries (offset={offset})")


def _parse_cell(val):
    """把飞书单元格值转为 Python 原始值。"""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, list):
        if len(val) == 0:
            return None
        first = val[0]
        # 列表内全是字符串：直接拼接
        if isinstance(first, str):
            return ", ".join(val)
        if isinstance(first, dict):
            if "name" in first:
                return ", ".join(str(v.get("name", "")) for v in val if isinstance(v, dict))
            if "text" in first:
                return ", ".join(str(v.get("text", "")) for v in val if isinstance(v, dict))
            if "file_token" in first:
                return f"[附件x{len(val)}]"
        return str(val)
    if isinstance(val, dict):
        return str(val.get("text") or val.get("name") or val)
    return str(val)


def load_activity_from_feishu() -> pd.DataFrame:
    """从飞书实时拉取全量活动记录，返回英文列名 DataFrame。

    返回的 DataFrame 与 data_loader.load_activity() 结构一致，
    可直接喂给 data_model.build_merged_activity_store。
    """
    print("=" * 60)
    print("从飞书实时加载活动总池...")
    print("=" * 60)

    all_rows = []
    field_names = []
    offset = 0
    page = 0

    while True:
        result = _run_cli(offset)
        if not result.get("ok"):
            err = result.get("error", {})
            raise RuntimeError(f"飞书 API 错误: {err.get('message', '')}")

        data = result["data"]
        if not field_names:
            field_names = list(data.get("fields", []))

        record_ids = data.get("record_id_list", [])
        rows = data.get("data", [])
        for i, row in enumerate(rows):
            rec = {}
            for j in range(len(field_names)):
                fname = field_names[j].replace("【必填】", "")
                val = _parse_cell(row[j]) if j < len(row) else None
                en = FEISHU_FIELD_MAP.get(fname)
                if en:
                    rec[en] = val
            rec["record_id"] = record_ids[i] if i < len(record_ids) else None
            all_rows.append(rec)
        page += 1

        print(f"  已拉取 {len(all_rows)} 条...")
        if not data.get("has_more"):
            break
        offset += PAGE_SIZE

    df = pd.DataFrame(all_rows)
    print(f"  飞书活动总池: {len(df)} 条, {len(field_names)} 字段")

    # 多代理商逗号分隔：取第一个作为主代理商
    if "dealer" in df.columns:
        multi = df["dealer"].str.contains(",", na=False).sum()
        if multi > 0:
            df["dealer"] = df["dealer"].str.split(",").str[0].str.strip()
            print(f"  多代理商拆分: {multi} 条取首代理商")

    # 派生 sales_clean：从相关转化销售清洗数值
    if "conversion_sales_raw" in df.columns:
        df["sales_raw"] = pd.to_numeric(df["conversion_sales_raw"], errors="coerce")
        df = _clean_sales(df)
    else:
        df["sales_raw"] = 0.0
        df["sales_clean"] = 0.0
        df["sales_anomaly"] = False
        df["anomaly_reason"] = None
    _clean_numeric(df)
    _clean_dates(df)
    _strip_strings(df)
    return df.reset_index(drop=True)


def _clean_numeric(df: pd.DataFrame) -> None:
    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _clean_sales(df: pd.DataFrame) -> pd.DataFrame:
    """对齐 Excel 版销售清洗逻辑。

    4 条异常规则（与飞书导出 Excel 的销售_清洗一致）：
      1. sales_too_large: 销售额 > 50 万
      2. sales_per_unit_too_large: sales/hosts > 2 万 (hosts>0)
      3. sales_without_conversion_qty: sales > 5 万 且 hosts=0
      4. sales_per_participant_too_large: sales/participants > 5000 (participants>0)
    异常记录 sales_clean 置 0。
    """
    import numpy as np
    df = df.copy()
    df["sales_raw"] = pd.to_numeric(df["sales_raw"], errors="coerce").fillna(0)
    df["sales_clean"] = df["sales_raw"]
    df["sales_anomaly"] = False
    df["anomaly_reason"] = None

    hosts = pd.to_numeric(df.get("converted_hosts", 0), errors="coerce").fillna(0)
    participants = pd.to_numeric(df.get("participants", 0), errors="coerce").fillna(0)
    sales = df["sales_raw"]

    reasons = pd.Series("", index=df.index)

    # 1. 销售额过大
    mask1 = sales > 500000
    reasons[mask1] = "sales_too_large"

    # 2. 单台销售过高
    with np.errstate(divide="ignore", invalid="ignore"):
        per_unit = np.where(hosts > 0, sales / hosts, 0)
    mask2 = (hosts > 0) & (per_unit > 20000) & ~mask1
    reasons[mask2] = "sales_per_unit_too_large"

    # 3. 有销售但无转化主机
    mask3 = (sales > 50000) & (hosts == 0) & ~mask1 & ~mask2
    reasons[mask3] = "sales_without_conversion_qty"

    # 4. 人均销售过高
    with np.errstate(divide="ignore", invalid="ignore"):
        per_participant = np.where(participants > 0, sales / participants, 0)
    mask4 = (participants > 0) & (per_participant > 5000) & ~mask1 & ~mask2 & ~mask3
    reasons[mask4] = "sales_per_participant_too_large"

    anomaly_mask = mask1 | mask2 | mask3 | mask4
    df.loc[anomaly_mask, "sales_clean"] = 0
    df.loc[anomaly_mask, "sales_anomaly"] = True
    df.loc[anomaly_mask, "anomaly_reason"] = reasons[anomaly_mask]

    df["sales_clean"] = df["sales_clean"].fillna(0)
    print(f"  销售清洗: {anomaly_mask.sum()} 条异常置零, "
          f"清洗后总销售 {df['sales_clean'].sum():.0f}")
    return df

def _clean_dates(df: pd.DataFrame) -> None:
    for col in DATE_FIELDS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")


def _strip_strings(df: pd.DataFrame) -> None:
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})


if __name__ == "__main__":
    df = load_activity_from_feishu()
    print(df.shape)
    print("列名:", list(df.columns))
    print(df.head(2).to_string())
