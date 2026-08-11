"""ETL 管线：Excel -> Data Model -> SQLite。

流程：
  1. data_loader 读取 data/raw/ 下的 Excel
  2. backend.data_model 构建统一业务数据模型
  3. 写入 offline_activity.db（upsert，可重复执行）

用法: python etl_pipeline.py [--drop]
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, date
import json

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, select, text, Float as SAFloat, Boolean as SABool
from sqlalchemy.orm import Session

# 项目根目录
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import ensure_dirs, REPORTS_DIR, ACTIVITY_COLUMNS
from data_loader import load_activity, load_stores
from backend.data_model import build_all_models
from backend.model_utils import detect_product_columns
from database.models import (
    Base, DimDate, DimStore, DimDealer, DimProduct,
    FactActivity, FactActivityProduct,
)
from database.database_init import get_engine, init_database, DB_PATH


# ── 日志 ──────────────────────────────────────────────────

class ETLLog:
    def __init__(self):
        self.lines: list[str] = []
        self._t0 = datetime.now()

    def log(self, msg: str):
        ts = (datetime.now() - self._t0).total_seconds()
        line = f"[{ts:7.1f}s] {msg}"
        self.lines.append(line)
        print(line)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines), encoding="utf-8")


# ── 类型清洗 ──────────────────────────────────────────────

def _coerce_float_columns(df: pd.DataFrame, model_cls) -> pd.DataFrame:
    """将 ORM 模型中声明为 Float 的列强制转为 numeric，无法转换的设为 None。"""
    float_cols = [c.name for c in model_cls.__table__.columns if isinstance(c.type, SAFloat)]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def _coerce_bool_columns(df: pd.DataFrame, model_cls) -> pd.DataFrame:
    """将 ORM 模型中声明为 Boolean 的列转为 Python bool。"""
    bool_cols = [c.name for c in model_cls.__table__.columns if isinstance(c.type, SABool)]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(bool)
    return df


# ── 日期维度构建 ──────────────────────────────────────────

def build_dim_date(fact: pd.DataFrame) -> list[dict]:
    """从活动日期范围生成 dim_date 记录。"""
    dates = pd.to_datetime(fact["activity_date"], errors="coerce").dropna()
    if dates.empty:
        return []
    end_date = pd.Timestamp(date.today())
    start = dates.min().normalize()
    all_dates = pd.date_range(start=start, end=end_date, freq="D")

    records = []
    for d in all_dates:
        iso = d.isocalendar()
        records.append({
            "date": d.to_pydatetime(),
            "year": d.year,
            "quarter": d.quarter,
            "month": d.month,
            "week": int(iso.week),
            "weekday": d.dayofweek + 1,
            "year_month": d.strftime("%Y-%m"),
            "year_week": f"{iso.year}W{iso.week}",
            "quarter_name": f"{d.year}Q{d.quarter}",
            "is_holiday": d.dayofweek >= 5,
        })
    return records


# ── 产品维度构建 ──────────────────────────────────────────

def build_dim_product(fact: pd.DataFrame) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """自动扫描产品列，生成 dim_product 记录。

    返回 (records, {产品线名: product_id}, {英文列名: 产品线名})。
    """
    product_cols: dict[str, str] = {}
    for cn, en in ACTIVITY_COLUMNS.items():
        if cn.endswith("销量"):
            product_cols[en] = cn.replace("销量", "")
    for col in fact.columns:
        if isinstance(col, str) and col.endswith("销量") and col not in product_cols:
            product_cols[col] = col.replace("销量", "")

    records = []
    name_to_id = {}
    for i, (col, name) in enumerate(sorted(product_cols.items())):
        pid = f"PR{i:03d}"
        name_to_id[name] = pid
        records.append({
            "product_id": pid,
            "product_line": name,
            "source_column": col,
            "first_seen": datetime.now(),
        })
    return records, name_to_id, product_cols


# ── 活动-产品关联构建 ──────────────────────────────────────

def build_fact_activity_product(
    fact: pd.DataFrame, name_to_id: dict[str, str], product_cols: dict[str, str]
) -> list[dict]:
    """从产品销量列展开为关联表记录。"""
    records = []
    for _, row in fact.iterrows():
        aid = row["activity_id"]
        for col, name in product_cols.items():
            if col not in fact.columns:
                continue
            v = pd.to_numeric(row.get(col), errors="coerce")
            if v is not None and pd.notna(v) and float(v) > 0:
                pid = name_to_id.get(name)
                if pid:
                    records.append({
                        "activity_id": aid,
                        "product_id": pid,
                        "product_line": name,
                        "sales_qty": float(v),
                    })
    return records


# ── upsert 工具 ───────────────────────────────────────────

def _upsert_table(session: Session, model_cls, records: list[dict],
                  pk_col: str, log: ETLLog, label: str):
    """通用 upsert：按主键存在则更新，不存在则插入。"""
    if not records:
        log.log(f"{label}: 0 条（跳过）")
        return 0
    existing_ids = set(session.execute(
        select(getattr(model_cls, pk_col))
    ).scalars())

    new_count = 0
    update_count = 0
    batch = []
    for rec in records:
        pk_val = rec[pk_col]
        if pk_val in existing_ids:
            obj = session.get(model_cls, pk_val)
            for k, v in rec.items():
                if k != pk_col:
                    setattr(obj, k, v)
            update_count += 1
        else:
            batch.append(rec)
            new_count += 1
            if len(batch) >= 500:
                session.bulk_insert_mappings(model_cls, batch)
                batch.clear()

    if batch:
        session.bulk_insert_mappings(model_cls, batch)

    session.flush()
    log.log(f"{label}: 新增 {new_count} 条, 更新 {update_count} 条, 共 {len(records)} 条")
    return len(records)


def _upsert_auto_pk(session: Session, model_cls, records: list[dict],
                    unique_cols: list[str], log: ETLLog, label: str):
    """自增主键表的 upsert：按唯一组合去重。"""
    if not records:
        log.log(f"{label}: 0 条（跳过）")
        return 0
    existing = set()
    for r in session.execute(
        select(*[getattr(model_cls, c) for c in unique_cols])
    ):
        existing.add(tuple(r))

    new_records = []
    for rec in records:
        key = tuple(rec.get(c) for c in unique_cols)
        if key not in existing:
            new_records.append(rec)
            existing.add(key)

    if new_records:
        session.bulk_insert_mappings(model_cls, new_records)
    session.flush()
    log.log(f"{label}: 新增 {len(new_records)} 条, 跳过 {len(records) - len(new_records)} 条, 共 {len(records)} 条")
    return len(new_records)


# ── 主 ETL ────────────────────────────────────────────────

def run_etl(drop_first: bool = False) -> dict:
    """执行完整 ETL 管线。返回统计 dict。"""
    log = ETLLog()
    log.log("=" * 60)
    log.log("ETL 管线启动: Excel -> Data Model -> SQLite")
    log.log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.log("=" * 60)

    # 1. 初始化数据库
    if drop_first or not DB_PATH.exists():
        log.log("初始化数据库（重建表结构）...")
        init_database(drop_first=drop_first or not DB_PATH.exists())
    else:
        log.log("数据库已存在，使用 upsert 模式")

    engine = get_engine()

    # 2. 构建数据模型
    log.log("构建业务数据模型...")
    models = build_all_models()
    fact = models["fact_activity"]
    dim_store = models["dim_store"]
    dim_dealer = models["dim_dealer"]
    merged = models["merged_activity_store"]
    log.log(f"模型构建完成: 活动 {len(fact)}, 门店 {len(dim_store)}, 代理商 {len(dim_dealer)}")

    # 3. 写入数据库
    with Session(engine) as session:
        # dim_date
        date_records = build_dim_date(fact)
        _upsert_table(session, DimDate, date_records, "date", log, "dim_date")

        # dim_store
        store_df = dim_store.replace({np.nan: None}).copy()
        _coerce_float_columns(store_df, DimStore)
        store_records = store_df.to_dict("records")
        _upsert_table(session, DimStore, store_records, "store_id", log, "dim_store")

        # dim_dealer
        dealer_df = dim_dealer.replace({np.nan: None}).copy()
        _coerce_float_columns(dealer_df, DimDealer)
        dealer_records = dealer_df.to_dict("records")
        _upsert_table(session, DimDealer, dealer_records, "dealer_id", log, "dim_dealer")

        # dim_product（自动检测）
        product_records, name_to_id, product_cols = build_dim_product(fact)
        _upsert_table(session, DimProduct, product_records, "product_id", log, "dim_product")

        # fact_activity（从 merged 取，含 store_id 关联）
        merged_clean = merged.replace({np.nan: None}).copy()
        merged_clean = _coerce_float_columns(merged_clean, FactActivity)
        merged_clean = _coerce_bool_columns(merged_clean, FactActivity)
        merged_clean["product_lines"] = merged_clean["product_lines"].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, list) else "[]"
        )
        fact_records = merged_clean.to_dict("records")
        _upsert_table(session, FactActivity, fact_records, "activity_id", log, "fact_activity")

        # fact_activity_product
        fap_records = build_fact_activity_product(fact, name_to_id, product_cols)
        _upsert_auto_pk(session, FactActivityProduct, fap_records,
                        ["activity_id", "product_id"], log, "fact_activity_product")

        session.commit()

    # 4. 统计
    log.log("=" * 60)
    log.log("导入统计")
    log.log("=" * 60)
    stats = {}
    with Session(engine) as session:
        for model_cls, label in [
            (DimDate, "日期"), (DimStore, "门店"), (DimDealer, "代理商"),
            (DimProduct, "产品"), (FactActivity, "活动"),
            (FactActivityProduct, "活动-产品关联"),
        ]:
            cnt = session.execute(select(model_cls)).scalars().all()
            stats[label] = len(cnt)
            log.log(f"  {label}数量: {len(cnt)}")

        total_sales = session.execute(
            text("SELECT COALESCE(SUM(sales_clean),0) FROM fact_activity")
        ).scalar()
        match_rate = session.execute(text(
            "SELECT CAST(SUM(CASE WHEN store_id IS NOT NULL THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) FROM fact_activity"
        )).scalar()
        valid_count = session.execute(text(
            "SELECT COUNT(*) FROM fact_activity WHERE is_valid_activity = 1"
        )).scalar()
        log.log(f"  销售总额: {total_sales:,.0f} 元")
        log.log(f"  门店匹配率: {match_rate:.1%}")
        log.log(f"  有效活动: {valid_count} 条")

    # 5. 保存日志
    log_path = REPORTS_DIR / "etl_log.txt"
    log.save(log_path)
    log.log(f"\n日志已保存: {log_path}")

    return stats


if __name__ == "__main__":
    drop = "--drop" in sys.argv
    run_etl(drop_first=drop)
    print("\nETL 管线执行完成。")
    print(f"数据库: {DB_PATH}")
