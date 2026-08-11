"""全链路编排脚本。

执行顺序：
  1. 加载数据 -> 2. 构建数据模型 -> 3. 计算指标 -> 4. 运行诊断
  5. 导出全部结果到 output/
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from datetime import datetime

import pandas as pd

from .data_model import build_all_models
from .metrics import compute_all_metrics
from .diagnostics import run_full_diagnosis
from .scoring import compute_all_scores
from .insight_engine import get_engine_insight
from .rules_engine import get_engine as get_rules_engine
from .config import OUTPUT_DIR


def export_to_excel(models: dict, metrics: dict, diagnosis: dict) -> Path:
    """导出所有数据模型和指标到 Excel。"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = OUTPUT_DIR / f"analysis_result_{timestamp}.xlsx"

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # 数据模型
        models["merged_activity_store"].to_excel(writer, sheet_name="merged_activity_store", index=False)
        models["dim_store"].to_excel(writer, sheet_name="dim_store", index=False)
        models["dim_dealer"].to_excel(writer, sheet_name="dim_dealer", index=False)
        models["dim_employee"].to_excel(writer, sheet_name="dim_employee", index=False)

        # 指标
        # activity_overview 是 dict，转为 DataFrame
        pd.DataFrame([metrics["activity_overview"]]).to_excel(
            writer, sheet_name="activity_overview", index=False
        )
        metrics["activity_by_type"].to_excel(writer, sheet_name="activity_by_type", index=False)
        metrics["activity_monthly_trend"].to_excel(writer, sheet_name="monthly_trend", index=False)
        metrics["store_metrics"].to_excel(writer, sheet_name="store_metrics", index=False)
        metrics["dealer_metrics"].to_excel(writer, sheet_name="dealer_metrics", index=False)
        metrics["product_metrics"].to_excel(writer, sheet_name="product_metrics", index=False)
        metrics["region_metrics"].to_excel(writer, sheet_name="region_metrics", index=False)
        metrics["province_metrics"].to_excel(writer, sheet_name="province_metrics", index=False)

        # 诊断
        for name, items in diagnosis.items():
            if isinstance(items, list) and len(items) > 0:
                pd.DataFrame(items).to_excel(writer, sheet_name=f"diag_{name}"[:31], index=False)

        # 评分体系
        scores["store_scores"].to_excel(writer, sheet_name="store_scores", index=False)
        scores["dealer_scores"].to_excel(writer, sheet_name="dealer_scores", index=False)
        scores["region_scores"].to_excel(writer, sheet_name="region_scores", index=False)

        # 洞察引擎
        for name in ["summary", "problems", "opportunities", "risks", "recommendations", "replication"]:
            items = insights.get(name, [])
            if isinstance(items, list) and len(items) > 0:
                pd.DataFrame(items).to_excel(writer, sheet_name=f"insight_{name}"[:31], index=False)

    return filepath


def export_diagnosis_report(diagnosis: dict) -> Path:
    """导出诊断文本报告。"""
    filepath = OUTPUT_DIR / "diagnosis_report.txt"
    lines = [
        "=" * 60,
        "中国区专卖店线下活动经营分析 - 诊断报告",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
    ]

    issue_count = 0
    for category, items in diagnosis.items():
        if not isinstance(items, list) or len(items) == 0:
            continue
        lines.append(f"\n{'─' * 40}")
        lines.append(f"[{category}] 共 {len(items)} 项")
        lines.append("─" * 40)

        for item in items[:20]:
            if isinstance(item, dict):
                desc = item.get("description", str(item))
                severity = item.get("severity", "")
                lines.append(f"  [{severity.upper()}] {desc}")
            else:
                lines.append(f"  {item}")
        if len(items) > 20:
            lines.append(f"  ... 还有 {len(items) - 20} 项")
        issue_count += len(items)

    lines.append(f"\n{'=' * 60}")
    lines.append(f"诊断完成，共发现 {issue_count} 个问题/关注点")
    lines.append("=" * 60)

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def run_pipeline() -> dict:
    """执行全链路。"""
    print("=" * 60)
    print("中国区专卖店线下活动经营分析平台 - 全链路执行")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 构建数据模型
    models = build_all_models()

    # 2. 计算统一指标
    metrics = compute_all_metrics(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )

    # 3. 运行经营诊断
    diagnosis = run_full_diagnosis(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )

    # 4. 第五阶段：评分体系 + 洞察引擎
    scores = compute_all_scores(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
    )
    insights = get_engine_insight().generate_insights(
        models["merged_activity_store"],
        models["dim_store"],
        models["dim_dealer"],
        scores,
    )

    # 5. 导出结果
    print("\n导出结果...")
    excel_path = export_to_excel(models, metrics, diagnosis)
    print(f"  Excel: {excel_path}")

    report_path = export_diagnosis_report(diagnosis)
    print(f"  诊断报告: {report_path}")

    print("\n" + "=" * 60)
    print("全链路执行完成")
    print("=" * 60)

    return {
        "models": models,
        "metrics": metrics,
        "diagnosis": diagnosis,
        "scores": scores,
        "insights": insights,
        "excel_path": str(excel_path),
        "report_path": str(report_path),
    }


if __name__ == "__main__":
    result = run_pipeline()
