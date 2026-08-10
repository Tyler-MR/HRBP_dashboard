<template>
  <div class="efficiency-dashboard">
    <!-- 头部 -->
    <header class="dashboard-header">
      <div class="header-left">
        <h1>📊 人效看板</h1>
        <span class="update-tag">实时更新</span>
      </div>
      <div class="header-right">
        <span class="update-time">🕐 {{ updatedAt }}</span>
        <button class="refresh-btn" @click="loadData">🔄</button>
      </div>
    </header>

    <!-- 粒度切换：年度 / 半年度 / 季度 / 月度 -->
    <div class="period-bar">
      <button v-for="p in periods" :key="p.value"
        :class="['period-btn', { active: period === p.value }]"
        @click="setPeriod(p.value)">
        {{ p.label }}
      </button>
    </div>

    <!-- KPI 卡片行 -->
    <div class="kpi-row">
      <div class="kpi-card" v-for="kpi in summaryCards" :key="kpi.label"
        :style="{ borderTop: `3px solid ${kpi.color}` }">
        <div class="kpi-label">{{ kpi.label }}</div>
        <div class="kpi-value" :style="{ color: kpi.color }">{{ kpi.value }}</div>
        <div class="kpi-unit">{{ kpi.unit }}</div>
      </div>
    </div>

    <!-- 图表区域 — 第一行 -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-header">
          <h3>📈 营收与人力成本关系</h3>
          <span class="badge">月度趋势对比</span>
        </div>
        <v-chart :option="revenueCostOption" autoresize class="chart-lg" />
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <h3>👥 在岗人数与人力总成本关系</h3>
          <span class="badge">规模与投入</span>
        </div>
        <v-chart :option="headcountCostOption" autoresize class="chart-lg" />
      </div>
    </div>

    <!-- 图表区域 — 第二行 -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-header">
          <h3>💰 净利润与人力成本关系</h3>
          <span class="badge">盈利与投入对比</span>
        </div>
        <v-chart :option="profitCostOption" autoresize class="chart-lg" />
      </div>
      <div class="chart-card">
        <div class="chart-header">
          <h3>📊 成本效能趋势</h3>
          <span class="badge">每元人力成本产出营收</span>
        </div>
        <v-chart :option="costEfficiencyOption" autoresize class="chart-lg" />
      </div>
    </div>

    <!-- 图表区域 — 第三行：人均指标对比 -->
    <div class="chart-card full-width">
      <div class="chart-header">
        <h3>🎯 人均指标月度对比</h3>
        <span class="badge">人均收入 · 人均成本 · 人均净利润</span>
      </div>
      <v-chart :option="perCapitaOption" autoresize class="chart-xl" />
    </div>

    <!-- 月度数据明细表格 -->
    <div class="chart-card full-width">
      <div class="chart-header">
        <h3>📋 人效数据明细</h3>
        <span class="badge">{{ periodText }}视图</span>
      </div>
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>期间</th>
              <th>营收(万)</th>
              <th>净利润(万)</th>
              <th>人力总成本(万)</th>
              <th>在岗人数</th>
              <th>人均收入(万)</th>
              <th>人均成本(万)</th>
              <th>人均净利润(万)</th>
              <th>成本效能</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in monthly" :key="row.month">
              <td class="month-cell">{{ row.label }}</td>
              <td>{{ row.revenue }}</td>
              <td>{{ row.net_profit }}</td>
              <td>{{ row.total_labor_cost }}</td>
              <td>{{ row.headcount }}</td>
              <td>{{ row.revenue_per_employee }}</td>
              <td>{{ row.cost_per_employee }}</td>
              <td>{{ row.profit_per_employee }}</td>
              <td>
                <span :class="['badge-eff', row.cost_efficiency >= 2.0 ? 'high' : row.cost_efficiency >= 1.5 ? 'mid' : 'low']">
                  {{ row.cost_efficiency }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button :class="['tab-btn', { active: activeTab === 'efficiency' }]" @click="activeTab='efficiency'">📊 人效数据</button>
      <button :class="['tab-btn', { active: activeTab === 'talent' }]" @click="activeTab='talent'">🧬 人才质量分析</button>
    </div>

    <TalentAnalysisPanel v-if="activeTab === 'talent'" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, ToolboxComponent, DataZoomComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchHrEfficiency } from '../api/index.js'
import TalentAnalysisPanel from './TalentAnalysisPanel.vue'

use([
  CanvasRenderer, BarChart, LineChart,
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, ToolboxComponent, DataZoomComponent,
])

const monthly = ref([])
const summary = ref(null)
const updatedAt = ref('--')
const activeTab = ref('efficiency')
let timer = null

// 粒度切换：年度/半年度/季度/月度
const periods = [
  { value: 'year', label: '年度' },
  { value: 'half', label: '半年度' },
  { value: 'quarter', label: '季度' },
  { value: 'month', label: '月度' },
]
const period = ref('month')
const periodText = computed(() => periods.find(p => p.value === period.value)?.label || '月度')
function setPeriod(v) {
  period.value = v
  loadData()
}
// 图表 x 轴标签（后端 label：2024-01 / 2024-Q1 / 2024-H1 / 2024）
const xLabels = computed(() => monthly.value.map(m => m.label))

const COLORS = {
  revenue: '#4f46e5',
  netProfit: '#10b981',
  laborCost: '#f59e0b',
  headcount: '#8b5cf6',
  revPerEmp: '#3b82f6',
  costPerEmp: '#ef4444',
  profitPerEmp: '#22c55e',
  costEff: '#f97316',
}

const summaryCards = computed(() => {
  const s = summary.value
  if (!s) return []
  return [
    { label: '年度营收', value: s.total_revenue, unit: '万元', color: COLORS.revenue },
    { label: '年度净利润', value: s.total_net_profit, unit: '万元', color: COLORS.netProfit },
    { label: '年均在岗人数', value: s.avg_headcount, unit: '人', color: COLORS.headcount },
    { label: '人均收入', value: s.avg_revenue_per_employee, unit: '万元', color: COLORS.revPerEmp },
    { label: '人均成本', value: s.avg_cost_per_employee, unit: '万元', color: COLORS.costPerEmp },
    { label: '人均净利润', value: s.avg_profit_per_employee, unit: '万元', color: COLORS.profitPerEmp },
    { label: '成本效能', value: s.avg_cost_efficiency, unit: '', color: COLORS.costEff },
  ]
})

// 图表通用 tooltip
const tooltip = { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.96)', borderWidth: 0, borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }

// 1. 营收与人力成本关系
const revenueCostOption = computed(() => ({
  tooltip: { ...tooltip, axisPointer: { type: 'cross' } },
  legend: { data: ['营业收入', '人力总成本'], bottom: 0, icon: 'circle', itemWidth: 8 },
  grid: { top: 20, right: 20, bottom: 40, left: 50 },
  xAxis: { type: 'category', data: xLabels.value, axisLabel: { fontSize: 11 } },
  yAxis: [
    { type: 'value', name: '营收（万元）', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
    { type: 'value', name: '成本（万元）', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { show: false } },
  ],
  series: [
    {
      name: '营业收入', type: 'bar', data: monthly.value.map(m => m.revenue),
      itemStyle: { color: COLORS.revenue, borderRadius: [4, 4, 0, 0] },
      barWidth: '32%',
    },
    {
      name: '人力总成本', type: 'line', yAxisIndex: 1, data: monthly.value.map(m => m.total_labor_cost),
      lineStyle: { color: COLORS.laborCost, width: 3 }, symbol: 'circle', symbolSize: 8,
      itemStyle: { color: COLORS.laborCost },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.25)' }, { offset: 1, color: 'rgba(245,158,11,0.02)' }] } },
    },
  ],
}))

// 2. 在岗人数与人力总成本关系
const headcountCostOption = computed(() => ({
  tooltip: { ...tooltip, axisPointer: { type: 'cross' } },
  legend: { data: ['在岗人数', '人力总成本'], bottom: 0, icon: 'circle', itemWidth: 8 },
  grid: { top: 20, right: 20, bottom: 40, left: 50 },
  xAxis: { type: 'category', data: xLabels.value, axisLabel: { fontSize: 11 } },
  yAxis: [
    { type: 'value', name: '人数', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
    { type: 'value', name: '成本（万元）', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { show: false } },
  ],
  series: [
    {
      name: '在岗人数', type: 'bar', data: monthly.value.map(m => m.headcount),
      itemStyle: { color: COLORS.headcount, borderRadius: [4, 4, 0, 0] },
      barWidth: '32%',
    },
    {
      name: '人力总成本', type: 'line', yAxisIndex: 1, data: monthly.value.map(m => m.total_labor_cost),
      lineStyle: { color: COLORS.laborCost, width: 3 }, symbol: 'diamond', symbolSize: 8,
      itemStyle: { color: COLORS.laborCost },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.2)' }, { offset: 1, color: 'rgba(245,158,11,0.02)' }] } },
    },
  ],
}))

// 3. 净利润与人力成本关系
const profitCostOption = computed(() => ({
  tooltip: { ...tooltip, axisPointer: { type: 'cross' } },
  legend: { data: ['净利润', '人力总成本'], bottom: 0, icon: 'circle', itemWidth: 8 },
  grid: { top: 20, right: 20, bottom: 40, left: 50 },
  xAxis: { type: 'category', data: xLabels.value, axisLabel: { fontSize: 11 } },
  yAxis: [
    { type: 'value', name: '净利润（万元）', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
    { type: 'value', name: '成本（万元）', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { show: false } },
  ],
  series: [
    {
      name: '净利润', type: 'bar', data: monthly.value.map(m => m.net_profit),
      itemStyle: { color: COLORS.netProfit, borderRadius: [4, 4, 0, 0] },
      barWidth: '32%',
    },
    {
      name: '人力总成本', type: 'line', yAxisIndex: 1, data: monthly.value.map(m => m.total_labor_cost),
      lineStyle: { color: COLORS.laborCost, width: 3 }, symbol: 'roundRect', symbolSize: 8,
      itemStyle: { color: COLORS.laborCost },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(245,158,11,0.2)' }, { offset: 1, color: 'rgba(245,158,11,0.02)' }] } },
    },
  ],
}))

// 4. 成本效能趋势
const costEfficiencyOption = computed(() => ({
  tooltip: { ...tooltip, formatter: params => `${params[0].axisValue}<br/>成本效能：<strong>${params[0].value}</strong> （每元成本产出营收）` },
  grid: { top: 20, right: 20, bottom: 40, left: 50 },
  xAxis: { type: 'category', data: xLabels.value, axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', name: '成本效能', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
  visualMap: {
    show: false,
    pieces: [{ min: 2, color: COLORS.costEff }, { min: 1.5, max: 1.99, color: '#fbbf24' }, { max: 1.49, color: '#ef4444' }],
    calculable: false,
  },
  series: [{
    type: 'line',
    data: monthly.value.map(m => ({
      value: m.cost_efficiency,
      itemStyle: {
        color: m.cost_efficiency >= 2.0 ? COLORS.costEff : m.cost_efficiency >= 1.5 ? '#fbbf24' : '#ef4444',
      },
    })),
    lineStyle: { color: COLORS.costEff, width: 3 },
    symbol: 'circle', symbolSize: 9,
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(249,115,22,0.3)' },
          { offset: 1, color: 'rgba(249,115,22,0.02)' },
        ],
      },
    },
    markLine: {
      silent: true,
      data: [
        { yAxis: 2.0, label: { formatter: '优秀线 2.0', fontSize: 10, color: COLORS.costEff }, lineStyle: { color: COLORS.costEff, type: 'dashed' } },
        { yAxis: 1.5, label: { formatter: '基准线 1.5', fontSize: 10, color: '#fbbf24' }, lineStyle: { color: '#fbbf24', type: 'dashed' } },
      ],
    },
  }],
}))

// 5. 人均指标对比
const perCapitaOption = computed(() => ({
  tooltip: { ...tooltip, axisPointer: { type: 'cross' } },
  legend: { data: ['人均收入', '人均成本', '人均净利润'], bottom: 0, icon: 'circle', itemWidth: 8 },
  grid: { top: 20, right: 20, bottom: 40, left: 50 },
  xAxis: { type: 'category', data: xLabels.value, axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', name: '万元/人', nameTextStyle: { fontSize: 11, color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
  series: [
    {
      name: '人均收入', type: 'line', data: monthly.value.map(m => m.revenue_per_employee),
      lineStyle: { color: COLORS.revPerEmp, width: 3 },
      itemStyle: { color: COLORS.revPerEmp }, symbol: 'circle', symbolSize: 8,
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(59,130,246,0.2)' }, { offset: 1, color: 'rgba(59,130,246,0.02)' }] } },
    },
    {
      name: '人均成本', type: 'line', data: monthly.value.map(m => m.cost_per_employee),
      lineStyle: { color: COLORS.costPerEmp, width: 3 },
      itemStyle: { color: COLORS.costPerEmp }, symbol: 'diamond', symbolSize: 8,
    },
    {
      name: '人均净利润', type: 'line', data: monthly.value.map(m => m.profit_per_employee),
      lineStyle: { color: COLORS.profitPerEmp, width: 3 },
      itemStyle: { color: COLORS.profitPerEmp }, symbol: 'roundRect', symbolSize: 8,
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(34,197,94,0.2)' }, { offset: 1, color: 'rgba(34,197,94,0.02)' }] } },
    },
  ],
}))

async function loadData() {
  try {
    const data = await fetchHrEfficiency(period.value)
    monthly.value = data.monthly || []
    summary.value = data.summary
    updatedAt.value = data.updated_at || new Date().toLocaleString()
  } catch (err) {
    console.error('加载人效数据失败:', err)
  }
}

onMounted(() => { loadData(); timer = setInterval(loadData, 30000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.efficiency-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 头部 */
.dashboard-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; padding-bottom: 14px;
  border-bottom: 2px solid #e8e8e8;
}
.header-left { display: flex; align-items: center; gap: 10px; }
.header-left h1 { font-size: 22px; font-weight: 700; margin: 0; }
.update-tag {
  font-size: 11px; background: #4f46e5; color: #fff;
  padding: 2px 10px; border-radius: 10px; font-weight: 500;
}
.header-right { display: flex; align-items: center; gap: 14px; }
.update-time { font-size: 13px; color: #888; }
.refresh-btn {
  padding: 7px 14px; border: none; border-radius: 6px;
  background: #4f46e5; color: #fff; font-size: 13px;
  cursor: pointer; transition: 0.2s;
}
.refresh-btn:hover { background: #4338ca; }

/* 粒度切换：年度/半年度/季度/月度 */
.period-bar { display: flex; gap: 6px; margin-bottom: 16px; }
.period-btn {
  padding: 6px 16px; border: 1px solid #d1d5db; border-radius: 8px;
  background: #fff; color: #374151; font-size: 12px; font-weight: 500; cursor: pointer; transition: 0.15s;
}
.period-btn:hover { border-color: #4f46e5; color: #4f46e5; }
.period-btn.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }

/* KPI 卡片行 */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.kpi-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px 14px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}
.kpi-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}
.kpi-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}
.kpi-unit {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}

/* 图表卡片 */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.chart-card.full-width {
  grid-column: 1 / -1;
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.chart-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
}
.badge {
  font-size: 11px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 3px 10px;
  border-radius: 10px;
}
.chart-lg {
  height: 280px;
  width: 100%;
}
.chart-xl {
  height: 320px;
  width: 100%;
}

/* 数据表格 */
.table-wrapper {
  overflow-x: auto;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.data-table th {
  background: #f8fafc;
  color: #374151;
  font-weight: 600;
  padding: 10px 8px;
  text-align: center;
  border-bottom: 2px solid #e5e7eb;
  white-space: nowrap;
}
.data-table td {
  padding: 9px 8px;
  text-align: center;
  border-bottom: 1px solid #f3f4f6;
  color: #1f2937;
}
.data-table tbody tr:hover {
  background: #f9fafb;
}
.month-cell {
  font-weight: 600;
  color: #4f46e5;
}
.badge-eff {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 11px;
}
.badge-eff.high {
  background: #dcfce7;
  color: #16a34a;
}
.badge-eff.mid {
  background: #fef3c7;
  color: #d97706;
}
.badge-eff.low {
  background: #fee2e2;
  color: #dc2626;
}

/* Tab 切换 */
.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: #f3f4f6;
  border-radius: 10px;
  padding: 3px;
}
.tab-btn {
  flex: 1;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn:hover {
  color: #374151;
  background: rgba(79, 70, 229, 0.05);
}
.tab-btn.active {
  background: #4f46e5;
  color: #fff;
  box-shadow: 0 1px 3px rgba(79, 70, 229, 0.3);
}

@media (max-width: 960px) {
  .chart-row {
    grid-template-columns: 1fr;
  }
  .kpi-row {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
