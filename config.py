"""项目配置：路径与 Excel 文件注册表。

统一管理所有路径，不硬编码。新增 Excel 只需在 EXCEL_SOURCES 中添加配置。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

REPORTS_DIR = PROJECT_ROOT / "reports"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
OUTPUT_DIR = PROJECT_ROOT / "output"


EXCEL_SOURCES: dict[str, dict] = {
    "activity": {
        "filename": "活动总池.xlsx",
        "sheet": "Sheet1",
        "header_row": 0,
        "description": "飞书《线下活动管理》活动总池",
    },
    "store": {
        "filename": "专卖店信息表.xlsx",
        "sheet": "门店全量映射",
        "header_row": 0,
        "description": "飞书《YourCompany专卖店信息表》",
    },
}


def raw_path(name: str) -> Path:
    return RAW_DIR / EXCEL_SOURCES[name]["filename"]


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR, REPORTS_DIR, DASHBOARD_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


ACTIVITY_COLUMNS = {
    "活动简述": "activity_desc",
    "活动时间": "activity_date",
    "活动类型": "activity_type",
    "状态": "activity_status",
    "门店名称": "store_name",
    "代理商": "dealer",
    "店型归类": "store_category",
    "商型归类": "business_category",
    "门店类型": "store_type",
    "门店位置": "store_location",
    "门店状态": "store_status",
    "省份": "province",
    "城市": "city",
    "提报人": "reporter",
    "提出日期": "report_date",
    "店员": "staff_info",
    "店员数量": "staff_count",
    "是否长期合作": "long_term_coop",
    "参与人数": "participants",
    "企微添加": "wechat_adds",
    "相关转化销售": "conversion_sales_raw",
    "销售_原始": "sales_raw",
    "销售_清洗": "sales_clean",
    "转化主机数量": "converted_hosts",
    "当场成交率": "conversion_rate_pct",
    "无人机展示": "drone_display",
    "是否展示/体验做无人机": "drone_display",
    "无人机销量": "drone_sales",
    "无人机销售数量": "drone_sales",
    "无人机企微": "drone_wechat",
    "无人机企微客户添加数量": "drone_wechat",
    "我司承担活动费用预估": "activity_cost",
    "Luna销量": "luna_sales",
    "x系列销量": "x_series_sales",
    "Go系列销量": "go_series_sales",
    "Ace系列销量": "ace_series_sales",
    "活动费用": "activity_cost",
    "配件销售额": "accessories_sales_amount",
    "配件销售": "accessories_sales_qty",
    "活动来源": "activity_source",
    "场景标签": "scene_tags",
    "合作品牌": "partner_brands",
    "Mall店": "mall_store_ref",
    "Mall商": "mall_dealer_ref",
    "照材店": "camera_store_ref",
    "照材商": "camera_dealer_ref",
    "销售额异常": "sales_anomaly",
    "异常原因": "anomaly_reason",
    "记录ID": "record_id",
}

STORE_COLUMNS = {
    "门店名称": "store_name",
    "代理商": "dealer",
    "代理商_分货": "dealer_distribution",
    "门店类别(2)": "store_category",
    "省区单元": "province_unit",
    "区域": "region",
    "省份": "province",
    "城市": "city",
    "城市等级": "city_tier",
    "营业状态": "business_status",
    "状态": "store_status",
    "开业时间": "open_date",
    "闭店日期": "close_date",
    "门店等级(最终)": "store_level",
    "铺型": "shop_type",
    "商场等级": "mall_level",
    "面积": "area_sqm",
    "店内是否能试飞": "can_fly_indoor",
    "客户负责人(YourCompany)": "insta_manager",
    "运营负责人": "ops_manager",
    "代理商运营代表": "dealer_ops_rep",
    "飞书管理群": "feishu_group",
    "商场名称": "mall_name",
    "门店地址【包含省-市-区-街道-商场名-具体楼层】": "store_address",
    "店长": "store_manager",
    "店长电话": "manager_phone",
}

NUMERIC_FIELDS = [
    "participants", "wechat_adds", "sales_raw", "sales_clean",
    "converted_hosts", "conversion_rate_pct", "drone_sales",
    "luna_sales", "x_series_sales", "go_series_sales", "ace_series_sales",
    "activity_cost", "accessories_sales_amount", "accessories_sales_qty",
    "staff_count",
]

DATE_FIELDS = ["activity_date", "report_date"]

ACTIVITY_TYPE_CATEGORIES = {
    "异业合作": "跨界合作",
    "新品品鉴会": "新品推广",
    "workshop课堂": "教育培训",
    "外拍活动": "体验活动",
    "无人机专项": "产品专项",
    "其他类型": "其他",
    "异业合作-商场宣发资源置换": "跨界合作",
}

COMPLETED_STATUSES = ["已完成", "待评估"]


def is_completed(status) -> bool:
    return status in COMPLETED_STATUSES
