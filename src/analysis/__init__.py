"""经营分析引擎 (Business Analysis Engine)。

按 spec 要求建立 analysis/ 包，包含四个周期分析模块：
  - daily_analysis.py     每日经营分析
  - weekly_analysis.py    每周经营分析
  - monthly_analysis.py   每月经营分析
  - quarterly_analysis.py 季度经营复盘
  - realtime_quarterly.py 季度实时追踪

每个模块统一输出三层结构：
  data            经营数据
  findings        经营结论（发现 / 原因 / 影响）
  recommendations 经营建议（下一步怎么办）
"""

from .daily_analysis import daily_analysis
from .weekly_analysis import weekly_analysis
from .monthly_analysis import monthly_analysis
from .quarterly_analysis import quarterly_analysis, luna_analysis
from .realtime_quarterly import realtime_quarterly_analysis

__all__ = [
    "daily_analysis",
    "weekly_analysis",
    "monthly_analysis",
    "quarterly_analysis",
    "luna_analysis",
    "realtime_quarterly_analysis",
]
