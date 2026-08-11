"""共享查询工具：过滤器构建 + 标准JSON响应 + DB查询。"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
from flask import request, jsonify
from sqlalchemy import create_engine, text


_DB_URL = None
_engine = None


def _get_engine():
    global _engine, _DB_URL
    if _engine is None:
        from config import PROJECT_ROOT
        _DB_URL = f"sqlite:///{PROJECT_ROOT / 'database' / 'offline_activity.db'}"
        _engine = create_engine(_DB_URL, echo=False)
    return _engine


def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """执行 SQL 返回 DataFrame。"""
    return pd.read_sql_query(text(sql), _get_engine(), params=params or {})


def query_scalar(sql: str, params: dict | None = None):
    with _get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def build_filters(args=None, table_alias: str = "f", join_store: bool = False) -> tuple[str, dict]:
    """从请求参数构建 WHERE 子句。

    支持筛选：date, quarter, month, region, dealer, store, activity_type, product_line
    join_store=True 时 region 从 dim_store 取（需要 JOIN）。
    """
    if args is None:
        args = request.args
    conds = []
    params: dict = {}

    if args.get("date"):
        conds.append(f"date({table_alias}.activity_date) = :date")
        params["date"] = args["date"]
    if args.get("quarter"):
        conds.append(f"{table_alias}.quarter_name = :quarter")
        params["quarter"] = args["quarter"]
    if args.get("month"):
        conds.append(f"{table_alias}.year_month = :month")
        params["month"] = args["month"]
    if args.get("dealer"):
        conds.append(f"{table_alias}.dealer = :dealer")
        params["dealer"] = args["dealer"]
    if args.get("store"):
        conds.append(f"{table_alias}.store_name = :store")
        params["store"] = args["store"]
    if args.get("activity_type"):
        conds.append(f"{table_alias}.activity_type = :activity_type")
        params["activity_type"] = args["activity_type"]
    if args.get("region"):
        if join_store:
            conds.append("s.region = :region")
        else:
            conds.append(f"{table_alias}.region = :region")
        params["region"] = args["region"]
    if args.get("business_category"):
        conds.append(f"{table_alias}.business_category = :business_category")
        params["business_category"] = args["business_category"]

    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def build_product_filter(args=None, table_alias: str = "f") -> tuple[str, dict]:
    """产品线筛选（用于关联表查询）。"""
    if args is None:
        args = request.args
    conds = []
    params: dict = {}
    if args.get("product_line"):
        conds.append(f"{table_alias}.product_line = :product_line")
        params["product_line"] = args["product_line"]
    where = (" AND " + " AND ".join(conds)) if conds else ""
    return where, params


def json_response(df: pd.DataFrame, **extra) -> "flask.Response":
    """标准 JSON 响应：{data: [...], ...extra}，处理 NaN/Inf。"""
    df = df.replace([np.inf, -np.inf], None)
    df = df.where(pd.notnull(df), None)
    records = df.to_dict("records")
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.floating,)):
                if math.isnan(v):
                    rec[k] = None
                else:
                    rec[k] = float(v)
            elif isinstance(v, pd.Timestamp):
                rec[k] = v.isoformat()
    return jsonify({"data": records, **extra})


def json_single(data: dict, **extra) -> "flask.Response":
    """单对象响应。"""
    return jsonify({"data": data, **extra})
