"""导出独立 HTML 看板：将所有 API 数据嵌入模板，无需服务器即可打开。"""
from __future__ import annotations
import json, urllib.request, os
from pathlib import Path

BASE = "http://127.0.0.1:8080"
TEMPLATE = Path(__file__).parent / "web" / "templates" / "index.html"
OUTPUT = Path(__file__).parent.parent / "output" / "线下活动经营分析看板_独立版.html"

# All API endpoints the template calls
ENDPOINTS = {
    "overview": "/api/overview",
    "activity_by_type": "/api/activity/by_type",
    "activity_trend": "/api/activity/trend",
    "stores": "/api/stores?page=1&size=500",
    "dealers": "/api/dealers",
    "products": "/api/products",
    "regions": "/api/regions",
    "provinces": "/api/provinces",
    "diagnostics": "/api/diagnostics",
    "excellent": "/api/excellent",
    "insights": "/api/insights",
    "analysis_daily": "/api/analysis/daily",
    "analysis_weekly": "/api/analysis/weekly",
    "analysis_monthly": "/api/analysis/monthly",
    "review_q2": "/api/review/q2",
    "review_luna": "/api/review/luna",
    "channel_comparison": "/api/channel/comparison",
    "channel_drone": "/api/channel/drone",
    "channel_brands": "/api/channel/brands",
    "funnel": "/api/funnel",
    "scores_stores": "/api/scores/stores?page=1&size=500",
    "scores_dealers": "/api/scores/dealers",
    "scores_regions": "/api/scores/regions",
    "scores_activities": "/api/scores/activities?page=1&size=100",
    "product_type_cross": "/api/product/type_cross",
    "product_monthly": "/api/product/monthly",
    "type_month_cross": "/api/type/month_cross",
    "trend_monthly_multi": "/api/trend/monthly_multi",
    "filter_options": "/api/filter_options",
}


def fetch(url: str) -> dict:
    try:
        with urllib.request.urlopen(f"{BASE}{url}", timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  WARN: {url} -> {e}")
        return {"error": str(e), "data": []}


def export():
    print("=" * 60)
    print("导出独立 HTML 看板...")
    print("=" * 60)

    # 1. Fetch all API data
    api_data = {}
    for key, ep in ENDPOINTS.items():
        print(f"  拉取 {key}...", end=" ")
        api_data[key] = fetch(ep)
        size = len(json.dumps(api_data[key], ensure_ascii=False, default=str))
        print(f"{size:,} bytes")

    # 2. Read template
    html = TEMPLATE.read_text(encoding="utf-8")

    # 3. Embed data as global variable
    json_str = json.dumps(api_data, ensure_ascii=False, default=str)
    embed_script = f'<script>window.__STANDALONE_DATA__ = {json_str};</script>'

    # 4. Replace fetchJSON with standalone version
    # Original: async function fetchJSON(url) { return fetch(url).then(r => r.json()); }
    # New: returns from embedded data
    old_fetch = "async function fetchJSON(url) {\n    const r = await fetch(url);\n    if (!r.ok) throw new Error('API error: ' + r.status);\n    return r.json();\n  }"
    new_fetch = """async function fetchJSON(url) {
    // Standalone mode: return from embedded data
    var map = {
      '/api/overview': window.__STANDALONE_DATA__.overview,
      '/api/activity/by_type': window.__STANDALONE_DATA__.activity_by_type,
      '/api/activity/trend': window.__STANDALONE_DATA__.activity_trend,
      '/api/dealers': window.__STANDALONE_DATA__.dealers,
      '/api/products': window.__STANDALONE_DATA__.products,
      '/api/regions': window.__STANDALONE_DATA__.regions,
      '/api/provinces': window.__STANDALONE_DATA__.provinces,
      '/api/diagnostics': window.__STANDALONE_DATA__.diagnostics,
      '/api/excellent': window.__STANDALONE_DATA__.excellent,
      '/api/insights': window.__STANDALONE_DATA__.insights,
      '/api/insights/summary': {data: (window.__STANDALONE_DATA__.insights.summary||[])},
      '/api/insights/recommendations': {data: (window.__STANDALONE_DATA__.insights.recommendations||[])},
      '/api/analysis/daily': window.__STANDALONE_DATA__.analysis_daily,
      '/api/analysis/weekly': window.__STANDALONE_DATA__.analysis_weekly,
      '/api/analysis/monthly': window.__STANDALONE_DATA__.analysis_monthly,
      '/api/review/q2': window.__STANDALONE_DATA__.review_q2,
      '/api/review/luna': window.__STANDALONE_DATA__.review_luna,
      '/api/channel/comparison': window.__STANDALONE_DATA__.channel_comparison,
      '/api/channel/drone': window.__STANDALONE_DATA__.channel_drone,
      '/api/channel/brands': window.__STANDALONE_DATA__.channel_brands,
      '/api/funnel': window.__STANDALONE_DATA__.funnel,
      '/api/scores/regions': window.__STANDALONE_DATA__.scores_regions,
      '/api/filter_options': window.__STANDALONE_DATA__.filter_options,
    };
    // Handle paginated endpoints
    if (url.startsWith('/api/stores')) return window.__STANDALONE_DATA__.stores;
    if (url.startsWith('/api/scores/stores')) return window.__STANDALONE_DATA__.scores_stores;
    if (url.startsWith('/api/scores/activities')) return window.__STANDALONE_DATA__.scores_activities;
    if (url.startsWith('/api/scores/dealers')) return window.__STANDALONE_DATA__.scores_dealers;
    if (url.startsWith('/api/product/type_cross')) return window.__STANDALONE_DATA__.product_type_cross;
    if (url.startsWith('/api/product/monthly')) return window.__STANDALONE_DATA__.product_monthly;
    if (url.startsWith('/api/type/month_cross')) return window.__STANDALONE_DATA__.type_month_cross;
    if (url.startsWith('/api/trend/monthly_multi')) return window.__STANDALONE_DATA__.trend_monthly_multi;
    if (url.startsWith('/api/snapshot')) return window.__STANDALONE_DATA__.overview;
    // Fallback: try exact match
    if (map[url]) return map[url];
    console.warn('Standalone mode: no data for', url);
    return {data: [], error: 'standalone mode: endpoint not cached'};
  }"""

    # Try to replace the original fetchJSON
    if old_fetch in html:
        html = html.replace(old_fetch, new_fetch)
        print("  fetchJSON replaced (exact match)")
    else:
        # Find and replace the fetchJSON function by regex
        import re
        pattern = r'async function fetchJSON\(url\)\s*\{[^}]*\}'
        match = re.search(pattern, html)
        if match:
            html = html[:match.start()] + new_fetch + html[match.end():]
            print("  fetchJSON replaced (regex match)")
        else:
            print("  WARNING: could not find fetchJSON to replace")
            # Inject before the first script that uses it
            html = html.replace('<script>', embed_script + '\n<script>', 1)
            return _save(html, embed_script)

    # 5. Inject embedded data before closing </head>
    html = html.replace('</head>', embed_script + '\n</head>')

    # 6. Add standalone banner
    banner = '<div style="background:#f59e0b;color:#fff;padding:6px 16px;font-size:12px;text-align:center">独立版看板 · 数据快照时间: ' + \
             json.loads(json_str).get('overview',{}).get('total_activities','?') if False else '' + \
             ' · 数据不会实时更新</div>'
    # Simpler banner
    from datetime import datetime
    banner = f'<div style="background:#f59e0b;color:#1e293b;padding:6px 16px;font-size:12px;text-align:center;font-weight:600">独立版看板 · 数据快照: {datetime.now().strftime("%Y-%m-%d %H:%M")} · 此页面数据不会实时更新</div>'
    html = html.replace('<div class="main">', banner + '<div class="main">')

    return _save(html, None)


def _save(html: str, embed_script: str) -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if embed_script and embed_script not in html:
        html = html.replace('</head>', embed_script + '\n</head>')
    OUTPUT.write_text(html, encoding="utf-8")
    size_mb = OUTPUT.stat().st_size / 1024 / 1024
    print(f"\n  输出: {OUTPUT}")
    print(f"  大小: {size_mb:.1f} MB")
    print(f"  打开方式: 双击文件或用浏览器打开 file://{OUTPUT}")
    return OUTPUT


if __name__ == "__main__":
    export()
