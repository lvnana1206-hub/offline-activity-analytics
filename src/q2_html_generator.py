"""生成 Q2 季度经营复盘独立 HTML 页面。"""
from __future__ import annotations
import json
from .q2_review_generator import compute_q2_review


def generate_q2_html() -> str:
    data = compute_q2_review()
    json_str = json.dumps(data, ensure_ascii=False, default=str)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026 Q2 线下活动经营复盘</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
:root {{
  --primary:#4f46e5; --success:#10b981; --warning:#f59e0b; --danger:#ef4444;
  --info:#0ea5e9; --bg:#f1f5f9; --card:#fff; --text:#1e293b; --text2:#64748b;
  --text3:#94a3b8; --border:#e2e8f0; --radius:6px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }}
.container {{ max-width:1400px; margin:0 auto; padding:20px 24px; }}

/* Header */
.header {{ background:linear-gradient(135deg,#4f46e5,#818cf8); color:#fff; border-radius:var(--radius); padding:24px 28px; margin-bottom:20px; }}
.header h1 {{ font-size:22px; font-weight:700; margin-bottom:10px; }}
.header-info {{ display:flex; gap:24px; flex-wrap:wrap; font-size:13px; opacity:.9; }}
.header-info span {{ display:flex; align-items:center; gap:4px; }}

/* Section */
.section {{ background:var(--card); border-radius:var(--radius); padding:20px 24px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
.section-title {{ font-size:16px; font-weight:700; margin-bottom:16px; padding:8px 14px; background:linear-gradient(90deg,#4f46e5,#818cf8); color:#fff; border-radius:4px; display:inline-block; }}

/* KPI */
.kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:14px; }}
.kpi-card {{ background:var(--card); border-radius:var(--radius); padding:18px 20px; box-shadow:0 1px 3px rgba(0,0,0,.06); border-top:3px solid var(--primary); }}
.kpi-card .label {{ font-size:12px; color:var(--text2); margin-bottom:6px; }}
.kpi-card .value {{ font-size:24px; font-weight:700; }}
.kpi-card .sub {{ font-size:11px; color:var(--text3); margin-top:4px; }}
.kpi-card.green {{ border-top-color:var(--success); }} .kpi-card.green .value {{ color:var(--success); }}
.kpi-card.blue {{ border-top-color:var(--info); }} .kpi-card.blue .value {{ color:var(--info); }}
.kpi-card.orange {{ border-top-color:var(--warning); }} .kpi-card.orange .value {{ color:var(--warning); }}
.kpi-card.red {{ border-top-color:var(--danger); }} .kpi-card.red .value {{ color:var(--danger); }}
.kpi-card.purple {{ border-top-color:#8b5cf6; }} .kpi-card.purple .value {{ color:#8b5cf6; }}

/* Chart */
.chart-row {{ display:grid; gap:16px; margin-bottom:16px; }}
.chart-row.cols-2 {{ grid-template-columns:1fr 1fr; }}
.chart-box {{ background:var(--card); border-radius:var(--radius); padding:16px 20px; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
.chart-box .ct {{ font-size:14px; font-weight:600; margin-bottom:12px; }}
.chart-body {{ width:100%; }}

/* Table */
.table-wrap {{ overflow-x:auto; margin-top:8px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; padding:8px 12px; background:#f8fafc; color:var(--text2); font-weight:600; white-space:nowrap; border-bottom:2px solid var(--border); }}
td {{ padding:8px 12px; border-bottom:1px solid var(--border); white-space:nowrap; }}
tr:hover td {{ background:#f8fafc; }}
.text-right {{ text-align:right; }}
.text-center {{ text-align:center; }}

/* Analysis text */
.analysis-box {{ background:#f8fafc; border-radius:var(--radius); padding:14px 18px; margin:12px 0; font-size:13px; line-height:1.8; }}
.analysis-box p {{ margin-bottom:6px; }}
.analysis-box .at {{ font-weight:600; margin-bottom:8px; color:var(--primary); }}

/* Summary */
.summary-cat {{ font-size:15px; font-weight:700; margin:16px 0 10px; padding-bottom:6px; border-bottom:2px solid var(--border); }}
.summary-cat.hl {{ color:var(--success); }}
.summary-cat.prob {{ color:var(--danger); }}
.summary-cat.q3 {{ color:var(--primary); }}
.summary-item {{ background:#f8fafc; border-radius:var(--radius); padding:14px 18px; margin-bottom:10px; border-left:4px solid var(--primary); }}
.summary-item .si-label {{ font-size:11px; font-weight:700; color:var(--text2); }}
.summary-item .si-text {{ font-size:13px; margin:2px 0 6px; }}
.summary-item .si-suggest {{ font-size:13px; color:var(--primary); font-weight:600; }}

/* Funnel */
.funnel-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:8px; margin:16px 0; }}
.funnel-step {{ text-align:center; padding:16px 8px; border-radius:var(--radius); color:#fff; }}
.funnel-step .fs-val {{ font-size:20px; font-weight:700; }}
.funnel-step .fs-label {{ font-size:11px; opacity:.9; margin-top:4px; }}
.funnel-arrow {{ text-align:center; font-size:20px; color:var(--text3); display:flex; align-items:center; justify-content:center; }}

/* Case */
.case-card {{ background:var(--card); border-radius:var(--radius); padding:14px 18px; box-shadow:0 1px 3px rgba(0,0,0,.06); margin-bottom:10px; display:flex; gap:14px; align-items:center; }}
.case-rank {{ font-size:22px; font-weight:800; color:var(--primary); min-width:36px; text-align:center; }}
.case-info {{ flex:1; }}
.case-info .cn {{ font-size:14px; font-weight:600; margin-bottom:4px; }}
.case-info .cm {{ font-size:12px; color:var(--text2); }}
.case-info .cr {{ font-size:11px; color:var(--primary); margin-top:4px; }}
.case-sales {{ text-align:right; }}
.case-sales .amount {{ font-size:18px; font-weight:700; color:var(--success); }}
.case-sales .meta {{ font-size:11px; color:var(--text3); }}

/* Filter bar */
.filter-bar {{ background:var(--card); border-radius:var(--radius); padding:12px 20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
.filter-bar select {{ padding:6px 10px; border:1px solid var(--border); border-radius:4px; font-size:13px; }}
.filter-bar label {{ font-size:12px; color:var(--text2); }}
.export-btn {{ padding:6px 14px; border:1px solid var(--primary); background:var(--primary); color:#fff; border-radius:4px; cursor:pointer; font-size:12px; }}
.export-btn:hover {{ opacity:.9; }}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
  <h1>2026 Q2 线下活动经营复盘</h1>
  <div class="header-info">
    <span>数据来源：飞书《线下活动管理》活动总池 + YourCompany专卖店信息表</span>
    <span>数据刷新：__HEADER_TIME__</span>
    <span>活动总记录：__TOTAL_RECORDS__ 场</span>
    <span>有效活动：__EFFECTIVE_COUNT__ 场</span>
  </div>
</div>

<!-- Filter Bar -->
<div class="filter-bar">
  <label>省区</label><select id="f-region"><option value="">全部</option></select>
  <label>代理商</label><select id="f-dealer"><option value="">全部</option></select>
  <label>活动类型</label><select id="f-type"><option value="">全部</option></select>
  <label>产品</label><select id="f-product"><option value="">全部</option></select>
  <button class="export-btn" onclick="exportPNG()">导出PNG</button>
  <button class="export-btn" onclick="exportExcel()" style="background:var(--success);border-color:var(--success)">导出Excel</button>
</div>

<!-- Part 1: KPI -->
<div class="section">
  <div class="section-title">一、Q2 经营总览</div>
  <div class="kpi-grid" id="kpi-grid"></div>
</div>

<!-- Part 2: Monthly Trend -->
<div class="section">
  <div class="section-title">二、月度趋势分析</div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">活动场次 & 销售额趋势</div><div class="chart-body" id="c-trend1" style="height:300px"></div></div>
    <div class="chart-box"><div class="ct">转化主机 & 企微新增趋势</div><div class="chart-body" id="c-trend2" style="height:300px"></div></div>
  </div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">有效活动趋势</div><div class="chart-body" id="c-trend3" style="height:260px"></div></div>
    <div class="chart-box"><div class="ct">无人机活动趋势</div><div class="chart-body" id="c-trend4" style="height:260px"></div></div>
  </div>
  <div class="analysis-box" id="trend-analysis"></div>
</div>

<!-- Part 3: Funnel -->
<div class="section">
  <div class="section-title">三、活动转化漏斗</div>
  <div class="chart-body" id="c-funnel" style="height:320px"></div>
  <div class="analysis-box" id="funnel-analysis"></div>
</div>

<!-- Part 4: Activity Types -->
<div class="section">
  <div class="section-title">四、活动类型经营分析</div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">各类型销售额对比</div><div class="chart-body" id="c-type-sales" style="height:300px"></div></div>
    <div class="chart-box"><div class="ct">活动占比</div><div class="chart-body" id="c-type-pie" style="height:300px"></div></div>
  </div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">企微新增对比</div><div class="chart-body" id="c-type-wechat" style="height:260px"></div></div>
    <div class="chart-box"><div class="ct">有效率对比</div><div class="chart-body" id="c-type-eff" style="height:260px"></div></div>
  </div>
  <div class="table-wrap" id="type-table"></div>
</div>

<!-- Part 5: Products -->
<div class="section">
  <div class="section-title">五、产品线经营分析</div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">产品销量对比</div><div class="chart-body" id="c-prod-sales" style="height:300px"></div></div>
    <div class="chart-box"><div class="ct">产品 × 活动类型 热力图</div><div class="chart-body" id="c-prod-heat" style="height:300px"></div></div>
  </div>
  <div class="chart-box"><div class="ct">产品月度趋势</div><div class="chart-body" id="c-prod-trend" style="height:280px"></div></div>
  <div class="table-wrap" id="prod-table"></div>
</div>

<!-- Part 6: Dealer Top20 -->
<div class="section">
  <div class="section-title">六、代理商经营排行 Top20</div>
  <div class="table-wrap" id="dealer-table"></div>
</div>

<!-- Part 7: Store Top20 -->
<div class="section">
  <div class="section-title">七、门店经营排行 Top20</div>
  <div class="table-wrap" id="store-table"></div>
</div>

<!-- Part 8: Regions -->
<div class="section">
  <div class="section-title">八、区域经营分析</div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">省区销售贡献 Top10</div><div class="chart-body" id="c-region-sales" style="height:340px"></div></div>
    <div class="chart-box"><div class="ct">省区活动数量 Top10</div><div class="chart-body" id="c-region-act" style="height:340px"></div></div>
  </div>
  <div class="table-wrap" id="region-table"></div>
</div>

<!-- Part 9: Channel -->
<div class="section">
  <div class="section-title">九、渠道经营分析（Mall店 vs 照材店）</div>
  <div class="chart-body" id="c-channel" style="height:300px"></div>
  <div class="table-wrap" id="channel-table"></div>
</div>

<!-- Part 10: Drone -->
<div class="section">
  <div class="section-title">十、无人机经营分析</div>
  <div class="chart-body" id="c-drone" style="height:300px"></div>
  <div class="table-wrap" id="drone-table"></div>
</div>

<!-- Part 11: Cooperation -->
<div class="section">
  <div class="section-title">十一、异业合作经营分析</div>
  <div class="chart-row cols-2">
    <div class="chart-box"><div class="ct">异业合作 vs 普通活动</div><div class="chart-body" id="c-coop-compare" style="height:280px"></div></div>
    <div class="chart-box"><div class="ct">合作品牌排行榜 Top10</div><div class="chart-body" id="c-coop-brand" style="height:280px"></div></div>
  </div>
</div>

<!-- Part 12: Cases -->
<div class="section">
  <div class="section-title">十二、优秀案例中心 Top20</div>
  <div id="cases-list"></div>
</div>

<!-- Part 13: Summary -->
<div class="section">
  <div class="section-title">十三、经营总结</div>
  <div id="summary-list"></div>
</div>

</div>

<script>
const D = {json_str};
const COLORS = ['#4f46e5','#10b981','#f59e0b','#ef4444','#0ea5e9','#8b5cf6','#ec4899','#14b8a6','#f97316','#6366f1'];
const charts = {{}};

function initChart(id) {{ const el=document.getElementById(id); if(!el) return null; if(charts[id]) charts[id].dispose(); charts[id]=echarts.init(el); return charts[id]; }}
function fmt(n) {{ if(n==null) return '-'; n=Number(n); if(isNaN(n)) return '-'; if(Math.abs(n)>=10000) return (n/10000).toFixed(1)+'万'; return n.toLocaleString('zh-CN',{{maximumFractionDigits:0}}); }}
function fmtPct(n) {{ if(n==null) return '-'; return (n*100).toFixed(1)+'%'; }}

// ── Part 1: KPI ─────────────────────────────
const k = D.kpi;
const kpiData = [
  ['活动总场次', fmt(k.total_activities), '场', ''],
  ['活动销售总额', '¥'+fmt(k.total_sales), '元', 'green'],
  ['转化主机数量', fmt(k.total_hosts), '台', 'blue'],
  ['活动参与人数', fmt(k.total_participants), '人', 'blue'],
  ['企微新增人数', fmt(k.total_wechat), '人', 'orange'],
  ['有效活动数', fmt(k.effective_activities), '场', 'green'],
  ['平均单场销售额', '¥'+fmt(k.avg_sales), '元', 'purple'],
  ['活动成交率', fmtPct(k.conversion_rate), '', 'red'],
];
document.getElementById('kpi-grid').innerHTML = kpiData.map(x=>`<div class="kpi-card ${{x[3]}}"><div class="label">${{x[0]}}</div><div class="value">${{x[1]}}</div><div class="sub">${{x[2]}}</div></div>`).join('');

// ── Part 2: Monthly Trend ───────────────────
const md = D.monthly_trend.data;
const months = md.map(r=>r.month_name);
const c1 = initChart('c-trend1');
c1.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:['活动场次','销售额'],top:0}}, grid:{{left:50,right:50,bottom:30,top:30}},
  xAxis:{{type:'category',data:months}}, yAxis:[{{type:'value',name:'场次'}},{{type:'value',name:'销售额',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}}],
  series:[{{name:'活动场次',type:'bar',data:md.map(r=>r.activities),itemStyle:{{color:COLORS[0]}}}},{{name:'销售额',type:'line',yAxisIndex:1,data:md.map(r=>Math.round(r.sales||0)),itemStyle:{{color:COLORS[1]}},smooth:true}}] }});

const c2 = initChart('c-trend2');
c2.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:['转化主机','企微新增'],top:0}}, grid:{{left:50,right:30,bottom:30,top:30}},
  xAxis:{{type:'category',data:months}}, yAxis:{{type:'value'}},
  series:[{{name:'转化主机',type:'bar',data:md.map(r=>r.hosts),itemStyle:{{color:COLORS[2]}}}},{{name:'企微新增',type:'line',data:md.map(r=>r.wechat),itemStyle:{{color:COLORS[4]}},smooth:true}}] }});

const c3 = initChart('c-trend3');
c3.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:50,right:30,bottom:30,top:20}},
  xAxis:{{type:'category',data:months}}, yAxis:{{type:'value',name:'有效活动'}},
  series:[{{type:'bar',data:md.map(r=>r.effective),itemStyle:{{color:COLORS[1]}},label:{{show:true,position:'top'}}}}] }});

const c4 = initChart('c-trend4');
c4.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:50,right:30,bottom:30,top:20}},
  xAxis:{{type:'category',data:months}}, yAxis:{{type:'value',name:'无人机活动'}},
  series:[{{type:'bar',data:md.map(r=>r.drone_activities),itemStyle:{{color:COLORS[5]}},label:{{show:true,position:'top'}}}}] }});

document.getElementById('trend-analysis').innerHTML = '<div class="at">趋势分析</div>' + D.monthly_trend.analysis.map(a=>`<p>${{a}}</p>`).join('');

// ── Part 3: Funnel ──────────────────────────
const f = D.funnel;
const fc = initChart('c-funnel');
fc.setOption({{ tooltip:{{trigger:'item',formatter:'{{b}}: {{c}}'}},
  series:[{{ type:'funnel', left:'10%',right:'10%',top:10,bottom:10, minSize:'30%', sort:'descending', gap:2,
    label:{{show:true,position:'inside',fontSize:13}},
    data:[
      {{name:'活动举办',value:f.activities,itemStyle:{{color:COLORS[0]}}}},
      {{name:'参与人数',value:f.participants,itemStyle:{{color:COLORS[1]}}}},
      {{name:'企微新增',value:f.wechat,itemStyle:{{color:COLORS[4]}}}},
      {{name:'成交人数',value:f.buyers,itemStyle:{{color:COLORS[2]}}}},
      {{name:'成交主机',value:f.hosts,itemStyle:{{color:COLORS[3]}}}},
      {{name:'成交销售额',value:f.sales,itemStyle:{{color:'#8b5cf6'}}}},
    ] }}] }});

document.getElementById('funnel-analysis').innerHTML = `<div class="at">转化分析</div>
  <p>活动参与率：${{fmtPct(f.r1)}}（参与${{fmt(f.participants)}}人 / 活动${{fmt(f.activities)}}场）</p>
  <p>企微转化率：${{fmtPct(f.r2)}}（企微${{fmt(f.wechat)}}人 / 参与${{fmt(f.participants)}}人）</p>
  <p>成交转化率：${{fmtPct(f.r3)}}（成交${{fmt(f.buyers)}}场 / 参与${{fmt(f.participants)}}人）</p>
  <p>客单主机数：${{fmt(f.r4)}}台/场（主机${{fmt(f.hosts)}}台 / 成交${{fmt(f.buyers)}}场）</p>
  <p>主机均价：¥${{fmt(f.r5)}}（销售额¥${{fmt(f.sales)}} / 主机${{fmt(f.hosts)}}台）</p>`;

// ── Part 4: Activity Types ──────────────────
const ts = D.activity_types.table;
const tNames = ts.map(r=>r.activity_type);
const cs1 = initChart('c-type-sales');
cs1.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:60,right:30,bottom:60,top:20}}, xAxis:{{type:'category',data:tNames,axisLabel:{{rotate:30,fontSize:10}}}},
  yAxis:{{type:'value',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}},
  series:[{{type:'bar',data:ts.map(r=>Math.round(r.sales||0)),itemStyle:{{color:COLORS[0]}},label:{{show:true,position:'top',formatter:p=>fmt(p.value),fontSize:9}}}}] }});

const cs2 = initChart('c-type-pie');
cs2.setOption({{ tooltip:{{trigger:'item',formatter:'{{b}}: {{c}}场 ({{d}}%)'}}, legend:{{orient:'vertical',right:0,top:'center',textStyle:{{fontSize:11}}}},
  series:[{{type:'pie',radius:['35%','65%'],center:['40%','50%'],data:ts.map((r,i)=>({{name:r.activity_type,value:r.count,itemStyle:{{color:COLORS[i%10]}}}}))}}] }});

const cs3 = initChart('c-type-wechat');
cs3.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:60,right:30,bottom:60,top:20}}, xAxis:{{type:'category',data:tNames,axisLabel:{{rotate:30,fontSize:10}}}},
  yAxis:{{type:'value'}}, series:[{{type:'bar',data:ts.map(r=>r.wechat||0),itemStyle:{{color:COLORS[4]}}}}] }});

const cs4 = initChart('c-type-eff');
cs4.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:60,right:30,bottom:60,top:20}}, xAxis:{{type:'category',data:tNames,axisLabel:{{rotate:30,fontSize:10}}}},
  yAxis:{{type:'value',max:1,axisLabel:{{formatter:v=>(v*100).toFixed(0)+'%'}}}},
  series:[{{type:'bar',data:ts.map(r=>r.effective_rate||0),itemStyle:{{color:COLORS[1]}},label:{{show:true,position:'top',formatter:p=>fmtPct(p.value),fontSize:9}}}}] }});

document.getElementById('type-table').innerHTML = `<table><thead><tr>
  <th>活动类型</th><th class="text-right">活动场次</th><th class="text-right">有效活动</th><th class="text-right">有效率</th>
  <th class="text-right">销售额</th><th class="text-right">场均销售额</th><th class="text-right">转化主机</th>
  <th class="text-right">企微新增</th><th class="text-right">参与人数</th>
</tr></thead><tbody>${{ts.map(r=>`<tr><td>${{r.activity_type}}</td><td class="text-right">${{fmt(r.count)}}</td>
  <td class="text-right">${{fmt(r.effective)}}</td><td class="text-right">${{fmtPct(r.effective_rate)}}</td>
  <td class="text-right">¥${{fmt(r.sales)}}</td><td class="text-right">¥${{fmt(r.avg_sales)}}</td>
  <td class="text-right">${{fmt(r.hosts)}}</td><td class="text-right">${{fmt(r.wechat)}}</td>
  <td class="text-right">${{fmt(r.participants)}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 5: Products ────────────────────────
const ps = D.products.table;
const pNames = ps.map(r=>r.product);
const cp1 = initChart('c-prod-sales');
cp1.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:50,right:30,bottom:30,top:20}}, xAxis:{{type:'category',data:pNames}},
  yAxis:{{type:'value'}}, series:[{{type:'bar',data:ps.map(r=>Math.round(r.total_sales||0)),itemStyle:{{color:COLORS[0]}},label:{{show:true,position:'top',formatter:p=>fmt(p.value)}}}}] }});

// Heatmap
const cross = D.products.cross;
const pTypes = [...new Set(cross.map(r=>r.activity_type))];
const heatData = [];
cross.forEach(r=>{{ const pi=pNames.indexOf(r.product); const ti=pTypes.indexOf(r.activity_type); if(pi>=0&&ti>=0) heatData.push([ti,pi,r.count]); }});
const cp2 = initChart('c-prod-heat');
cp2.setOption({{ tooltip:{{position:'top'}}, grid:{{left:80,right:30,bottom:60,top:20}},
  xAxis:{{type:'category',data:pTypes,axisLabel:{{rotate:30,fontSize:10}}}},
  yAxis:{{type:'category',data:pNames}},
  visualMap:{{min:0,max:Math.max(...heatData.map(d=>d[2]),1),calculable:true,orient:'horizontal',left:'center',bottom:0}},
  series:[{{type:'heatmap',data:heatData,label:{{show:true,fontSize:10}}}}] }});

const pm = D.products.monthly;
const cp3 = initChart('c-prod-trend');
cp3.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:pNames,top:0}}, grid:{{left:50,right:30,bottom:30,top:30}},
  xAxis:{{type:'category',data:pm.map(r=>r.month_name)}}, yAxis:{{type:'value'}},
  series:pNames.map((p,i)=>({{name:p,type:'line',data:pm.map(r=>r[p]||0),itemStyle:{{color:COLORS[i%10]}},smooth:true}})) }});

document.getElementById('prod-table').innerHTML = `<table><thead><tr>
  <th>产品</th><th class="text-right">活动场次</th><th class="text-right">总销量</th><th class="text-right">场均销量</th>
  <th class="text-right">参与人数</th><th>推荐活动类型</th>
</tr></thead><tbody>${{ps.map(r=>`<tr><td>${{r.product}}</td><td class="text-right">${{fmt(r.activity_count)}}</td>
  <td class="text-right">${{fmt(r.total_sales)}}</td><td class="text-right">${{fmt(r.avg_sales)}}</td>
  <td class="text-right">${{fmt(r.participants)}}</td><td>${{r.top_type}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 6: Dealer Top20 ────────────────────
const ds = D.dealer_top20;
document.getElementById('dealer-table').innerHTML = `<table><thead><tr>
  <th class="text-center">排名</th><th>代理商</th><th>省区</th><th class="text-right">活动场次</th>
  <th class="text-right">有效活动</th><th class="text-right">有效率</th><th class="text-right">销售额</th>
  <th class="text-right">转化主机</th><th class="text-right">企微新增</th><th class="text-right">参与人数</th>
  <th class="text-right">场均销售额</th>
</tr></thead><tbody>${{ds.map(r=>`<tr><td class="text-center">${{r.rank}}</td><td>${{r.dealer}}</td><td>${{r.province}}</td>
  <td class="text-right">${{fmt(r.activities)}}</td><td class="text-right">${{fmt(r.effective)}}</td><td class="text-right">${{fmtPct(r.effective_rate)}}</td>
  <td class="text-right">¥${{fmt(r.sales)}}</td><td class="text-right">${{fmt(r.hosts)}}</td>
  <td class="text-right">${{fmt(r.wechat)}}</td><td class="text-right">${{fmt(r.participants)}}</td>
  <td class="text-right">¥${{fmt(r.avg_sales)}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 7: Store Top20 ─────────────────────
const ss = D.store_top20;
document.getElementById('store-table').innerHTML = `<table><thead><tr>
  <th class="text-center">排名</th><th>门店名称</th><th>代理商</th><th>省区</th>
  <th class="text-right">活动场次</th><th class="text-right">销售额</th><th class="text-right">转化主机</th>
  <th class="text-right">企微新增</th><th class="text-right">参与人数</th><th class="text-right">场均销售额</th>
</tr></thead><tbody>${{ss.map(r=>`<tr><td class="text-center">${{r.rank}}</td><td>${{r.store_name}}</td><td>${{r.dealer||'-'}}</td><td>${{r.province_unit||'-'}}</td>
  <td class="text-right">${{fmt(r.activities)}}</td><td class="text-right">¥${{fmt(r.sales)}}</td><td class="text-right">${{fmt(r.hosts)}}</td>
  <td class="text-right">${{fmt(r.wechat)}}</td><td class="text-right">${{fmt(r.participants)}}</td>
  <td class="text-right">¥${{fmt(r.avg_sales)}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 8: Regions ─────────────────────────
const rs = D.regions.province_units.slice(0,10);
const cr1 = initChart('c-region-sales');
cr1.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:100,right:30,bottom:20,top:20}},
  xAxis:{{type:'value',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}},
  yAxis:{{type:'category',data:rs.map(r=>r.region).reverse(),axisLabel:{{fontSize:10}}}},
  series:[{{type:'bar',data:rs.map(r=>Math.round(r.sales||0)).reverse(),itemStyle:{{color:COLORS[1]}},label:{{show:true,position:'right',fontSize:10}}}}] }});

const cr2 = initChart('c-region-act');
cr2.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:100,right:30,bottom:20,top:20}},
  xAxis:{{type:'value'}}, yAxis:{{type:'category',data:rs.map(r=>r.region).reverse(),axisLabel:{{fontSize:10}}}},
  series:[{{type:'bar',data:rs.map(r=>r.activities||0).reverse(),itemStyle:{{color:COLORS[0]}},label:{{show:true,position:'right',fontSize:10}}}}] }});

const rsAll = D.regions.province_units;
document.getElementById('region-table').innerHTML = `<table><thead><tr>
  <th>省区</th><th class="text-right">活动数</th><th class="text-right">销售额</th>
  <th class="text-right">转化主机</th><th class="text-right">覆盖门店</th><th class="text-right">覆盖代理商</th><th class="text-right">参与人数</th>
</tr></thead><tbody>${{rsAll.map(r=>`<tr><td>${{r.region}}</td><td class="text-right">${{fmt(r.activities)}}</td>
  <td class="text-right">¥${{fmt(r.sales)}}</td><td class="text-right">${{fmt(r.hosts)}}</td>
  <td class="text-right">${{fmt(r.stores)}}</td><td class="text-right">${{fmt(r.dealers)}}</td>
  <td class="text-right">${{fmt(r.participants)}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 9: Channel ─────────────────────────
const ch = D.channels;
const chNames = ch.map(r=>r.channel);
const cc = initChart('c-channel');
cc.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:['活动数量','销售额','参与人数','企微新增'],top:0}},
  grid:{{left:50,right:30,bottom:30,top:30}}, xAxis:{{type:'category',data:chNames}},
  yAxis:[{{type:'value'}},{{type:'value',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}}],
  series:[
    {{name:'活动数量',type:'bar',data:ch.map(r=>r.activities),itemStyle:{{color:COLORS[0]}}}},
    {{name:'销售额',type:'bar',yAxisIndex:1,data:ch.map(r=>Math.round(r.sales||0)),itemStyle:{{color:COLORS[1]}}}},
    {{name:'参与人数',type:'line',data:ch.map(r=>r.participants),itemStyle:{{color:COLORS[2]}}}},
    {{name:'企微新增',type:'line',data:ch.map(r=>r.wechat),itemStyle:{{color:COLORS[4]}}}},
  ] }});
document.getElementById('channel-table').innerHTML = `<table><thead><tr>
  <th>渠道</th><th class="text-right">活动数量</th><th class="text-right">销售额</th><th class="text-right">转化主机</th>
  <th class="text-right">参与人数</th><th class="text-right">企微新增</th><th class="text-right">单场销售额</th><th class="text-right">转化率</th>
</tr></thead><tbody>${{ch.map(r=>`<tr><td>${{r.channel}}</td><td class="text-right">${{fmt(r.activities)}}</td>
  <td class="text-right">¥${{fmt(r.sales)}}</td><td class="text-right">${{fmt(r.hosts)}}</td>
  <td class="text-right">${{fmt(r.participants)}}</td><td class="text-right">${{fmt(r.wechat)}}</td>
  <td class="text-right">¥${{fmt(r.avg_sales)}}</td><td class="text-right">${{fmtPct(r.conversion)}}</td></tr>`).join('')}}</tbody></table>`;

// ── Part 10: Drone ──────────────────────────
const dr = D.drone;
const dc = initChart('c-drone');
dc.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:['活动数量','销售额','参与人数','企微新增','单场销售额'],top:0}},
  grid:{{left:50,right:50,bottom:30,top:30}}, xAxis:{{type:'category',data:['无人机活动','普通活动']}},
  yAxis:[{{type:'value'}},{{type:'value',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}}],
  series:[
    {{name:'活动数量',type:'bar',data:[dr.drone.count,dr.normal.count],itemStyle:{{color:COLORS[0]}}}},
    {{name:'销售额',type:'bar',yAxisIndex:1,data:[Math.round(dr.drone.sales),Math.round(dr.normal.sales)],itemStyle:{{color:COLORS[1]}}}},
    {{name:'参与人数',type:'line',data:[dr.drone.participants,dr.normal.participants],itemStyle:{{color:COLORS[2]}}}},
    {{name:'企微新增',type:'line',data:[dr.drone.wechat,dr.normal.wechat],itemStyle:{{color:COLORS[4]}}}},
    {{name:'单场销售额',type:'line',yAxisIndex:1,data:[Math.round(dr.drone.avg_sales),Math.round(dr.normal.avg_sales)],itemStyle:{{color:COLORS[3]}}}},
  ] }});
document.getElementById('drone-table').innerHTML = `<table><thead><tr>
  <th>类型</th><th class="text-right">活动数量</th><th class="text-right">销售额</th><th class="text-right">参与人数</th>
  <th class="text-right">转化主机</th><th class="text-right">企微新增</th><th class="text-right">单场销售额</th>
</tr></thead><tbody>
  <tr><td>无人机活动</td><td class="text-right">${{fmt(dr.drone.count)}}</td><td class="text-right">¥${{fmt(dr.drone.sales)}}</td>
  <td class="text-right">${{fmt(dr.drone.participants)}}</td><td class="text-right">${{fmt(dr.drone.hosts)}}</td>
  <td class="text-right">${{fmt(dr.drone.wechat)}}</td><td class="text-right">¥${{fmt(dr.drone.avg_sales)}}</td></tr>
  <tr><td>普通活动</td><td class="text-right">${{fmt(dr.normal.count)}}</td><td class="text-right">¥${{fmt(dr.normal.sales)}}</td>
  <td class="text-right">${{fmt(dr.normal.participants)}}</td><td class="text-right">${{fmt(dr.normal.hosts)}}</td>
  <td class="text-right">${{fmt(dr.normal.wechat)}}</td><td class="text-right">¥${{fmt(dr.normal.avg_sales)}}</td></tr>
</tbody></table><p style="margin-top:8px;font-size:13px;color:var(--text2)">无人机活动占比：${{fmtPct(dr.drone_ratio)}}</p>`;

// ── Part 11: Cooperation ────────────────────
const co = D.coop;
const cco1 = initChart('c-coop-compare');
cco1.setOption({{ tooltip:{{trigger:'axis'}}, legend:{{data:['活动数量','销售额','场均销售'],top:0}},
  grid:{{left:50,right:50,bottom:30,top:30}}, xAxis:{{type:'category',data:['异业合作','普通活动']}},
  yAxis:[{{type:'value'}},{{type:'value',axisLabel:{{formatter:v=>v>=10000?(v/10000).toFixed(0)+'万':v}}}}],
  series:[
    {{name:'活动数量',type:'bar',data:[co.coop.count,co.normal.count],itemStyle:{{color:COLORS[0]}}}},
    {{name:'销售额',type:'bar',yAxisIndex:1,data:[Math.round(co.coop.sales),Math.round(co.normal.sales)],itemStyle:{{color:COLORS[1]}}}},
    {{name:'场均销售',type:'line',yAxisIndex:1,data:[Math.round(co.coop.avg_sales),Math.round(co.normal.avg_sales)],itemStyle:{{color:COLORS[3]}}}},
  ] }});

const brands = (co.brands||[]).slice(0,10);
const cco2 = initChart('c-coop-brand');
cco2.setOption({{ tooltip:{{trigger:'axis'}}, grid:{{left:80,right:30,bottom:20,top:20}},
  xAxis:{{type:'value'}}, yAxis:{{type:'category',data:brands.map(r=>r.brand).reverse(),axisLabel:{{fontSize:10}}}},
  series:[{{type:'bar',data:brands.map(r=>r.coop_count).reverse(),itemStyle:{{color:COLORS[5]}},label:{{show:true,position:'right',fontSize:10}}}}] }});

// ── Part 12: Cases ──────────────────────────
const cases = D.cases;
document.getElementById('cases-list').innerHTML = cases.map((c,i)=>`<div class="case-card">
  <div class="case-rank">#${{i+1}}</div>
  <div class="case-info">
    <div class="cn">${{c.activity_desc}}</div>
    <div class="cm">${{c.store_name||'-'}} · ${{c.activity_type||'-'}} · ${{c.activity_date}} · 评分${{c.score}}</div>
    <div class="cr">推荐复制：${{c.recommend_reason}}</div>
  </div>
  <div class="case-sales"><div class="amount">¥${{fmt(c.sales)}}</div>
  <div class="meta">参与${{fmt(c.participants)}}人 · 企微${{fmt(c.wechat)}} · 主机${{fmt(c.hosts)}}</div></div>
</div>`).join('');

// ── Part 13: Summary ────────────────────────
const sums = D.summaries;
const catClass = {{'Q2经营亮点':'hl','Q2存在问题':'prob','Q3重点方向':'q3'}};
document.getElementById('summary-list').innerHTML = sums.map(s=>`
  <div class="summary-cat ${{catClass[s.category]||''}}">${{s.category}}</div>
  ${{s.items.map(item=>`<div class="summary-item">
    <div class="si-label">【发现】</div><div class="si-text">${{item.finding}}</div>
    <div class="si-label">【原因】</div><div class="si-text">${{item.cause}}</div>
    <div class="si-label">【影响】</div><div class="si-text">${{item.impact}}</div>
    <div class="si-label">【建议】</div><div class="si-suggest">${{item.suggestion}}</div>
  </div>`).join('')}}
`).join('');

// ── Export ──────────────────────────────────
function exportPNG() {{
  // Find the largest chart and export
  Object.values(charts).forEach((c,i)=>{{
    if(c) {{ const url=c.getDataURL({{type:'png',pixelRatio:2}}); const a=document.createElement('a'); a.href=url; a.download=`q2_chart_${{i}}.png`; a.click(); }}
  }});
}}
function exportExcel() {{
  // Export all tables as CSV
  let csv='';
  document.querySelectorAll('table').forEach(t=>{{
    csv += t.innerText.replace(/\\n/g,'\\n')+'\\n\\n';
  }});
  const blob=new Blob(['\\ufeff'+csv],{{type:'text/csv'}}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download='Q2经营复盘数据.csv'; a.click();
}}

window.addEventListener('resize',()=>{{ Object.values(charts).forEach(c=>c&&c.resize()); }});
</script>
</body>
</html>'''

    # Fill in header values
    h = data["header"]
    html = html.replace("__HEADER_TIME__", h["refresh_time"])
    html = html.replace("__TOTAL_RECORDS__", str(h["total_records"]))
    html = html.replace("__EFFECTIVE_COUNT__", str(h["effective_count"]))

    return html


if __name__ == "__main__":
    print("生成 Q2 季度经营复盘 HTML...")
    html = generate_q2_html()
    output_path = "output/2026 Q2 线下活动经营复盘.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    import os
    print(f"已生成: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)")
