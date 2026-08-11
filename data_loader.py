"""统一数据读取模块。

自动读取 data/raw/ 目录下所有配置的 Excel 文件。
新增 Excel 只需在 config.py 的 EXCEL_SOURCES 中添加配置，无需改本文件。

用法::
    from data_loader import load_activity, load_stores, load_all
    activity_df = load_activity()
    store_df = load_stores()
    all_data = load_all()  # {name: DataFrame}
"""

from __future__ import annotations

import pandas as pd
import warnings

from config import (
    EXCEL_SOURCES, raw_path,
    ACTIVITY_COLUMNS, STORE_COLUMNS,
    NUMERIC_FIELDS, DATE_FIELDS,
)

warnings.filterwarnings("ignore")


# ── 单表加载 ──────────────────────────────────────────────

def _read_excel(name: str) -> pd.DataFrame:
    """按 EXCEL_SOURCES 配置读取单个 Excel，返回原始 DataFrame。"""
    cfg = EXCEL_SOURCES[name]
    path = raw_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")
    df = pd.read_excel(
        path,
        sheet_name=cfg["sheet"],
        header=cfg.get("header_row", 0),
    )
    # Strip 【必填】 prefix from column names (Feishu export format)
    df.columns = [c.replace("【必填】", "") if isinstance(c, str) else c for c in df.columns]
    return df


def load_activity() -> pd.DataFrame:
    """加载活动总池，统一列名为英文，清洗数值/日期。"""
    df = _read_excel("activity")
    df = df.rename(columns=ACTIVITY_COLUMNS)
    df = df[df["record_id"].notna() & (df["record_id"] != "")].copy()
    # Derive sales_clean from conversion_sales_raw if not present
    if "sales_clean" not in df.columns and "conversion_sales_raw" in df.columns:
        df["sales_clean"] = df["conversion_sales_raw"]
        # Cap extreme outliers (> 10M is data entry error)
        df.loc[df["sales_clean"] > 10_000_000, "sales_clean"] = 0
    if "sales_raw" not in df.columns and "conversion_sales_raw" in df.columns:
        df["sales_raw"] = df["conversion_sales_raw"]
        df.loc[df["sales_raw"] > 10_000_000, "sales_raw"] = 0
    # Derive business_category from store_type if not present
    if "business_category" not in df.columns and "store_type" in df.columns:
        df["business_category"] = df["store_type"].apply(
            lambda v: "Mall商" if "Mall" in str(v) else ("照材商" if "照材" in str(v) else "其他")
        )
    _clean_numeric(df)
    _clean_dates(df)
    _strip_strings(df)
    return df.reset_index(drop=True)


def load_stores() -> pd.DataFrame:
    """加载专卖店信息表，统一列名为英文，清洗数值/日期。"""
    df = _read_excel("store")
    df = df.rename(columns=STORE_COLUMNS)
    _strip_strings(df)
    df["area_sqm"] = pd.to_numeric(df["area_sqm"], errors="coerce")
    df["open_date"] = pd.to_datetime(df["open_date"], errors="coerce")
    df["business_status"] = df["business_status"].replace({"xxx": "未知"}).fillna("未知")
    return df.reset_index(drop=True)


# ── 批量加载 ──────────────────────────────────────────────

def load_all() -> dict[str, pd.DataFrame]:
    """读取 EXCEL_SOURCES 中所有配置的 Excel，返回 {name: DataFrame}。

    新增 Excel 只需在 config.py 注册，本函数自动包含。
    """
    loaders = {
        "activity": load_activity,
        "store": load_stores,
    }
    result: dict[str, pd.DataFrame] = {}
    for name in EXCEL_SOURCES:
        if name in loaders:
            result[name] = loaders[name]()
        else:
            result[name] = _read_excel(name)
    return result


def list_sources() -> list[str]:
    """返回当前配置的所有 Excel 数据源名称。"""
    return list(EXCEL_SOURCES.keys())


# ── 清洗辅助 ──────────────────────────────────────────────

def _clean_numeric(df: pd.DataFrame) -> None:
    for col in NUMERIC_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _clean_dates(df: pd.DataFrame) -> None:
    for col in DATE_FIELDS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")


def _strip_strings(df: pd.DataFrame) -> None:
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})


if __name__ == "__main__":
    print("已配置数据源:", list_sources())
    for name, df in load_all().items():
        print(f"  {name}: {len(df)} 条, {df.shape[1]} 列")
