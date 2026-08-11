"""Flask API 服务层。

所有 HTML 页面未来只通过 API 获取数据，禁止前端计算业务指标。
启动: python backend/app.py
访问: http://127.0.0.1:8080
注意: 端口 5000 被 macOS AirPlay 占用，默认使用 8080。
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

from flask import Flask, jsonify, send_file
from sqlalchemy import create_engine, text
import numpy as np

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import PROJECT_ROOT, ensure_dirs, DASHBOARD_DIR

DB_PATH = PROJECT_ROOT / "database" / "offline_activity.db"
DB_URL = f"sqlite:///{DB_PATH}"
ETL_SCRIPT = PROJECT_ROOT / "etl_pipeline.py"


def create_app() -> Flask:
    """Application Factory：所有路由在内部注册。"""
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.url_map.strict_slashes = False

    # ── 基础路由 ──

    @app.route("/")
    def index():
        """根路径：服务看板页面。"""
        html = DASHBOARD_DIR / "index.html"
        if html.exists():
            return send_file(str(html))
        return jsonify({"error": "dashboard/index.html not found"}), 404

    @app.route("/api/health")
    def health():
        """健康检查：数据库状态。"""
        db_ok = DB_PATH.exists()
        db_tables = 0
        if db_ok:
            try:
                engine = create_engine(DB_URL)
                with engine.connect() as conn:
                    db_tables = conn.execute(
                        text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    ).scalar()
            except Exception:
                pass
        return jsonify({
            "status": "ok" if db_ok else "error",
            "database": str(DB_PATH),
            "database_exists": db_ok,
            "table_count": db_tables,
        })

    @app.route("/api/refresh", methods=["POST"])
    def refresh_data():
        """触发 ETL 管线：Excel -> Data Model -> SQLite。"""
        if not ETL_SCRIPT.exists():
            return jsonify({"ok": False, "error": f"ETL script not found: {ETL_SCRIPT}"}), 500
        try:
            result = subprocess.run(
                [sys.executable, str(ETL_SCRIPT)],
                capture_output=True, text=True, timeout=120,
                cwd=str(PROJECT_ROOT),
            )
            log_text = result.stdout + ("\n" + result.stderr if result.stderr else "")
            return jsonify({
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "log": log_text,
            })
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "ETL timeout (120s)"}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/export")
    def export_db():
        """导出清洗后的 SQLite 数据库文件。"""
        if not DB_PATH.exists():
            return jsonify({"error": "database not found"}), 404
        return send_file(
            str(DB_PATH),
            as_attachment=True,
            download_name="offline_activity_cleaned.db",
            mimetype="application/x-sqlite3",
        )

    @app.route("/api/feishu/status")
    def feishu_status():
        """飞书连接状态。"""
        from backend.feishu_client import test_connection
        ok = test_connection()
        return jsonify({
            "connected": ok,
            "message": "飞书已连接" if ok else "飞书未连接，请运行 lark-cli auth login",
        })

    @app.route("/api/feishu/sync", methods=["POST"])
    def feishu_sync():
        """从飞书拉取最新数据并同步到数据库。"""
        try:
            from backend.feishu_sync import sync_from_feishu
            result = sync_from_feishu()
            return jsonify({
                "ok": True,
                "data": result,
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/q3/status")
    def q3_status():
        """Q3 实时追踪数据（支持 business_category 筛选）。"""
        if not DB_PATH.exists():
            return jsonify({"error": "database not found"}), 404

        from flask import request
        bc = request.args.get("business_category", "")
        bc_cond = " AND business_category = :bc" if bc else ""
        bc_params = {"bc": bc} if bc else {}

        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            # Q3 概览
            overview = conn.execute(text(f"""
                SELECT
                    COUNT(*) AS activity_count,
                    SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN activity_status = '待评估' THEN 1 ELSE 0 END) AS pending,
                    COALESCE(ROUND(SUM(sales_clean),0),0) AS total_sales,
                    COALESCE(ROUND(SUM(wechat_adds),0),0) AS total_wechat,
                    COALESCE(ROUND(SUM(participants),0),0) AS total_participants,
                    COALESCE(ROUND(SUM(converted_hosts),0),0) AS total_hosts,
                    COUNT(DISTINCT store_id) AS active_stores,
                    COUNT(DISTINCT dealer) AS active_dealers,
                    SUM(CASE WHEN is_drone_activity = 1 THEN 1 ELSE 0 END) AS drone_activities,
                    ROUND(CAST(SUM(CASE WHEN activity_status IN ('已完成','待评估') THEN 1 ELSE 0 END) AS FLOAT)
                        / NULLIF(COUNT(*),0) * 100, 1) AS completion_rate
                FROM fact_activity WHERE quarter_name = '2026Q3'{bc_cond}
            """), bc_params).mappings().first()

            # Q3 逐周
            weekly = conn.execute(text(f"""
                SELECT year_week, COUNT(*) AS cnt,
                    COALESCE(ROUND(SUM(sales_clean),0),0) AS sales,
                    COALESCE(ROUND(SUM(wechat_adds),0),0) AS wechat,
                    COALESCE(ROUND(SUM(participants),0),0) AS participants
                FROM fact_activity WHERE quarter_name = '2026Q3'{bc_cond}
                GROUP BY year_week ORDER BY year_week
            """), bc_params).mappings().all()

            # Q3 按类型
            by_type = conn.execute(text(f"""
                SELECT activity_type, COUNT(*) AS cnt,
                    COALESCE(ROUND(SUM(sales_clean),0),0) AS sales
                FROM fact_activity WHERE quarter_name = '2026Q3'{bc_cond}
                GROUP BY activity_type ORDER BY cnt DESC
            """), bc_params).mappings().all()

            # Q3 按区域
            by_region = conn.execute(text(f"""
                SELECT s.region, COUNT(*) AS cnt,
                    COALESCE(ROUND(SUM(f.sales_clean),0),0) AS sales
                FROM fact_activity f JOIN dim_store s ON f.store_id = s.store_id
                WHERE f.quarter_name = '2026Q3'{bc_cond.replace("business_category", "f.business_category")}
                GROUP BY s.region ORDER BY cnt DESC
            """), bc_params).mappings().all()

            # Q3 代理商 Top5
            top_dealers = conn.execute(text(f"""
                SELECT dealer, COUNT(*) AS cnt,
                    COALESCE(ROUND(SUM(sales_clean),0),0) AS sales
                FROM fact_activity WHERE quarter_name = '2026Q3'{bc_cond}
                GROUP BY dealer ORDER BY sales DESC LIMIT 5
            """), bc_params).mappings().all()

        def to_dict(row):
            d = dict(row)
            for k, v in d.items():
                if isinstance(v, (np.integer,)):
                    d[k] = int(v)
                elif isinstance(v, (np.floating,)):
                    d[k] = float(v) if not np.isnan(v) else None
            return d

        return jsonify({"data": {
            **to_dict(overview),
            "weekly": [to_dict(r) for r in weekly],
            "by_type": [to_dict(r) for r in by_type],
            "by_region": [to_dict(r) for r in by_region],
            "top_dealers": [to_dict(r) for r in top_dealers],
        }})

    # ── Blueprint 路由 ──

    from api import (
        dashboard_bp, activity_bp, store_bp,
        dealer_bp, product_bp, insight_bp,
        compat_bp,
    )
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(activity_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(dealer_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(insight_bp)
    app.register_blueprint(compat_bp)

    return app


# 模块级 app 实例（供 wsgi / test_client 使用）
app = create_app()


def run(host: str = "127.0.0.1", port: int = 8080):
    """启动 Flask 服务。"""
    ensure_dirs()
    print("=" * 50)
    print("Server running:")
    print(f"  http://{host}:{port}")
    print(f"  Health: http://{host}:{port}/api/health")
    print(f"  Dashboard: http://{host}:{port}/")
    print(f"  Database: {DB_PATH}")
    print("=" * 50)
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
