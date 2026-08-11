"""指标层：所有指标统一读取 offline_activity.db。"""
from .db import get_engine, query, scalar, DB_PATH
