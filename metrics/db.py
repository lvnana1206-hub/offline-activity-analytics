"""共享数据库连接：所有 metrics 模块通过本模块访问 offline_activity.db。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "database" / "offline_activity.db"
DB_URL = f"sqlite:///{DB_PATH}"

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, echo=False)
    return _engine


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """执行 SQL 查询，返回 DataFrame。"""
    return pd.read_sql_query(text(sql), get_engine(), params=params or {})


def scalar(sql: str, params: dict | None = None):
    """执行 SQL 查询，返回标量值。"""
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def get_session() -> Session:
    return Session(get_engine())
