"""数据加载与清洗模块。

从飞书导出的 Excel 中读取活动总池和专卖店信息表，
统一列名、清洗数值/日期字段、处理空值。
"""

import pandas as pd
import warnings

from .config import (
    ACTIVITY_FILE, STORE_FILE, ACTIVITY_COLUMNS, STORE_COLUMNS,
    NUMERIC_FIELDS, DATE_FIELDS,
)

warnings.filterwarnings("ignore")


def load_activity() -> pd.DataFrame:
    """加载活动总池，跳过标题行，统一列名为英文。"""
    df = pd.read_excel(ACTIVITY_FILE, sheet_name="活动总池全量数据", header=1)
    df = df.rename(columns=ACTIVITY_COLUMNS)
    # 过滤空记录（无记录ID的行）
    df = df[df["record_id"].notna() & (df["record_id"] != "")].copy()
    _clean_numeric(df)
    _clean_dates(df)
    _strip_strings(df)
    return df.reset_index(drop=True)


def load_stores() -> pd.DataFrame:
    """加载专卖店信息表（门店全量映射 sheet），统一列名为英文。"""
    df = pd.read_excel(STORE_FILE, sheet_name="门店全量映射")
    df = df.rename(columns=STORE_COLUMNS)
    _strip_strings(df)
    # 清洗面积
    df["area_sqm"] = pd.to_numeric(df["area_sqm"], errors="coerce")
    # 清洗开业时间
    df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")
    # 标准化营业状态：xxx -> 未知
    df["business_status"] = df["business_status"].replace({"xxx": "未知"}).fillna("未知")
    return df.reset_index(drop=True)


def _clean_numeric(df: pd.DataFrame) -> None:
    """将数值型字段转为 float，空字符串/无效值转 NaN。"""
    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _clean_dates(df: pd.DataFrame) -> None:
    """将日期字段转为 datetime。"""
    for col in DATE_FIELDS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")


def _strip_strings(df: pd.DataFrame) -> None:
    """去除字符串列的首尾空白。"""
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})
