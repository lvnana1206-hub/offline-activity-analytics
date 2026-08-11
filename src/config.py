"""项目配置：路径与常量。"""

"""src 包兼容层：从根级 config.py 统一导入。

路径、字段映射、常量全部在根级 config.py 管理，此处仅做 re-export，
保证 src/ 现有代码的 `from .config import ...` 不受影响。
"""

import sys
from pathlib import Path

# 把项目根目录加入 sys.path 以便 import 根级 config
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import (  # noqa: E402,F401
    PROJECT_ROOT, DATA_DIR, RAW_DIR, PROCESSED_DIR,
    REPORTS_DIR, DASHBOARD_DIR, OUTPUT_DIR,
    EXCEL_SOURCES, raw_path, ensure_dirs,
    ACTIVITY_COLUMNS, STORE_COLUMNS,
    NUMERIC_FIELDS, DATE_FIELDS,
    ACTIVITY_TYPE_CATEGORIES,
    COMPLETED_STATUSES, is_completed,
)

# 兼容旧代码：ACTIVITY_FILE / STORE_FILE 指向 data/raw/
ACTIVITY_FILE = raw_path("activity")
STORE_FILE = raw_path("store")
