# 指标字典 (METRIC_DICTIONARY.md)

中国区专卖店线下活动经营分析平台 · Phase 4：指标体系。

所有指标统一从 `offline_activity.db` 计算，禁止在前端 HTML 中计算。
指标实现：`metrics/` 目录下 6 个模块。

## 一、活动指标（metrics/activity_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| total_activities | 活动总数 | COUNT(*) | fact_activity | 全局概览、日报 |
| completed_activities | 已完成活动数 | 状态 IN (已完成, 待评估) 的记录数 | fact_activity | 完成率追踪 |
| completion_rate_pct | 活动完成率 | 已完成 / 总数 * 100 | fact_activity | 经营健康度 |
| total_sales | 销售总额 | SUM(sales_clean) | fact_activity | 销售 KPI |
| avg_sales_valid | 有效活动场均销售 | AVG(sales_clean) WHERE is_valid=1 | fact_activity | 活动效率 |
| total_wechat_adds | 企微添加总数 | SUM(wechat_adds) | fact_activity | 私域蓄水 |
| total_participants | 参与总人数 | SUM(participants) | fact_activity | 覆盖评估 |
| avg_conversion_rate | 平均成交率 | AVG(conversion_rate_pct) | fact_activity | 转化效率 |
| valid_activities | 有效活动数 | is_valid_activity=1 的记录数 | fact_activity | 质量评估 |
| recap_completed | 完成复盘数 | is_recap_completed=1 的记录数 | fact_activity | 闭环追踪 |
| activity_by_type | 分类型活动数 | GROUP BY activity_type | fact_activity | 类型分析 |
| activity_monthly_trend | 月度趋势 | GROUP BY year_month | fact_activity | 趋势分析 |
| activity_by_source | 分来源活动数 | GROUP BY activity_source | fact_activity | 来源分析 |

## 二、门店指标（metrics/store_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| total_stores | 门店总数 | COUNT(*) FROM dim_store | dim_store | 全局概览 |
| active_stores | 有活动门店数 | COUNT(DISTINCT store_id) FROM fact_activity | fact_activity | 覆盖评估 |
| store_coverage_rate | 门店覆盖率 | active / total * 100 | dim_store + fact_activity | 经营健康度 |
| activity_count_per_store | 门店活动数 | COUNT(*) GROUP BY store_id | fact_activity | 门店活跃度 |
| total_sales_per_store | 门店销售额 | SUM(sales_clean) GROUP BY store_id | fact_activity | 门店排名 |
| avg_sales_per_store | 门店场均销售 | AVG(sales_clean) GROUP BY store_id | fact_activity | 门店效率 |
| inactive_stores | 不活跃门店 | N天无活动的已开业门店 | dim_store + fact_activity | 风险预警 |
| never_active_stores | 零活动门店 | 从未举办活动的门店 | dim_store + fact_activity | 覆盖差距 |

## 三、代理商指标（metrics/dealer_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| total_dealers | 代理商总数 | COUNT(*) FROM dim_dealer | dim_dealer | 全局概览 |
| active_dealers | 有活动代理商数 | COUNT(DISTINCT dealer) FROM fact_activity | fact_activity | 参与度 |
| activity_count_per_dealer | 代理商活动数 | COUNT(*) GROUP BY dealer | fact_activity | 代理商排名 |
| total_sales_per_dealer | 代理商销售额 | SUM(sales_clean) GROUP BY dealer | fact_activity | 代理商排名 |
| covered_stores_per_dealer | 代理商覆盖门店 | COUNT(DISTINCT store_id) GROUP BY dealer | fact_activity | 覆盖评估 |
| completion_rate_per_dealer | 代理商完成率 | 已完成 / 总数 GROUP BY dealer | fact_activity | 执行质量 |

## 四、产品指标（metrics/product_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| total_product_lines | 产品线总数 | COUNT(DISTINCT product_line) | dim_product + fact_activity_product | 产品概览 |
| product_activity_count | 产品活动数 | COUNT(DISTINCT activity_id) GROUP BY product_line | fact_activity_product | 产品推广 |
| product_total_qty | 产品总销量 | SUM(sales_qty) GROUP BY product_line | fact_activity_product | 产品 KPI |
| product_avg_qty | 产品场均销量 | AVG(sales_qty) GROUP BY product_line | fact_activity_product | 产品效率 |
| product_covered_stores | 产品覆盖门店 | COUNT(DISTINCT store_id) GROUP BY product_line | fact_activity_product | 渗透评估 |
| product_monthly_trend | 产品月趋势 | GROUP BY year_month, product_line | fact_activity_product | 趋势分析 |
| product_by_region | 产品分区域 | GROUP BY region, product_line | fact_activity_product | 区域分析 |

## 五、区域指标（metrics/region_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| region_activity_count | 区域活动数 | COUNT(*) GROUP BY region | fact_activity + dim_store | 区域排名 |
| region_total_sales | 区域销售额 | SUM(sales_clean) GROUP BY region | fact_activity + dim_store | 区域 KPI |
| region_avg_sales | 区域场均销售 | AVG(sales_clean) GROUP BY region | fact_activity + dim_store | 区域效率 |
| region_active_stores | 区域活跃门店 | COUNT(DISTINCT store_id) GROUP BY region | fact_activity + dim_store | 区域覆盖 |
| region_coverage_pct | 区域覆盖率 | active / total GROUP BY region | dim_store + fact_activity | 覆盖差距 |
| province_metrics | 省级指标 | GROUP BY province | fact_activity + dim_store | 省级分析 |

## 六、新品指标（metrics/launch_metrics.py）

| 指标名称 | 业务定义 | 计算公式 | 数据来源 | 应用场景 |
|---|---|---|---|---|
| first_seen_month | 首次出现月份 | MIN(year_month) GROUP BY product_line | fact_activity_product | 上市追踪 |
| launch_total_qty | 上市总销量 | SUM(sales_qty) GROUP BY product_line | fact_activity_product | 上市 KPI |
| launch_covered_stores | 上市覆盖门店 | COUNT(DISTINCT store_id) | fact_activity_product | 渠道渗透 |
| launch_covered_dealers | 上市覆盖代理商 | COUNT(DISTINCT dealer) | fact_activity_product | 渠道渗透 |
| penetration_pct | 渗透率 | covered / total_stores * 100 | fact_activity_product + dim_store | 渗透评估 |
| launch_monthly_trend | 月度趋势 | GROUP BY year_month, product_line | fact_activity_product | 趋势分析 |
| launch_quarterly_comparison | 季度对比 | GROUP BY quarter_name, product_line | fact_activity_product | 季度复盘 |
| launch_analysis | 单品深度分析 | 综合以上指标 | 多表 JOIN | 新品专项 |

## 指标使用规范

1. 所有指标统一从 `offline_activity.db` 计算，通过 `metrics/` 模块调用
2. 分析引擎（`analysis/`）调用指标模块，不直接写 SQL
3. 评分模型（`scoring/`）基于指标计算分数
4. 前端只展示结果，不做计算
5. 新增指标：在对应 metrics 模块中添加函数，更新本字典
