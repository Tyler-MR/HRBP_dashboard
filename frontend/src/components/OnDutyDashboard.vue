<template>
  <div class="onduty">
    <header class="page-header">
      <h1><i class="ic ic-chart"></i> 各部门在岗时长统计及分析建议</h1>
      <span class="update-tag">钉钉多维表实时数据</span>
      <div class="month-picker">
        <select v-model="month" @change="loadStats">
          <option v-for="m in months" :key="m" :value="m">{{ m.replace('-', '年') }}月</option>
        </select>
      </div>
      <span class="update-time"><i class="ic ic-clock"></i> {{ updatedAt }}</span>
      <button class="refresh-btn" @click="loadStats" title="刷新"><i class="ic ic-refresh"></i></button>
    </header>

    <div v-if="error" class="error-banner">
      <i class="ic ic-alert"></i> {{ error }}
    </div>
    <div v-if="loading" class="loading-tip"><span class="spinner"></span> 数据加载中，请稍候…</div>

    <template v-if="!loading && stats.depts && stats.depts.length">
      <!-- 统计卡 -->
      <div class="stat-cards">
        <div class="stat-card"><div class="stat-val">{{ stats.overview.dept_count }}</div><div class="stat-label">部门数</div></div>
        <div class="stat-card"><div class="stat-val">{{ stats.overview.person_count }}</div><div class="stat-label">统计人数</div></div>
        <div class="stat-card"><div class="stat-val">{{ stats.overview.all_avg_onduty?.display || '—' }}</div><div class="stat-label">全员平均在岗</div></div>
        <div class="stat-card">
          <div class="stat-val sm">{{ stats.overview.max_dept?.name }} {{ stats.overview.max_dept?.display }}</div>
          <div class="stat-label">最长在岗部门（最短：{{ stats.overview.min_dept?.name }} {{ stats.overview.min_dept?.display }}）</div>
        </div>
      </div>

      <!-- 部门在岗时长排行 -->
      <div class="section-title"><i class="ic ic-rank ic-green"></i> 部门人均在岗时长排行（{{ monthLabel }}）</div>
      <div class="chart-panel">
        <div ref="barEl" class="chart-box"></div>
      </div>
      <div class="section-title"><i class="ic ic-rank ic-indigo"></i> 部门人均上下班打卡时间</div>
      <div class="chart-panel">
        <div ref="clockEl" class="chart-box"></div>
      </div>

      <!-- 部门详情表 -->
      <div class="section-title"><i class="ic ic-rank ic-indigo"></i> 部门统计明细</div>
      <div class="rank-table-wrap">
        <table class="rank-table">
          <thead>
            <tr>
              <th>部门</th><th>一级部门</th><th>人数</th><th>人均在岗时长</th>
              <th>人均上班打卡</th><th>人均下班打卡</th><th>部门成员（点部门筛选）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in stats.depts" :key="d.dept"
                :class="['rank-row', { selected: filterDept === d.dept }]"
                @click="filterDept = filterDept === d.dept ? '' : d.dept">
              <td class="name-cell">{{ d.dept }}</td>
              <td>{{ d.l1 }}</td>
              <td>{{ d.count }}</td>
              <td class="score-cell"><b>{{ d.avg_onduty.display }}</b></td>
              <td>{{ d.avg_on.display || '—' }}</td>
              <td>{{ d.avg_off.display || '—' }}</td>
              <td class="tip-cell">{{ d.persons.map(p => p.name).join('、') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 个人明细 -->
      <div class="section-title">
        <i class="ic ic-rank ic-green"></i> 个人平均在岗明细
        <select v-model="filterDept" class="mini-select">
          <option value="">全部部门</option>
          <option v-for="d in stats.depts" :key="d.dept" :value="d.dept">{{ d.dept }}</option>
        </select>
      </div>
      <div class="rank-table-wrap">
        <table class="rank-table">
          <thead>
            <tr><th>部门</th><th>姓名</th><th>岗位</th><th>平均上班</th><th>平均下班</th><th>平均在岗</th><th>部门人均在岗</th><th>与部门人均差</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in filteredPersons" :key="p.dept + p.name">
              <td>{{ p.dept }}</td>
              <td class="name-cell">{{ p.name }}</td>
              <td>{{ p.position }}</td>
              <td>{{ p.on_time.display }}</td>
              <td>{{ p.off_time.display }}</td>
              <td class="score-cell"><b>{{ p.onduty.display }}</b></td>
              <td>{{ p.dept_onduty.display }}</td>
              <td :class="diffCls(p)">{{ diffText(p) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分析建议 -->
      <div class="section-title"><i class="ic ic-alert ic-orange"></i> 分析建议（规则引擎）</div>
      <div class="suggest-list">
        <div v-for="(s, i) in stats.suggestions" :key="i" class="suggest-item" :class="s.level">
          <span class="suggest-icon">{{ s.type === 'deviation_high' ? '📈' : s.type === 'deviation_low' ? '📉' : s.type === 'late_off' ? '🌙' : s.type === 'late_on' ? '⏰' : s.type.startsWith('personal') ? '👤' : '💡' }}</span>
          <span class="suggest-text">{{ s.text }}</span>
          <span class="suggest-tag" :class="s.level">{{ s.level === 'dept' ? '部门' : '个人' }}</span>
        </div>
        <div v-if="!stats.suggestions.length" class="no-suggest">✅ 本月无异常：各部门在岗时长均在合理区间</div>
      </div>
    </template>

    <div v-else-if="!loading && stats.note" class="no-log-tip">{{ stats.note }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

const INDIGO = '#4f46e5'
const GREEN = '#059669'

const stats = ref({ depts: [], overview: {}, suggestions: [], months: [] })
const month = ref('')
const months = ref([])
const loading = ref(false)
const error = ref('')
const updatedAt = ref('')
const filterDept = ref('')
const barEl = ref(null)
const clockEl = ref(null)
let barChart = null
let clockChart = null

const monthLabel = computed(() => (month.value || '').replace('-', '年') + '月')

const filteredPersons = computed(() => {
  const all = (stats.value.depts || []).flatMap(d =>
    (d.persons || []).map(p => ({ ...p, dept: d.dept })))
  return filterDept.value ? all.filter(p => p.dept === filterDept.value) : all
})

const fmtMin = (m) => m == null ? '' : `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
const diffText = (p) => {
  const pv = p.onduty.minutes, dv = p.dept_onduty.minutes
  if (pv == null || dv == null) return '—'
  const d = pv - dv
  if (d === 0) return '持平'
  return `${d > 0 ? '+' : '-'}${fmtMin(Math.abs(d))}`
}
const diffCls = (p) => {
  const pv = p.onduty.minutes, dv = p.dept_onduty.minutes
  if (pv == null || dv == null) return ''
  const d = pv - dv
  return Math.abs(d) >= 60 ? (d > 0 ? 'diff-high' : 'diff-low') : 'diff-ok'
}

async function loadStats() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/onduty-stats', { params: { month: month.value } })
    stats.value = res.data
    months.value = res.data.months || []
    if (res.data.month && !month.value) month.value = res.data.month
    if (res.data.source_error) error.value = res.data.source_error
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    await nextTick()
    renderCharts()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  if (!barEl.value || !clockEl.value || !stats.value.depts?.length) return
  const depts = stats.value.depts

  // 部门人均在岗时长排行（横向柱状）
  barChart = barChart || echarts.init(barEl.value)
  barChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (ps) => {
        const p = ps[0]
        const d = depts.find(x => x.dept === p.name)
        return `${p.name}：人均在岗 <b>${d?.avg_onduty.display}</b>（${d?.count}人）`
      },
    },
    grid: { left: 90, right: 60, top: 10, bottom: 24 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: (v) => fmtMin(v) },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
    },
    yAxis: { type: 'category', data: depts.map(d => d.dept), inverse: true, axisLabel: { color: '#1a1a2e' } },
    series: [{
      type: 'bar', data: depts.map(d => d.avg_onduty.minutes), barWidth: 16,
      itemStyle: { color: GREEN, borderRadius: [0, 8, 8, 0] },
      label: { show: true, position: 'right', formatter: (p) => depts[p.dataIndex]?.avg_onduty.display, color: '#065f46', fontWeight: 600 },
    }],
  })

  // 部门人均上下班打卡时间（分组横向）
  clockChart = clockChart || echarts.init(clockEl.value)
  clockChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['人均上班打卡', '人均下班打卡'], right: 10, top: 0 },
    grid: { left: 90, right: 60, top: 30, bottom: 24 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: (v) => fmtMin(v) },
      splitLine: { lineStyle: { color: '#f3f4f6' } },
    },
    yAxis: { type: 'category', data: depts.map(d => d.dept), inverse: true, axisLabel: { color: '#1a1a2e' } },
    series: [
      {
        name: '人均上班打卡', type: 'bar', data: depts.map(d => d.avg_on.minutes), barWidth: 12,
        itemStyle: { color: INDIGO, borderRadius: [0, 6, 6, 0] },
      },
      {
        name: '人均下班打卡', type: 'bar', data: depts.map(d => d.avg_off.minutes), barWidth: 12,
        itemStyle: { color: GREEN, borderRadius: [0, 6, 6, 0] },
      },
    ],
  })
}

function onResize() {
  barChart?.resize()
  clockChart?.resize()
}

onMounted(() => {
  loadStats()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  barChart?.dispose()
  clockChart?.dispose()
})
</script>

<style scoped>
.onduty { padding: 20px 24px; }
.page-header { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.page-header h1 { font-size: 20px; color: #1a1a2e; display: flex; align-items: center; gap: 8px; }
.update-tag { font-size: 12px; color: #059669; background: #ecfdf5; padding: 3px 10px; border-radius: 20px; }
.update-time { font-size: 12px; color: #8b8fa8; }
.refresh-btn { border: none; background: #fff; border-radius: 8px; padding: 6px 10px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.month-picker select { padding: 7px 12px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; background: #fff; color: #1a1a2e; outline: none; cursor: pointer; }

.error-banner { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; padding: 12px 16px; border-radius: 10px; margin-bottom: 14px; font-size: 13px; }
.loading-tip { text-align: center; padding: 60px 0; color: #8b8fa8; font-size: 14px; }
.no-log-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 16px; border-radius: 10px; text-align: center; font-size: 14px; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #c7d2fe; border-top-color: #4f46e5; border-radius: 50%; animation: spin .8s linear infinite; vertical-align: -3px; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.stat-val { font-size: 28px; font-weight: 700; color: #4f46e5; }
.stat-val.sm { font-size: 18px; }
.stat-label { font-size: 13px; color: #8b8fa8; margin-top: 4px; }

.section-title { font-size: 16px; font-weight: 700; color: #1a1a2e; margin: 20px 0 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mini-select { padding: 6px 10px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; background: #fff; color: #1a1a2e; outline: none; cursor: pointer; margin-left: auto; }

.chart-panel { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.05); margin-bottom: 4px; }
.chart-box { height: 380px; }

.rank-table-wrap { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.05); overflow-x: auto; }
.rank-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank-table th { background: #4f46e5; color: #fff; padding: 10px 12px; text-align: left; white-space: nowrap; font-weight: 600; }
.rank-table td { padding: 9px 12px; border-bottom: 1px solid #f3f4f6; white-space: nowrap; }
.rank-row { cursor: pointer; }
.rank-row:hover { background: #f5f7ff; }
.rank-row.selected { background: #eef2ff; }
.name-cell { font-weight: 600; color: #1a1a2e; }
.score-cell b { font-size: 15px; color: #4f46e5; }
.tip-cell { white-space: normal; line-height: 1.5; font-size: 12px; min-width: 200px; }

.diff-ok { color: #8b8fa8; }
.diff-high { color: #dc2626; font-weight: 600; }
.diff-low { color: #059669; font-weight: 600; }

.suggest-list { display: flex; flex-direction: column; gap: 10px; }
.suggest-item { display: flex; align-items: flex-start; gap: 10px; background: #fff; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.05); border-left: 4px solid #4f46e5; }
.suggest-item.person { border-left-color: #059669; background: #fafffd; }
.suggest-icon { font-size: 18px; }
.suggest-text { font-size: 13px; color: #1a1a2e; line-height: 1.7; flex: 1; }
.suggest-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; white-space: nowrap; }
.suggest-tag.dept { background: #eef2ff; color: #3730a3; }
.suggest-tag.person { background: #ecfdf5; color: #047857; }
.no-suggest { background: #ecfdf5; border: 1px solid #a7f3d0; color: #047857; padding: 14px 16px; border-radius: 10px; font-size: 13px; }
</style>
