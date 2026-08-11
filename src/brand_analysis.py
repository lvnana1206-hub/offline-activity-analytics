"""异业合作品牌分析引擎。

品牌大类 -> 具体品牌 -> 活动明细，多维度下钻。
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import datetime
import re

from .analysis.common import safe_num

# ── 品牌大类映射 ──────────────────────────────

BRAND_CATEGORY_MAP = {
    "车企出行": [
        "极氪","蔚来","理想","理想汽车","问界","AITO","aito","华为AITO","鸿蒙智行",
        "小米汽车","小米之家","宝马","BMW","bmw","路虎","长城","魏牌","魏派","长城魏派",
        "长城魏牌","智己","智己汽车","腾势","腾势汽车","小鹏","小鹏汽车","丰田","比亚迪",
        "特斯拉","Tesla","奥迪","Audi","smart","Smart","猛士","9号电动车","9号",
        "蔚来乐道","乐道","蔚来萤火虫","萤火虫","蔚来汽车","蔚来汽车人",
        "华为汽车","G-SHOCK×鸿蒙智行","绵阳建国汽车城","汽车城","建国汽车城",
        "汽车","车友","车队","卡丁车","商场卡丁车",
    ],
    "机车骑行": [
        "机车","摩托车","贝纳利","贝纳利摩托车","春风","竞峰","竞峰机车","北堡","北堡机车",
        "荣山寮","荣山寮摩托车","杜卡迪","ktm","ktm-金卡纳肄业","机车俱乐部",
        "小布","Brompton","brompton","崔克","Trek","TREK","捷安特","捷安特GINANT",
        "喜德盛","单车","小布自行车","小布Brompton","Brompton小布","brompton小布",
        "Brompton 小布折叠车","Brompton小布折叠自行车","崔克Trek自行车",
        "TREK公路自行车","brompton&gaga","Brompton 万豪酒店","昆cycle&explore Brompton",
        "而意","而意&佳明","骑趣视界","成都骑行吧","骑行","骑行社团",
    ],
    "运动户外": [
        "迪卡侬","hoka","HOKA","昂跑","凯乐石","可隆","北面","萨洛蒙","骆驼",
        "诺诗兰","brooks","lululemon","Lululemon","Nike","nike","耐克","李宁",
        "斐乐","Kappa","New Balance","滔博体育","匡威","堡狮龙","堡狮龙bossini",
        "波司登","锐力运动家","Outopia","outopia","MAIA","sanse","SPELIALIZED",
        "海德","wilson","Wilson","bossni","亚瑟士","GARMIN","佳明","佳明 GARMIN",
        "韶音","韶音SHOKZ","韶音耳机","SHOKZ","BrandA×BrandB×BrandC×BrandD",
        "HOKA GARMIN SHOKZ","YourCompany×亚瑟士×成都来士","亚瑟士 × YourCompany × BLT × 宇树",
        "跑步","跑步社团","跑团","徒步","攀岩","户外","户外运动","户外社团",
        "钓鱼","汇钓体育","船石湖艇钓基地","滑雪","滑雪俱乐部","浆板运动",
        "帆船赛","棒球","棒球比赛","海口海之星棒垒球俱乐部","网球","ATP网球俱乐部",
        "羽毛球","羽毛球馆","搜羽羽毛球俱乐部","淄博市张店区羽动羽毛球俱乐部",
        "淄博陶涛羽毛球俱乐部","当地羽毛球馆","健身房","MH健身房","源力悦体",
        "拉丁舞","上弦射箭馆","射击俱乐部","镭战大联盟","中山战鹰真人cs","商场cs",
        "熊马勇士少儿障碍挑战赛","熊猫勇士少儿障碍挑战赛","体育赛事组","赛事",
        "中国体育彩票杯","骑行社团","运动社团","运动品牌","汉马","攀岩",
        "桂林探索新境户外探险","OldFlowers滑板俱乐部","游侠客","弈力体育",
        "八喜","5freedoms","游乐园","骑趣视界",
    ],
    "科技数码": [
        "华为","华为荣耀","小米","荣耀","索尼","sony","苹果","联想","飞利浦",
        "卡西欧","美的","360","科技界","G-SHOCK","泰卓龙眼镜","远景智能科技有限公司",
        "小松山推","2026人工智能博览会","awe","IDG","精选配件","医院＋华为",
    ],
    "商业地产": [
        "商场","商场合作","万象汇商场","万象汇","青岛万象城","昆明恒隆广场",
        "A park商场","a park","菏泽佳和城商场","金华永盛购物广场","丹尼斯奥莱店",
        "丹尼斯超市","红星美凯龙","百脑汇","帕帕拉兹&天街商圈","悠唐皇冠假日",
        "青岛海尔洲际酒店","内江船石湖豪生温泉酒店","W2","A park",
    ],
    "潮玩娱乐": [
        "乐高","乐高授权专卖店","任天堂","三丽鸥","cosplay","明星","明星快闪",
        "明星活动","明星资源","王者荣耀","王者荣耀赛事主办方","王者荣耀全国大赛海口中心站漫展",
        "展览","秀场","音乐会","艺术节","环球嘉年华","鼓浪屿美院","深圳文博会",
        "五条由","爱丽丝","猫咖","星图犬盟","成都佰舜文化传媒有限责任公司",
    ],
    "餐饮生活": [
        "星巴克","GAGA","gaga","五粮液","八马茶业","九玖佰萃温养堂","边树水脚档",
        "菲仕乐","PENHALIGON'S（潘海利根）","潮宏基","dr钻戒","Dr.","雅诗兰黛",
        "SKG未来健康","慈瑞体检","茶山姑娘","膳武艾境",
    ],
    "金融保险": [
        "银行","交通银行","上海交通银行信用卡","广发银行","中国银行","visa",
        "中国邮储银行新疆分行上门购","中国邮储银行",
    ],
    "教育机构": [
        "高校","高校摄影展","摄影协会","摄影","英孚教育","东南大学","福建商学院",
        "上海建设管理职责技术学院","安防学院","宜昌无人机培训学校","荟商商学院",
        "成都青少年文化宫","佛山市顺德设计师协会","北京国枫(上海)律师事务所",
    ],
    "政企公共": [
        "企业合作","政企合作","政企联合","地产合作","上海市政府","杨浦检察院",
        "杨浦区中医医院","新疆米东区卡子湾社区卫生服务中心","新疆第三人民医院",
        "中心医院","医院","保健院","昆明市商务局","云南省广播电视台",
        "厦门开元街道工会","共青团成都市委员","旅游局","民营企业协会","通讯公司",
        "携程集团","众信旅游","滴滴","美团","天猫","苏宁","中免集团",
        "天虹纺织","沙湖公园","梧桐山","鼠山清野","毛棉杜鹃节公益","红博",
        "cd设计之都","漫道","画外","360","俱乐部","涨霸弗",
    ],
    "宠物生态": [
        "宠物","猫咖","星图犬盟","爪爪巴士",
    ],
}


# ── 品牌标准化映射 ──────────────────────────
# 将各种写法收敛为统一品牌名

BRAND_NORMALIZE_MAP = {
    # 小布/Brompton 系列
    "小布": "Brompton小布",
    "小布自行车": "Brompton小布",
    "小布Brompton": "Brompton小布",
    "brompton": "Brompton小布",
    "Brompton": "Brompton小布",
    "brompton小布": "Brompton小布",
    "Brompton小布": "Brompton小布",
    "Brompton小布折叠自行车": "Brompton小布",
    "Brompton 小布折叠车": "Brompton小布",
    "brompton&gaga": "Brompton小布",
    "Brompton 万豪酒店": "Brompton小布",
    "昆cycle&explore Brompton": "Brompton小布",

    # 蔚来系列
    "蔚来汽车": "蔚来",
    "蔚来汽车人": "蔚来",
    "蔚来乐道": "蔚来乐道",
    "乐道": "蔚来乐道",
    "蔚来萤火虫": "蔚来萤火虫",
    "萤火虫": "蔚来萤火虫",

    # 理想系列
    "理想": "理想汽车",
    "理想汽车": "理想汽车",

    # 鸿蒙智行/问界系列
    "问界": "鸿蒙智行",
    "AITO": "鸿蒙智行",
    "aito": "鸿蒙智行",
    "华为AITO": "鸿蒙智行",
    "华为汽车": "鸿蒙智行",
    "G-SHOCK×鸿蒙智行": "鸿蒙智行",

    # 小米系列
    "小米之家": "小米",
    "小米汽车": "小米汽车",

    # 宝马系列
    "BMW": "宝马",
    "bmw": "宝马",

    # 长城系列
    "长城魏派汽车": "长城魏牌",
    "长城魏牌": "长城魏牌",
    "魏牌": "长城魏牌",
    "魏派": "长城魏牌",
    "长城 卡骆驰": "长城魏牌",

    # 智己
    "智己": "智己汽车",
    "智己汽车": "智己汽车",

    # 腾势
    "腾势": "腾势汽车",
    "腾势汽车": "腾势汽车",

    # 小鹏
    "小鹏": "小鹏汽车",
    "小鹏汽车": "小鹏汽车",

    # 韶音系列
    "韶音SHOKZ": "韶音",
    "韶音耳机": "韶音",
    "SHOKZ": "韶音",
    "YourCompany×韶音×友社": "韶音",
    "BrandA×BrandB×BrandC×BrandD": "韶音",

    # HOKA系列
    "HOKA": "HOKA",
    "hoka": "HOKA",
    "HOKA GARMIN SHOKZ": "HOKA",

    # 佳明系列
    "佳明 GARMIN": "佳明GARMIN",
    "GARMIN": "佳明GARMIN",
    "佳明": "佳明GARMIN",
    "而意&佳明": "佳明GARMIN",

    # Wilson系列
    "wilson": "Wilson",
    "Wilson": "Wilson",

    # Nike系列
    "nike": "Nike",
    "Nike": "Nike",
    "耐克": "Nike",

    # lululemon系列
    "Lululemon": "lululemon",
    "lululemon×第二十一网球": "lululemon",

    # 崔克系列
    "崔克": "崔克Trek",
    "崔克Trek自行车": "崔克Trek",
    "TREK公路自行车": "崔克Trek",
    "Trek": "崔克Trek",
    "TREK": "崔克Trek",

    # 捷安特系列
    "捷安特GINANT": "捷安特",
    "捷安特": "捷安特",

    # 昂跑系列
    "昂跑 曲江创意谷": "昂跑",

    # Outopia系列
    "Outopia": "Outopia",
    "outopia": "Outopia",
    "outopia跑团": "Outopia",

    # 商场系列 -> 统一为"商场合作"
    "商场合作": "商场合作",
    "万象汇商场": "商场合作",
    "A park商场": "商场合作",
    "a park": "商场合作",
    "菏泽佳和城商场": "商场合作",

    # 银行系列
    "上海交通银行信用卡": "交通银行",
    "中国邮储银行新疆分行上门购": "邮储银行",
    "中国邮储银行": "邮储银行",
    "中国银行": "中国银行",
    "广发银行": "广发银行",

    # 华为系列
    "华为荣耀": "华为荣耀",
    "医院＋华为": "华为",

    # 摄影
    "高校摄影展": "摄影协会",
    "摄影": "摄影协会",

    # 跑步
    "跑步社团": "跑步",

    # 社区
    "社区组织": "社区",
    "社区": "社区",

    # 户外
    "户外运动": "户外",
    "户外社团": "户外",
    "桂林探索新境户外探险": "户外",

    # 骑行
    "骑行社团": "骑行",
    "成都骑行吧": "骑行",

    # 高校
    "高校": "高校",

    # 健身房
    "MH健身房": "健身房",

    # 羽毛球
    "当地羽毛球馆": "羽毛球",

    # 堡狮龙
    "堡狮龙bossini": "堡狮龙",

    # 赛事
    "体育赛事组": "赛事",

    # 机车
    "俱乐部": "机车俱乐部",

    # 荣耀 vs 王者荣耀
    "王者荣耀赛事主办方": "王者荣耀",
    "王者荣耀全国大赛海口中心站漫展": "王者荣耀",

    # 乐高
    "乐高授权专卖店": "乐高",
    "卡西欧  乐高": "乐高",

    # 而意
    "而意": "而意",

    # 360/YourCompany自身
    "YourCompany×亚瑟士×成都来士": "亚瑟士",
    "亚瑟士 × YourCompany × BLT × 宇树": "亚瑟士",
}


def _normalize_brand(brand_text: str) -> str:
    """将品牌文本标准化为统一名称。"""
    text = str(brand_text).strip()
    if not text or text == "无":
        return text
    # 精确匹配
    if text in BRAND_NORMALIZE_MAP:
        return BRAND_NORMALIZE_MAP[text]
    # 模糊匹配（检查是否包含已知品牌关键词）
    text_lower = text.lower()
    for key, val in BRAND_NORMALIZE_MAP.items():
        if key.lower() == text_lower:
            return val
    return text


def _categorize_brand(brand_text: str) -> str:
    """将品牌文本映射到大类。"""
    text = str(brand_text).strip()
    if not text or text == "无":
        return "未分类"
    text_lower = text.lower()
    for category, keywords in BRAND_CATEGORY_MAP.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return category
    return "其他"


def analyze_brand_partnerships(
    merged: pd.DataFrame,
    dim_store: pd.DataFrame | None = None,
    dim_dealer: pd.DataFrame | None = None,
) -> dict:
    """生成异业合作品牌分析全量数据。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = safe_num(df["sales_clean"])
    df["participants"] = safe_num(df["participants"])
    df["wechat"] = safe_num(df["wechat_adds"])
    df["hosts"] = safe_num(df["converted_hosts"])
    dealer_col = "dealer_final" if "dealer_final" in df.columns else "dealer"

    # 有合作品牌的活动
    has_brand = df["partner_brands"].notna() & df["partner_brands"].astype(str).str.strip().ne("") & df["partner_brands"].astype(str).str.strip().ne("无")
    coop_df = df[has_brand].copy()
    no_coop_df = df[~has_brand].copy()

    # 爆炸合作品牌
    coop_df["brand_raw"] = coop_df["partner_brands"].str.split(r"[,，、]")
    coop_exploded = coop_df.explode("brand_raw")
    coop_exploded["brand"] = coop_exploded["brand_raw"].str.strip().apply(_normalize_brand)
    coop_exploded = coop_exploded[coop_exploded["brand"] != ""]

    # 分类
    coop_exploded["brand_category"] = coop_exploded["brand"].apply(_categorize_brand)

    # ── 大类汇总 ──────────────────────────────
    categories = []
    for cat, g in coop_exploded.groupby("brand_category"):
        unique_brands = g["brand"].nunique()
        # 去重活动数（一条活动可能有多个品牌）
        activity_ids = g["record_id"].unique()
        categories.append({
            "category": cat,
            "brand_count": int(unique_brands),
            "activity_count": int(len(activity_ids)),
            "total_sales": float(g.groupby("record_id")["sales"].first().sum()),
            "total_participants": int(g.groupby("record_id")["participants"].first().sum()),
            "total_wechat": int(g.groupby("record_id")["wechat"].first().sum()),
            "total_hosts": int(g.groupby("record_id")["hosts"].first().sum()),
        })

    categories.sort(key=lambda x: x["activity_count"], reverse=True)

    # ── 品牌排行（全部）────────────────────────
    brands_list = []
    for brand, g in coop_exploded.groupby("brand"):
        cat = g["brand_category"].iloc[0]
        activity_ids = g["record_id"].unique()
        act_count = len(activity_ids)
        sales = float(g.groupby("record_id")["sales"].first().sum())
        parts = int(g.groupby("record_id")["participants"].first().sum())
        wechat = int(g.groupby("record_id")["wechat"].first().sum())
        hosts = int(g.groupby("record_id")["hosts"].first().sum())

        # 最早/最晚合作时间
        dates = g["activity_date"].dropna()
        first_date = dates.min().strftime("%Y-%m-%d") if len(dates) > 0 else ""
        last_date = dates.max().strftime("%Y-%m-%d") if len(dates) > 0 else ""

        brands_list.append({
            "brand": brand,
            "category": cat,
            "activity_count": act_count,
            "total_sales": sales,
            "total_participants": parts,
            "total_wechat": wechat,
            "total_hosts": hosts,
            "avg_sales": round(sales / act_count, 0) if act_count else 0,
            "avg_hosts": round(hosts / act_count, 1) if act_count else 0,
            "avg_wechat": round(wechat / act_count, 1) if act_count else 0,
            "conversion_rate": round(hosts / parts, 4) if parts > 0 else 0,
            "wechat_rate": round(wechat / parts, 4) if parts > 0 else 0,
            "first_coop_date": first_date,
            "last_coop_date": last_date,
            "stores": int(g["store_name"].nunique()),
            "dealers": int(g[dealer_col].nunique()) if dealer_col in g.columns else 0,
        })

    brands_list.sort(key=lambda x: x["activity_count"], reverse=True)

    # ── 合作 vs 无合作对比 ────────────────────
    comparison = {
        "coop": {
            "activity_count": int(len(coop_df)),
            "total_sales": float(coop_df["sales"].sum()),
            "total_participants": int(coop_df["participants"].sum()),
            "total_wechat": int(coop_df["wechat"].sum()),
            "total_hosts": int(coop_df["hosts"].sum()),
            "avg_sales": float(coop_df["sales"].sum() / len(coop_df)) if len(coop_df) else 0,
            "avg_hosts": float(coop_df["hosts"].sum() / len(coop_df)) if len(coop_df) else 0,
        },
        "no_coop": {
            "activity_count": int(len(no_coop_df)),
            "total_sales": float(no_coop_df["sales"].sum()),
            "total_participants": int(no_coop_df["participants"].sum()),
            "total_wechat": int(no_coop_df["wechat"].sum()),
            "total_hosts": int(no_coop_df["hosts"].sum()),
            "avg_sales": float(no_coop_df["sales"].sum() / len(no_coop_df)) if len(no_coop_df) else 0,
            "avg_hosts": float(no_coop_df["hosts"].sum() / len(no_coop_df)) if len(no_coop_df) else 0,
        },
    }

    # ── 月度趋势 ──────────────────────────────
    monthly = []
    coop_monthly = coop_df.copy()
    coop_monthly["month"] = coop_monthly["activity_date"].dt.to_period("M").astype(str)
    for month, g in coop_monthly.groupby("month"):
        if month == "NaT":
            continue
        monthly.append({
            "month": month,
            "activity_count": int(len(g)),
            "total_sales": float(g["sales"].sum()),
            "total_wechat": int(g["wechat"].sum()),
            "total_hosts": int(g["hosts"].sum()),
        })
    monthly.sort(key=lambda x: x["month"])

    return {
        "summary": {
            "total_activities": int(len(df)),
            "coop_activities": int(len(coop_df)),
            "coop_rate": round(len(coop_df) / len(df), 4) if len(df) else 0,
            "total_brands": int(coop_exploded["brand"].nunique()),
            "total_categories": len(categories),
        },
        "categories": categories,
        "brands": brands_list,
        "comparison": comparison,
        "monthly_trend": monthly,
    }


def get_brand_detail(
    merged: pd.DataFrame,
    brand_name: str,
) -> dict:
    """获取某个具体品牌的合作详情。"""
    df = merged.copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"], errors="coerce")
    df["sales"] = safe_num(df["sales_clean"])
    df["participants"] = safe_num(df["participants"])
    df["wechat"] = safe_num(df["wechat_adds"])
    df["hosts"] = safe_num(df["converted_hosts"])
    dealer_col = "dealer_final" if "dealer_final" in df.columns else "dealer"

    # 模糊匹配品牌（含标准化）
    normalized = _normalize_brand(brand_name)
    mask = df["partner_brands"].fillna("").str.contains(re.escape(brand_name), case=False, na=False, regex=True) | \
           df["partner_brands"].fillna("").str.contains(re.escape(normalized), case=False, na=False, regex=True) | \
           df["activity_desc"].fillna("").str.contains(re.escape(brand_name), case=False, na=False, regex=True)
    brand_df = df[mask].copy()

    if len(brand_df) == 0:
        return {"error": f"未找到品牌 '{brand_name}' 的合作活动"}

    category = _categorize_brand(brand_name)

    # 活动明细
    activities = []
    for _, r in brand_df.sort_values("activity_date", na_position="last").iterrows():
        activities.append({
            "activity_date": r["activity_date"].strftime("%Y-%m-%d") if pd.notna(r["activity_date"]) else "",
            "activity_desc": str(r.get("activity_desc", ""))[:100],
            "store_name": str(r.get("store_name", "")),
            "dealer": str(r.get(dealer_col, "")),
            "province_unit": str(r.get("province_unit", "")),
            "participants": int(r["participants"]),
            "wechat": int(r["wechat"]),
            "hosts": int(r["hosts"]),
            "sales": float(r["sales"]),
            "activity_status": str(r.get("activity_status", "")),
        })

    # 门店分布
    stores = []
    for store, g in brand_df.groupby("store_name"):
        stores.append({
            "store": store,
            "count": len(g),
            "sales": float(g["sales"].sum()),
            "hosts": int(g["hosts"].sum()),
        })
    stores.sort(key=lambda x: x["count"], reverse=True)

    # 代理商分布
    dealers = []
    for dealer, g in brand_df.groupby(dealer_col):
        dealers.append({
            "dealer": dealer,
            "count": len(g),
            "sales": float(g["sales"].sum()),
            "hosts": int(g["hosts"].sum()),
        })
    dealers.sort(key=lambda x: x["count"], reverse=True)

    # 月度趋势
    monthly = []
    bd = brand_df.copy()
    bd["month"] = bd["activity_date"].dt.to_period("M").astype(str)
    for month, g in bd.groupby("month"):
        if month == "NaT":
            continue
        monthly.append({
            "month": month,
            "count": len(g),
            "sales": float(g["sales"].sum()),
            "hosts": int(g["hosts"].sum()),
        })
    monthly.sort(key=lambda x: x["month"])

    return {
        "brand": brand_name,
        "category": category,
        "activity_count": int(len(brand_df)),
        "total_sales": float(brand_df["sales"].sum()),
        "total_participants": int(brand_df["participants"].sum()),
        "total_wechat": int(brand_df["wechat"].sum()),
        "total_hosts": int(brand_df["hosts"].sum()),
        "avg_sales": float(brand_df["sales"].sum() / len(brand_df)) if len(brand_df) else 0,
        "avg_hosts": float(brand_df["hosts"].sum() / len(brand_df)) if len(brand_df) else 0,
        "conversion_rate": float(brand_df["hosts"].sum() / brand_df["participants"].sum()) if brand_df["participants"].sum() > 0 else 0,
        "wechat_rate": float(brand_df["wechat"].sum() / brand_df["participants"].sum()) if brand_df["participants"].sum() > 0 else 0,
        "stores_covered": int(brand_df["store_name"].nunique()),
        "dealers_covered": int(brand_df[dealer_col].nunique()) if dealer_col in brand_df.columns else 0,
        "first_coop_date": brand_df["activity_date"].min().strftime("%Y-%m-%d") if brand_df["activity_date"].notna().any() else "",
        "last_coop_date": brand_df["activity_date"].max().strftime("%Y-%m-%d") if brand_df["activity_date"].notna().any() else "",
        "activities": activities,
        "store_distribution": stores,
        "dealer_distribution": dealers,
        "monthly_trend": monthly,
    }
