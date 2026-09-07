<template>
  <div class="onduty">
    <header class="page-header">
      <h1><i class="ic ic-chart"></i> 各部门在岗时长统计及分析建议</h1>
      <span class="update-tag">每日 00:05 自动同步 · 支持手动同步</span>
      <div class="month-picker">
        <select v-model="month" @change="loadStats">
          <option v-for="m in months" :key="m" :value="m">{{ m.replace('-', '年') }}月</option>
        </select>
      </div>
      <span class="update-time"><i class="ic ic-clock"></i> {{ updatedAt }}</span>
      <button class="refresh-btn" @click="syncStats" :disabled="loading" title="立即同步钉钉在岗数据">
        <i class="ic ic-refresh"></i>{{ loading ? ' 同步中' : ' 同步' }}
      </button>
    </header>

    <div v-if="error" class="error-banner">
      <i class="ic ic-alert"></i> {{ error }}
    </div>
    <div v-if="loading" class="loading-tip"><span class="spinner"></span> 数据加载中，请稍候…</div>

    <div v-if="!loading && stats.overview.standard_schedule" class="schedule-baseline">
      <span class="baseline-label"><i class="ic ic-clock"></i> 标准班次基线</span>
      <b>{{ stats.overview.standard_schedule.start }}—{{ stats.overview.standard_schedule.end }}</b>
      <span>理论在岗 {{ stats.overview.standard_schedule.onduty }}</span>
      <em>实际人均在岗仍按钉钉数据统计，基线用于判断超出或不足</em>
    </div>

    <!-- 家清垂类电商经营分析报告：先结论，再证据与动作 -->
    <section v-if="!loading && stats.analysis_report" class="analysis-report" :class="'status-' + stats.analysis_report.status">
      <div class="analysis-head">
        <div>
          <div class="analysis-kicker">在岗时长经营分析报告 · {{ stats.analysis_report.period }}</div>
          <h2>{{ stats.analysis_report.title }}</h2>
          <p>{{ stats.analysis_report.subtitle }}</p>
        </div>
        <span class="analysis-status">
          {{ stats.analysis_report.status === 'ready' ? '已基于当前数据' : stats.analysis_report.status === 'unavailable' ? '实时数据暂不可用' : '当前周期无数据' }}
        </span>
      </div>
      <div class="analysis-headline"><b>核心结论：</b>{{ stats.analysis_report.headline }}</div>
      <div v-if="stats.analysis_report.conclusion" class="analysis-conclusion">
        <b>管理层最终判断：</b>{{ stats.analysis_report.conclusion }}
      </div>

      <div class="analysis-summary">
        <div v-for="(item, i) in stats.analysis_report.summary" :key="i" class="summary-item">{{ item }}</div>
      </div>

      <div v-if="stats.analysis_report.metrics?.length" class="analysis-metrics">
        <div v-for="metric in stats.analysis_report.metrics" :key="metric.label" class="analysis-metric">
          <div class="analysis-metric-label">{{ metric.label }}</div>
          <div class="analysis-metric-value">{{ metric.value }}</div>
          <div class="analysis-metric-note">{{ metric.note }}</div>
        </div>
      </div>

      <div v-if="stats.analysis_report.business_views?.length" class="analysis-section">
        <div class="analysis-section-title">业务链路解读</div>
        <div class="business-views">
          <article v-for="view in stats.analysis_report.business_views" :key="view.title" class="business-view-card">
            <h3>{{ view.title }}</h3>
            <div class="business-scope">{{ view.scope }}</div>
            <div class="business-focus"><b>重点看：</b>{{ view.focus }}</div>
            <p>{{ view.guidance }}</p>
          </article>
        </div>
      </div>

      <div v-if="stats.analysis_report.findings?.length" class="analysis-section">
        <div class="analysis-section-title">关键判断</div>
        <div class="analysis-findings">
          <article v-for="finding in stats.analysis_report.findings" :key="finding.title" class="finding-card">
            <h3>{{ finding.title }}</h3>
            <p>{{ finding.text }}</p>
            <div class="finding-evidence">依据：{{ finding.evidence }}</div>
          </article>
        </div>
      </div>

      <div v-if="stats.analysis_report.dept_insights?.length" class="analysis-section">
        <div class="analysis-section-title">各部门核查建议</div>
        <div class="dept-insight-list">
          <article v-for="insight in stats.analysis_report.dept_insights" :key="insight.dept" class="dept-insight-card">
            <div class="dept-insight-head">
              <div><h3>{{ insight.dept }}</h3><span>{{ insight.profile }} · {{ insight.count }}人</span></div>
              <span class="dept-insight-status">{{ insight.status }}</span>
            </div>
            <div class="dept-insight-metrics">
              <span>人均在岗 <b>{{ insight.avg_onduty }}</b></span>
              <span>较标准 <b>{{ insight.baseline_delta || '—' }}</b></span>
              <span>平均上班 <b>{{ insight.avg_on }}</b></span>
              <span>平均下班 <b>{{ insight.avg_off }}</b></span>
              <span>相对全员 <b>{{ insight.delta }}</b></span>
            </div>
            <div class="dept-insight-focus">重点看：{{ insight.focus }}</div>
            <p><b>分析：</b>{{ insight.analysis }}</p>
            <p><b>建议：</b>{{ insight.action }}<span v-if="insight.personal_outliers">（其中 {{ insight.personal_outliers }} 人需核查个人偏离）</span></p>
          </article>
        </div>
      </div>

      <div class="analysis-section">
        <div class="analysis-section-title">建议动作</div>
        <div class="analysis-actions">
          <div v-for="action in stats.analysis_report.actions" :key="action.title" class="action-item">
            <span class="action-priority">{{ action.priority }}</span>
            <div><b>{{ action.title }}</b><p>{{ action.text }}</p></div>
          </div>
        </div>
      </div>

      <details class="analysis-details">
        <summary>查看指标口径与待补充数据</summary>
        <div class="analysis-detail-grid">
          <div><b>指标口径</b><ul><li v-for="(definition, i) in stats.analysis_report.definitions" :key="'d' + i">{{ definition }}</li></ul></div>
          <div><b>下周期建议补充</b><ul><li v-for="(question, i) in stats.analysis_report.questions" :key="'q' + i">{{ question }}</li></ul></div>
        </div>
      </details>
      <div class="analysis-note">{{ stats.analysis_report.data_note }}</div>
    </section>

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
              <th>部门</th><th>一级部门</th><th>人数</th><th>人均在岗时长</th><th>较标准基线</th>
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
              <td :class="baselineCls(d)"><b>{{ d.baseline_delta?.display || '—' }}</b></td>
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

      <!-- 规则提醒：作为核查触发器，不替代经营结果判断 -->
      <div class="section-title"><i class="ic ic-alert ic-orange"></i> 异常提醒（用于核查）</div>
      <div class="suggest-list">
        <div v-for="(s, i) in stats.suggestions" :key="i" class="suggest-item" :class="s.level">
          <span class="suggest-icon">{{ s.type === 'deviation_high' ? '📈' : s.type === 'deviation_low' ? '📉' : s.type === 'late_off' ? '🌙' : s.type === 'late_on' ? '⏰' : s.type.startsWith('personal') ? '👤' : '💡' }}</span>
          <span class="suggest-text">{{ s.text }}</span>
          <span class="suggest-tag" :class="s.level">{{ s.level === 'dept' ? '部门' : '个人' }}</span>
        </div>
        <div v-if="!stats.suggestions.length" class="no-suggest">✅ 当前周期未触发规则提醒：各部门在岗时长暂未出现明显偏离</div>
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
const STANDARD_START_MINUTES = 9 * 60 + 15
const STANDARD_END_MINUTES = 18 * 60 + 30
const STANDARD_ONDUTY_MINUTES = STANDARD_END_MINUTES - STANDARD_START_MINUTES

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
const baselineCls = (d) => {
  const minutes = d.baseline_delta?.minutes
  if (minutes == null) return ''
  return minutes >= 60 ? 'baseline-over' : minutes <= -60 ? 'baseline-under' : 'diff-ok'
}

async function loadStats() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/onduty-stats', { params: { month: month.value } })
    applyStatsData(res.data)
    await nextTick()
    renderCharts()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

async function syncStats() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.post('/api/sync-onduty', null, {
      params: { month: month.value },
      timeout: 120000,
    })
    applyStatsData(res.data)
    await nextTick()
    renderCharts()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

function applyStatsData(data) {
  stats.value = data
  months.value = data.months || []
  if (data.month && !month.value) month.value = data.month
  if (data.source_error) error.value = data.source_error
  updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
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
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: '#d97706', type: 'dashed', width: 1.5 },
        label: { show: true, formatter: '标准 09:15—18:30', color: '#b45309', fontSize: 10 },
        data: [{ xAxis: STANDARD_ONDUTY_MINUTES }],
      },
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
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: '#d97706', type: 'dashed', width: 1.5 },
          label: { show: true, formatter: '上班 09:15 / 下班 18:30', color: '#b45309', fontSize: 10 },
          data: [{ xAxis: STANDARD_START_MINUTES }, { xAxis: STANDARD_END_MINUTES }],
        },
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

.schedule-baseline { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; color: #92400e; font-size: 12px; }
.schedule-baseline b { color: #78350f; font-size: 13px; }
.baseline-label { font-weight: 700; }
.schedule-baseline em { color: #a16207; font-style: normal; font-size: 11px; }

/* 家清垂类电商在岗时长经营分析报告 */
.analysis-report { background: #fff; border: 1px solid #e0e7ff; border-left: 5px solid #4f46e5; border-radius: 14px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(79,70,229,.07); }
.analysis-report.status-unavailable { border-left-color: #d97706; border-color: #fed7aa; background: #fffdf8; }
.analysis-report.status-no_data { border-left-color: #94a3b8; border-color: #e2e8f0; }
.analysis-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.analysis-kicker { color: #4f46e5; font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.status-unavailable .analysis-kicker { color: #b45309; }
.analysis-head h2 { margin: 0; color: #1a1a2e; font-size: 18px; }
.analysis-head p { margin: 6px 0 0; color: #64748b; font-size: 12px; }
.analysis-status { flex-shrink: 0; color: #3730a3; background: #eef2ff; border-radius: 20px; padding: 5px 10px; font-size: 12px; font-weight: 700; }
.status-unavailable .analysis-status { color: #9a3412; background: #ffedd5; }
.status-no_data .analysis-status { color: #475569; background: #f1f5f9; }
.analysis-headline { margin-top: 16px; padding: 12px 14px; background: #f5f7ff; color: #3730a3; border-radius: 10px; font-size: 13px; line-height: 1.7; }
.status-unavailable .analysis-headline { background: #fff7ed; color: #9a3412; }
.analysis-conclusion { margin-top: 10px; padding: 13px 14px; background: #ecfdf5; border: 1px solid #a7f3d0; border-left: 4px solid #059669; color: #065f46; border-radius: 10px; font-size: 13px; line-height: 1.8; }
.status-unavailable .analysis-conclusion { background: #fff7ed; border-color: #fed7aa; border-left-color: #d97706; color: #9a3412; }
.status-no_data .analysis-conclusion { background: #f8fafc; border-color: #e2e8f0; border-left-color: #94a3b8; color: #475569; }
.analysis-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.summary-item { color: #334155; background: #f8fafc; border-radius: 8px; padding: 9px 12px; font-size: 13px; line-height: 1.6; }
.analysis-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.analysis-metric { border: 1px solid #eef2f7; border-radius: 10px; padding: 11px 13px; }
.analysis-metric-label { color: #64748b; font-size: 12px; }
.analysis-metric-value { color: #4f46e5; font-size: 20px; font-weight: 700; margin-top: 4px; }
.analysis-metric-note { color: #94a3b8; font-size: 11px; margin-top: 3px; }
.analysis-section { margin-top: 16px; }
.analysis-section-title { color: #1e293b; font-size: 14px; font-weight: 700; margin-bottom: 9px; }
.business-views { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.business-view-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; background: #fff; }
.business-view-card h3 { color: #1e293b; font-size: 13px; margin: 0 0 5px; }
.business-scope { color: #4f46e5; font-size: 11px; line-height: 1.5; min-height: 32px; }
.business-focus { color: #334155; background: #f8fafc; border-radius: 6px; padding: 6px 8px; font-size: 11px; line-height: 1.5; margin-top: 7px; }
.business-view-card p { color: #64748b; font-size: 12px; line-height: 1.6; margin: 7px 0 0; }
.analysis-findings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.finding-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; background: #fff; }
.finding-card h3 { color: #1e293b; font-size: 13px; margin: 0 0 6px; }
.finding-card p { color: #475569; font-size: 12px; line-height: 1.65; margin: 0; }
.finding-evidence { color: #64748b; background: #f8fafc; border-radius: 6px; font-size: 11px; line-height: 1.5; margin-top: 8px; padding: 6px 8px; }
.dept-insight-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.dept-insight-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; background: #fff; }
.dept-insight-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.dept-insight-head h3 { color: #1e293b; display: inline; font-size: 14px; margin: 0 7px 0 0; }
.dept-insight-head span { color: #64748b; font-size: 11px; }
.dept-insight-status { color: #3730a3 !important; background: #eef2ff; border-radius: 20px; padding: 4px 8px; white-space: nowrap; font-weight: 600; }
.dept-insight-metrics { display: flex; flex-wrap: wrap; gap: 7px 14px; margin-top: 9px; color: #64748b; font-size: 11px; }
.dept-insight-metrics b { color: #4f46e5; font-size: 12px; }
.dept-insight-focus { border-left: 3px solid #c7d2fe; color: #475569; font-size: 11px; line-height: 1.5; margin-top: 9px; padding-left: 8px; }
.dept-insight-card p { color: #475569; font-size: 12px; line-height: 1.6; margin: 7px 0 0; }
.dept-insight-card p b { color: #1e293b; }
.analysis-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.action-item { display: flex; align-items: flex-start; gap: 8px; background: #f8fafc; border-radius: 10px; padding: 11px 12px; }
.action-priority { color: #fff; background: #4f46e5; border-radius: 5px; padding: 2px 5px; font-size: 10px; font-weight: 700; flex-shrink: 0; }
.action-item b { color: #1e293b; font-size: 12px; }
.action-item p { color: #475569; font-size: 12px; line-height: 1.6; margin: 4px 0 0; }
.analysis-details { margin-top: 14px; border-top: 1px dashed #e5e7eb; padding-top: 10px; color: #475569; font-size: 12px; }
.analysis-details summary { color: #4f46e5; cursor: pointer; font-weight: 600; }
.analysis-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 10px; }
.analysis-detail-grid ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.7; }
.analysis-note { color: #94a3b8; font-size: 11px; line-height: 1.5; margin-top: 12px; }

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
.baseline-over { color: #dc2626; font-weight: 600; }
.baseline-under { color: #d97706; font-weight: 600; }

.suggest-list { display: flex; flex-direction: column; gap: 10px; }
.suggest-item { display: flex; align-items: flex-start; gap: 10px; background: #fff; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.05); border-left: 4px solid #4f46e5; }
.suggest-item.person { border-left-color: #059669; background: #fafffd; }
.suggest-icon { font-size: 18px; }
.suggest-text { font-size: 13px; color: #1a1a2e; line-height: 1.7; flex: 1; }
.suggest-tag { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; white-space: nowrap; }
.suggest-tag.dept { background: #eef2ff; color: #3730a3; }
.suggest-tag.person { background: #ecfdf5; color: #047857; }
.no-suggest { background: #ecfdf5; border: 1px solid #a7f3d0; color: #047857; padding: 14px 16px; border-radius: 10px; font-size: 13px; }

@media (max-width: 1000px) {
  .analysis-metrics, .business-views, .analysis-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 680px) {
  .onduty { padding: 16px; }
  .schedule-baseline { align-items: flex-start; flex-direction: column; gap: 4px; }
  .analysis-report { padding: 15px; }
  .analysis-head, .analysis-detail-grid { display: block; }
  .analysis-status { display: inline-block; margin-top: 10px; }
  .analysis-summary, .analysis-metrics, .business-views, .analysis-findings, .dept-insight-list, .analysis-actions { grid-template-columns: 1fr; }
  .stat-cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
