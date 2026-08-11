"""飞书多维表格数据连接层。

通过 lark-cli 读取飞书 Base 数据，转为 pandas DataFrame。
支持分页、字段映射、错误处理。

用法:
    from backend.feishu_client import FeishuClient
    client = FeishuClient()
    df = client.fetch_activity_records()
    df = client.fetch_store_records()
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

import pandas as pd


# ── 飞书 Base 配置 ─────────────────────────────────────────

ACTIVITY_BASE = "YOUR_FEISHU_BASE_TOKEN"
ACTIVITY_TABLE = "YOUR_FEISHU_TABLE_ID"

STORE_BASE = "ZkjwbunpMagWfCswBzdcf5bMnAc"
STORE_TABLE = "tblZkCP20XtmSwIO"


# ── 字段映射：飞书字段名 -> 标准列名 ──────────────────────

ACTIVITY_FIELD_MAP = {
    "活动简述": "activity_desc",
    "活动时间": "activity_date",
    "活动类型": "activity_type",
    "状态": "activity_status",
    "门店名称": "store_name",
    "代理商": "dealer",
    "城市": "city",
    "提报人": "reporter",
    "提出日期": "report_date",
    "门店类型": "store_type",
    "【必填】参与人数": "participants",
    "【必填】企微添加": "wechat_adds",
    "【必填】相关转化销售": "sales_raw",
    "转化主机数量": "converted_hosts",
    "当场成交率": "conversion_rate_pct",
    "加微率": "add_rate",
    "【必填】无人机销售数量": "drone_sales",
    "【必填】无人机企微客户添加数量": "drone_wechat",
    "【必填】Luna销量": "luna_sales",
    "【必填】x系列销量": "x_series_sales",
    "【必填】Go系列销量": "go_series_sales",
    "【必填】Ace系列销量": "ace_series_sales",
    "活动来源": "activity_source",
    "场景标签": "scene_tags",
    "合作品牌": "partner_brands",
    "【必填】是否展示/体验做无人机": "drone_display",
    "是否长期合作": "long_term_coop",
    "店长": "store_manager",
    "门店管理群": "feishu_group",
    "客户负责人": "insta_manager",
}

STORE_FIELD_MAP = {
    "门店名称": "store_name",
    "代理商": "dealer",
    "代理商_分货": "dealer_distribution",
    "门店类别(2)": "store_category",
    "省区单元": "province_unit",
    "区域": "region",
    "省份": "province",
    "城市": "city",
    "城市等级": "city_tier",
    "营业状态": "business_status",
    "状态": "store_status",
    "开业时间": "open_date",
    "闭店日期": "close_date",
    "门店等级(最终)": "store_level",
    "铺型": "shop_type",
    "商场等级": "mall_level",
    "面积": "area_sqm",
    "店内是否能试飞": "can_fly_indoor",
    "客户负责人(YourCompany)": "insta_manager",
    "运营负责人": "ops_manager",
    "代理商运营代表": "dealer_ops_rep",
    "飞书管理群": "feishu_group",
    "商场名称": "mall_name",
    "店长": "store_manager",
    "店长电话": "manager_phone",
}


# ── 值清洗工具 ────────────────────────────────────────────

def _clean_value(val):
    """将飞书字段值清洗为标量。"""
    if val is None:
        return None
    if isinstance(val, list):
        if len(val) == 0:
            return None
        parts = []
        for item in val:
            if isinstance(item, dict) and "name" in item:
                parts.append(item["name"])
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return ",".join(parts)
    if isinstance(val, dict):
        if "name" in val:
            return val["name"]
        if "text" in val:
            return val["text"]
        return json.dumps(val, ensure_ascii=False)
    return val


def _clean_numeric(val):
    """尝试转为数值。"""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class FeishuClient:
    """飞书多维表格客户端，封装 lark-cli 调用。"""

    def __init__(self, identity: str = "user"):
        self.identity = identity

    @staticmethod
    def _base_activity():
        return ACTIVITY_BASE

    @staticmethod
    def _table_activity():
        return ACTIVITY_TABLE

    @staticmethod
    def _base_store():
        return STORE_BASE

    @staticmethod
    def _table_store():
        return STORE_TABLE

    def _run_lark(self, args: list[str]) -> dict:
        """执行 lark-cli 命令，返回 JSON。"""
        cmd = ["lark-cli"] + args + ["--as", self.identity, "--format", "json"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"lark-cli 失败({result.returncode}): {result.stderr or result.stdout}"
            )
        data = json.loads(result.stdout)
        if not data.get("ok"):
            raise RuntimeError(
                f"lark-cli 返回错误: {json.dumps(data.get('error', {}), ensure_ascii=False)[:200]}"
            )
        return data

    def _fetch_all(
        self, base_token: str, table_id: str, limit: int = 200
    ) -> pd.DataFrame:
        """分页拉取全部记录，返回 DataFrame。"""
        all_rows = []
        all_ids = []
        fields = None
        offset = 0

        while True:
            args = [
                "base", "+record-list",
                "--base-token", base_token,
                "--table-id", table_id,
                "--limit", str(limit),
                "--offset", str(offset),
            ]

            data = self._run_lark(args)["data"]
            rows = data["data"]
            ids = data["record_id_list"]
            if fields is None:
                fields = data["fields"]

            all_rows.extend(rows)
            all_ids.extend(ids)
            offset += len(rows)

            if not data.get("has_more") or len(rows) < limit:
                break

        df = pd.DataFrame(all_rows, columns=fields)
        df.insert(0, "record_id", all_ids)
        return df

    def fetch_activity_records(self) -> pd.DataFrame:
        """拉取飞书《线下活动管理》全量记录。"""
        print("拉取飞书活动总池...")
        df = self._fetch_all(ACTIVITY_BASE, ACTIVITY_TABLE)

        # 字段映射
        for feishu_name, std_name in ACTIVITY_FIELD_MAP.items():
            if feishu_name in df.columns:
                df[feishu_name] = df[feishu_name].apply(_clean_value)
                df.rename(columns={feishu_name: std_name}, inplace=True)

        df.rename(columns={"record_id": "activity_id"}, inplace=True)

        # 活动类型取第一个
        if "activity_type" in df.columns:
            df["activity_type"] = df["activity_type"].apply(
                lambda x: x.split(",")[0] if isinstance(x, str) else x
            )
        # 状态取第一个
        if "activity_status" in df.columns:
            df["activity_status"] = df["activity_status"].apply(
                lambda x: x.split(",")[0] if isinstance(x, str) else x
            )

        # 数值字段
        num_cols = [
            "participants", "wechat_adds", "sales_raw", "converted_hosts",
            "conversion_rate_pct", "drone_sales", "drone_wechat",
            "luna_sales", "x_series_sales", "go_series_sales", "ace_series_sales",
        ]
        for col in num_cols:
            if col in df.columns:
                df[col] = df[col].apply(_clean_numeric)

        # 日期字段
        for col in ["activity_date", "report_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        print(f"  活动记录: {len(df)} 条")
        return df

    def fetch_store_records(self) -> pd.DataFrame:
        """拉取飞书《专卖店信息表》全量记录。"""
        print("拉取飞书专卖店信息表...")
        df = self._fetch_all(STORE_BASE, STORE_TABLE)

        # 字段映射
        for feishu_name, std_name in STORE_FIELD_MAP.items():
            if feishu_name in df.columns:
                df[feishu_name] = df[feishu_name].apply(_clean_value)
                df.rename(columns={feishu_name: std_name}, inplace=True)

        df.rename(columns={"record_id": "store_id"}, inplace=True)

        # 日期字段
        if "open_date" in df.columns:
            df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")
        if "close_date" in df.columns:
            df["close_date"] = pd.to_datetime(df["close_date"], errors="coerce")

        # 数值
        if "area_sqm" in df.columns:
            df["area_sqm"] = df["area_sqm"].apply(_clean_numeric)

        print(f"  门店记录: {len(df)} 条")
        return df


def test_connection() -> bool:
    """测试飞书连接是否可用。"""
    try:
        result = subprocess.run(
            ["lark-cli", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        identities = data.get("identities", {})
        user = identities.get("user", {})
        return user.get("available", False) or user.get("status") == "ready"
    except Exception:
        return False


if __name__ == "__main__":
    if not test_connection():
        print("飞书连接失败，请先运行: lark-cli auth login")
        sys.exit(1)

    client = FeishuClient()
    print("=" * 60)
    print("飞书数据连接测试")
    print("=" * 60)

    try:
        activities = client.fetch_activity_records()
        print(f"\n活动表: {activities.shape}")
        print(f"列名: {list(activities.columns)}")
        print(f"\n前3行:")
        print(activities.head(3).to_string())
    except Exception as e:
        print(f"活动表拉取失败: {e}")

    try:
        stores = client.fetch_store_records()
        print(f"\n门店表: {stores.shape}")
        print(f"列名: {list(stores.columns)}")
    except Exception as e:
        print(f"门店表拉取失败: {e}")
