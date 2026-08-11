# Offline Activity Analytics Platform

A comprehensive business analytics platform for retail offline activity management, built with Flask + ECharts. Designed for retail operations teams to track, analyze, and optimize offline marketing activities across store networks.

## Features

### 15 Analysis Pages
- **Overview Dashboard** - 8 KPI cards, trend charts, activity type distribution, regional ranking
- **Daily / Weekly / Monthly Analysis** - Time-based operational insights with findings and recommendations
- **Activity Analysis** - By type, with effectiveness metrics and full data tables
- **Store Analysis** - Store-level performance with scoring (A/B/C/D grades)
- **Dealer Analysis** - Dealer rankings with coverage rates and scatter plots
- **Product Analysis** - Product line performance, cross-matrix heatmaps, monthly trends
- **Region Analysis** - Province-level sales contribution and activity distribution
- **Channel Analysis** - Mall stores vs camera stores, drone vs non-drone, cross-brand partnerships
- **Efficiency Metrics** - Relative value indicators (per-activity, per-participant, conversion rates)
- **Business Diagnosis** - Automated problem detection and recommendations
- **Excellent Cases** - Top activity showcases with replication suggestions
- **Q2 Review** - 10-section quarterly business review with charts and conclusions
- **Luna Launch Review** - Pre/post launch comparison and product-specific analysis
- **Quarterly Tracker** - Real-time quarterly progress tracking

### Data Architecture
- **Data Source**: Feishu (Lark) Bitable API via `lark-cli`
- **Backend**: Flask with 30+ API endpoints
- **Frontend**: Single-page app with ECharts 5.5.0
- **Metrics Layer**: Unified metrics center, all calculations server-side
- **Scoring System**: 4-dimensional activity/store/dealer/region scoring model

### Key Metrics
- Activity count, completion rate, total sales
- Per-activity efficiency: sales/activity, participants/activity, wechat/activity
- Conversion rates: wechat add rate, host conversion rate
- Per-unit economics: sales per participant, sales per host
- Coverage: store coverage rate, dealer coverage rate
- Health score: effective activity ratio

## Project Structure

```
offline-activity-analytics/
├── src/
│   ├── web/
│   │   ├── app.py              # Flask application (30+ API endpoints)
│   │   └── templates/
│   │       └── index.html      # SPA frontend (15 pages, ECharts)
│   ├── feishu_loader.py        # Feishu Bitable data loader
│   ├── data_model.py           # Data model builder
│   ├── metrics.py              # Unified metrics computation
│   ├── metrics_center.py       # Metrics center (singleton)
│   ├── scoring.py              # 4D scoring system
│   ├── review_engine.py        # Quarterly review engine
│   ├── insight_engine.py       # Business insight engine
│   ├── channel_metrics.py      # Channel/drone/brand analysis
│   ├── filter_engine.py        # Global filter system
│   ├── diagnostics.py          # Automated diagnosis
│   ├── analysis/               # Daily/weekly/monthly/quarterly analysis
│   ├── brand_analysis.py       # Cross-brand partnership analysis
│   ├── export_standalone.py    # Export standalone HTML (no server needed)
│   ├── weekly_push.py          # Weekly report push to Feishu
│   └── monthly_push.py         # Monthly report push to Feishu
├── backend/                    # Alternative SQLite-based backend
├── api/                        # API layer modules
├── scoring/                    # Scoring sub-modules
├── metrics/                    # Metrics sub-modules
├── analysis/                   # Analysis sub-modules
├── config.py                   # Project configuration
├── requirements.txt
└── start_platform.sh           # Server startup script
```

## Quick Start

### Prerequisites
- Python 3.10+
- [lark-cli](https://github.com/larksuite/lark-cli) (for Feishu data access)

### Installation

```bash
pip install -r requirements.txt

# Configure Feishu credentials
# Edit src/feishu_loader.py:
#   BASE_TOKEN = "your_feishu_base_token"
#   TABLE_ID = "your_feishu_table_id"

# Authenticate with lark-cli
lark-cli auth login
```

### Run the Platform

```bash
# Start the server
python -m src.web.app

# Access at http://127.0.0.1:8080/
```

### Export Standalone HTML

```bash
# Generate a standalone HTML file with embedded data (no server needed)
python -m src.export_standalone
# Output: output/standalone_dashboard.html
```

## Configuration

All sensitive configurations use placeholder values:

| Config | Location | Description |
|--------|----------|-------------|
| `BASE_TOKEN` | `src/feishu_loader.py` | Feishu Bitable base token |
| `TABLE_ID` | `src/feishu_loader.py` | Feishu Bitable table ID |
| `DEFAULT_CHAT_ID` | `src/weekly_push.py` | Feishu group chat ID for reports |

Replace `YOUR_FEISHU_BASE_TOKEN`, `YOUR_FEISHU_TABLE_ID`, and `YOUR_FEISHU_CHAT_ID` with your actual values.

## Tech Stack

- **Backend**: Flask, Pandas, NumPy
- **Frontend**: Vanilla JS, ECharts 5.5.0
- **Data Source**: Feishu (Lark) Bitable API
- **Charts**: Bar, Line, Pie, Scatter, Radar, Heatmap, Funnel
- **Architecture**: API-driven SPA, server-side metrics computation

## License

This project is for internal use. Please do not commit real business data.
