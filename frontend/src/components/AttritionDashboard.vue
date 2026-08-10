<template>
  <div class="attrition-dashboard">
    <!-- 头部 -->
    <header class="dashboard-header">
      <div class="header-left">
        <h1>📊 离职分析看板</h1>
        <span class="update-tag">实时更新</span>
        <div class="view-toggle">
          <button :class="['toggle-btn', { active: viewType === 'monthly' }]" @click="switchView('monthly')">月度</button>
          <button :class="['toggle-btn', { active: viewType === 'yearly' }]" @click="switchView('yearly')">年度</button>
        </div>
      </div>
      <div class="header-right">
        <span class="update-time">🕐 {{ updatedAt }}</span>
        <button class="refresh-btn" @click="loadData" :disabled="loading">{{ loading ? '⏳' : '🔄' }}</button>
      </div>
    </header>

    <!-- 概览卡片 -->
    <div class="kpi-row">
      <div class="kpi-card" v-for="k in kpis" :key="k.key" :style="{ borderTop: '3px solid ' + k.color }">
        <div class="kpi-label">{{ k.label }}</div>
        <div class="kpi-value" :style="{ color: k.color }">{{ k.val }}</div>
        <div class="kpi-unit">{{ k.unit }}</div>
      </div>
    </div>

    <!-- 图表行 -->
    <div class="chart-row">
      <div class="card">
        <div class="card-header"><h2>🏢 各部门离职人数</h2></div>
        <div ref="deptChartRef" style="height: 220px"></div>
      </div>
      <div class="card">
        <div class="card-header"><h2>📌 离职原因分布</h2></div>
        <div ref="reasonChartRef" style="height: 220px"></div>
      </div>
    </div>

    <!-- 离职周期 -->
    <div class="card">
      <div class="card-header"><h2>⏱ 离职周期分布（司龄段）</h2></div>
      <div ref="tenureChartRef" style="height: 220px"></div>
    </div>

    <!-- 月度趋势 -->
    <div class="card">
      <div class="card-header"><h2>📈 离职趋势（{{ label }}）</h2></div>
      <div ref="trendChartRef" style="height: 200px"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 10000 })

const loading = ref(false)
const updatedAt = ref('--')
const viewType = ref('monthly')
const label = ref('')
const data = ref(null)

const deptChartRef = ref(null)
const reasonChartRef = ref(null)
const tenureChartRef = ref(null)
const trendChartRef = ref(null)
let deptChart = null, reasonChart = null, tenureChart = null, trendChart = null
let timer = null

const kpis = computed(() => {
  const d = data.value?.overview
  if (!d) return []
  return [
    { key: 'leavers', label: '离职总人数', val: d.total_leavers, unit: '人', color: '#ef4444' },
    { key: 'voluntary', label: '主动离职', val: d.voluntary, unit: '人', color: '#f59e0b' },
    { key: 'involuntary', label: '被动离职', val: d.involuntary, unit: '人', color: '#6b7280' },
    { key: 'rate', label: '离职率', val: d.attrition_rate, unit: '%', color: '#3b82f6' },
    { key: 'hc', label: '在岗人数', val: d.headcount, unit: '人', color: '#10b981' },
  ]
})

async function loadData() {
  loading.value = true
  try {
    const res = await api.get('/attrition', { params: { view_type: viewType.value } })
    data.value = res.data
    label.value = res.data.label
    updatedAt.value = res.data.updated_at
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function switchView(t) { viewType.value = t; loadData() }

function renderCharts() {
  if (!data.value) return
  const d = data.value

  // 部门
  if (deptChartRef.value) {
    if (!deptChart) deptChart = echarts.init(deptChartRef.value)
    deptChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 10, right: 40, top: 5, bottom: 5, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } } },
      yAxis: { type: 'category', data: d.by_dept.map(i => i.department).reverse(), axisLine: { show: false }, axisTick: { show: false } },
      series: [{
        type: 'bar', barWidth: 10,
        itemStyle: { color: '#ef4444', borderRadius: [0, 6, 6, 0] },
        label: { show: true, position: 'right', fontSize: 11, fontWeight: 600, formatter: (p) => `${p.value}人` },
        data: d.by_dept.map(i => i.leavers).reverse(),
      }],
    }, true); deptChart.resize()
  }

  // 原因
  if (reasonChartRef.value) {
    if (!reasonChart) reasonChart = echarts.init(reasonChartRef.value)
    reasonChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '55%'],
        label: { show: true, formatter: '{b}\n{d}%', fontSize: 10 },
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        data: d.by_reason.map((r, i) => ({
          name: r.reason, value: r.count,
          itemStyle: { color: ['#ef4444','#f59e0b','#3b82f6','#10b981','#8b5cf6','#ec4899'][i] },
        })),
      }],
    }, true); reasonChart.resize()
  }

  // 趋势
  if (trendChartRef.value) {
    if (!trendChart) trendChart = echarts.init(trendChartRef.value)
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['离职人数', '离职率'], bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 40, right: 40, top: 10, bottom: 35 },
      xAxis: { type: 'category', data: d.monthly_trend.map(i => i.month), axisLabel: { fontSize: 10 } },
      yAxis: [
        { type: 'value', name: '人数', min: 0, splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } } },
        { type: 'value', name: '%', min: 0, splitLine: { show: false } },
      ],
      series: [
        { name: '离职人数', type: 'bar', barWidth: 12, itemStyle: { color: '#ef4444', borderRadius: [4,4,0,0] }, data: d.monthly_trend.map(i => i.leavers) },
        { name: '离职率', type: 'line', smooth: true, yAxisIndex: 1, symbol: 'circle', symbolSize: 6, lineStyle: { color: '#3b82f6', width: 2 }, itemStyle: { color: '#3b82f6' }, data: d.monthly_trend.map(i => i.rate) },
      ],
    }, true); trendChart.resize()
  }

  // 离职周期
  if (tenureChartRef.value) {
    if (!tenureChart) tenureChart = echarts.init(tenureChartRef.value)
    tenureChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}<br/>人数: <b>${p[0].value}</b> (${p[0].data.percent})` },
      grid: { left: 10, right: 50, top: 5, bottom: 5, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } } },
      yAxis: { type: 'category', data: d.by_tenure.map(i => i.range), axisLine: { show: false }, axisTick: { show: false } },
      series: [{
        type: 'bar', barWidth: 12,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#fca5a5' }, { offset: 1, color: '#ef4444' },
          ]),
          borderRadius: [0, 8, 8, 0],
        },
        label: { show: true, position: 'right', fontSize: 11, fontWeight: 600, formatter: (p) => `${p.value}人 (${p.data.percent})` },
        data: d.by_tenure.map(i => ({ value: i.count, percent: i.percentage + '%' })),
      }],
    }, true); tenureChart.resize()
  }
}

watch(() => data.value, renderCharts)
onMounted(() => { loadData(); timer = setInterval(loadData, 30000); window.addEventListener('resize', () => { deptChart?.resize(); reasonChart?.resize(); tenureChart?.resize(); trendChart?.resize() }) })
onUnmounted(() => { if (timer) clearInterval(timer); window.removeEventListener('resize', () => {}); deptChart?.dispose(); reasonChart?.dispose(); tenureChart?.dispose(); trendChart?.dispose() })
</script>

<style scoped>
.attrition-dashboard { max-width: 1200px; margin: 0 auto; padding: 0; }
.dashboard-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #e8e8e8;
}
.header-left { display: flex; align-items: center; gap: 10px; }
.header-left h1 { font-size: 20px; font-weight: 700; }
.update-tag { font-size: 11px; background: #4f46e5; color: #fff; padding: 2px 10px; border-radius: 10px; }
.view-toggle { display: inline-flex; border: 1px solid #d1d5db; border-radius: 6px; overflow: hidden; }
.toggle-btn { padding: 4px 12px; font-size: 12px; border: none; cursor: pointer; background: #fff; color: #6b7280; font-weight: 500; transition: 0.15s; }
.toggle-btn.active { background: #4f46e5; color: #fff; }
.toggle-btn:not(.active):hover { background: #f3f4f6; }
.header-right { display: flex; align-items: center; gap: 14px; }
.update-time { font-size: 13px; color: #888; }
.refresh-btn { padding: 7px 14px; border: none; border-radius: 6px; background: #4f46e5; color: #fff; font-size: 13px; cursor: pointer; }
.refresh-btn:hover { background: #4338ca; }
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.kpi-card { background: #fff; border-radius: 10px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.kpi-label { font-size: 12px; color: #6b7280; }
.kpi-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.kpi-unit { font-size: 11px; color: #9ca3af; }

.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.card { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.card-header { margin-bottom: 8px; }
.card-header h2 { font-size: 14px; font-weight: 600; color: #1a1a2e; }
@media (max-width: 800px) { .kpi-row { grid-template-columns: repeat(3, 1fr); } .chart-row { grid-template-columns: 1fr; } }
</style>
