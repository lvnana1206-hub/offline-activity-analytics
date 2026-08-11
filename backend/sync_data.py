"""数据同步入口：读取本地 Excel -> 构建统一业务数据模型。

工作流：
  1. 从 data/raw/ 读取活动总池 + 专卖店信息表
  2. 构建 fact_activity / dim_store / dim_dealer / merged_activity_store
  3. 返回完整数据模型 + 质量报告

刷新流程：覆盖 data/raw/ 下的 Excel 后运行本模块即可。
"""

from __future__ import annotations

from datetime import datetime

from .data_model import build_all_models


def sync_all() -> dict:
    """读取本地 Excel 并构建统一业务数据模型。"""
    print("=" * 60)
    print("数据同步开始（本地 Excel）")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"数据源: data/raw/")
    print("=" * 60)

    models = build_all_models()

    meta = {
        "source": "excel",
        "sync_time": datetime.now().isoformat(timespec="seconds"),
        "activity_count": len(models["fact_activity"]),
        "store_count": len(models["dim_store"]),
        "dealer_count": len(models["dim_dealer"]),
        "match_rate": models["quality"]["match_rate"],
    }
    models["meta"] = meta

    print(f"\n同步完成: 活动 {meta['activity_count']} 条, "
          f"门店 {meta['store_count']} 家, "
          f"匹配率 {meta['match_rate']:.1%}")
    return models


if __name__ == "__main__":
    result = sync_all()
    merged = result["merged_activity_store"]
    print(f"\nmerged_activity_store: {merged.shape}")
    print(f"列名: {list(merged.columns)}")
    print(f"\n数据质量: {result['quality']}")
