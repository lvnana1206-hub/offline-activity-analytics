"""飞书数据同步模块：从飞书多维表格拉取数据，覆盖到 data/raw/，再执行 ETL。

工作流:
  1. FeishuClient 拉取飞书活动表 + 门店表（原始字段名）
  2. 清理字段名 + 值（list/dict -> 纯文本字符串）
  3. 保存为 Excel 到 data/raw/（覆盖旧文件）
  4. 调用 ETL 管线刷新数据库

用法:
    python -m backend.feishu_sync
    或通过 API: POST /api/feishu/sync
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import RAW_DIR
from backend.feishu_client import FeishuClient, test_connection, _clean_value


# openpyxl 不允许的控制字符（用 chr 构建，避免源码中出现 null bytes）
_BAD_CHARS = ''.join(chr(i) for i in list(range(0, 9)) + [11, 12] + list(range(14, 32)))
_TRANS_TABLE = str.maketrans('', '', _BAD_CHARS)


def _strip_illegal(val):
    """移除 openpyxl 不支持的控制字符。"""
    if isinstance(val, str):
        return val.translate(_TRANS_TABLE)
    return val


def _clean_field_name(name: str) -> str:
    """清理飞书字段名，去除【必填】前缀等。"""
    if name.startswith("【必填】"):
        name = name[4:]
    return name


def _deep_clean_value(val):
    """深度清理值：list/dict -> 纯文本，再移除控制字符。"""
    val = _clean_value(val)
    if isinstance(val, str):
        val = val.translate(_TRANS_TABLE)
    return val


def _clean_df_for_excel(df):
    """清理 DataFrame：所有列的 list/dict 值转为纯文本，移除控制字符。"""
    for col in df.columns:
        df[col] = df[col].apply(_deep_clean_value)
    return df


def sync_from_feishu() -> dict:
    """从飞书拉取数据并同步到数据库。返回同步结果摘要。"""
    print("=" * 60)
    print("飞书数据同步开始")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not test_connection():
        raise RuntimeError("飞书连接失败，请先运行: lark-cli auth login")

    client = FeishuClient()

    # 拉取活动数据
    print("\n[1/4] 拉取飞书活动总池...")
    activities_df = client._fetch_all(
        client._base_activity(), client._table_activity()
    )
    activities_df.columns = [_clean_field_name(c) for c in activities_df.columns]
    if "record_id" in activities_df.columns:
        activities_df.rename(columns={"record_id": "记录ID"}, inplace=True)
    activities_df = _clean_df_for_excel(activities_df)
    activity_path = RAW_DIR / "活动总池.xlsx"
    activities_df.to_excel(activity_path, index=False, sheet_name="活动总池全量数据")
    print(f"  保存到: {activity_path} ({len(activities_df)} 条)")

    # 拉取门店数据
    print("\n[2/4] 拉取飞书专卖店信息表...")
    stores_df = client._fetch_all(
        client._base_store(), client._table_store()
    )
    stores_df.columns = [_clean_field_name(c) for c in stores_df.columns]
    if "record_id" in stores_df.columns:
        stores_df.rename(columns={"record_id": "记录ID"}, inplace=True)
    stores_df = _clean_df_for_excel(stores_df)
    store_path = RAW_DIR / "专卖店信息表.xlsx"
    stores_df.to_excel(store_path, index=False, sheet_name="门店全量映射")
    print(f"  保存到: {store_path} ({len(stores_df)} 条)")

    # 执行 ETL 管线
    print("\n[3/4] 执行 ETL 管线...")
    from etl_pipeline import run_etl
    etl_result = run_etl()

    print("\n[4/4] 飞书同步完成！")
    print(f"  活动记录: {len(activities_df)} 条")
    print(f"  门店记录: {len(stores_df)} 条")

    return {
        "sync_time": datetime.now().isoformat(timespec="seconds"),
        "activity_count": len(activities_df),
        "store_count": len(stores_df),
        "etl_result": etl_result,
    }


if __name__ == "__main__":
    result = sync_from_feishu()
    print(f"\n同步完成: {result}")
