<template>
  <div class="log-eval">
    <header class="page-header">
      <h1><i class="ic ic-chart"></i> 管理人员日志评分</h1>
      <span class="update-tag">实时更新</span>
      <div v-if="viewMode === 'period'" class="month-filter" aria-label="评估月份筛选">
        <span class="month-filter-label">评估月份</span>
        <button class="month-nav-btn" type="button" title="上一个月" aria-label="上一个月" @click="shiftMonth(-1)">‹</button>
        <label class="month-input-wrap">
          <i class="ic ic-cal"></i>
          <input v-model="monthFilter" type="month" class="month-picker" aria-label="选择评估月份" @change="changeMonth" />
        </label>
        <button class="month-nav-btn" type="button" title="下一个月" aria-label="下一个月" @click="shiftMonth(1)">›</button>
      </div>
      <div class="period-tabs">
        <button v-for="p in periods" :key="p.value"
                :class="['period-tab', { active: period === p.value }]"
                @click="switchPeriod(p.value)">{{ p.label }}</button>
      </div>
      <div class="period-tabs view-switch">
        <button :class="['period-tab', { active: viewMode === 'period' }]"
                @click="switchView('period')">📊 综合评估</button>
        <button :class="['period-tab', { active: viewMode === 'weekly' }]"
                @click="switchView('weekly')">📅 周度周报</button>
      </div>
      <span class="update-time"><i class="ic ic-clock"></i> {{ updatedAt }}</span>
      <button class="refresh-btn" @click="refresh" title="刷新"><i class="ic ic-refresh"></i></button>
      <div v-if="viewMode === 'period'" class="download-actions">
        <button class="period-download-btn excel" :disabled="downloadBusy" @click="downloadComprehensive('excel')">
          {{ periodDownloading === 'excel' ? '导出中…' : '导出 Excel' }}
        </button>
        <button class="period-download-btn ranking" :disabled="downloadBusy" @click="downloadComprehensive('ranking')">
          {{ periodDownloading === 'ranking' ? '生成中…' : '下载排名看板' }}
        </button>
        <button class="period-download-btn batch" :disabled="downloadBusy || !ranking.people?.length" @click="downloadComprehensive('batch')">
          {{ periodDownloading === 'batch' ? '打包中…' : '批量下载图片' }}
        </button>
      </div>
    </header>

    <!-- 同步入口 -->
    <div v-if="needSync" class="sync-banner">
      <i class="ic ic-alert"></i> 暂无日志数据，请先同步钉钉日志
      <button class="sync-now" @click="syncLogs" :disabled="syncing">{{ syncing ? '⏳ 同步中…' : '🔄 同步钉钉日志' }}</button>
    </div>
    <div v-else class="sync-banner dim">
      <span>评估月份：{{ monthLabel }} · 数据范围：{{ rangeText }}</span>
      <button class="sync-now" @click="syncLogs" :disabled="syncing">{{ syncing ? '⏳ 同步中…' : '🔄 重新同步' }}</button>
    </div>

    <div v-if="loading" class="loading-tip"><span class="spinner"></span> 数据加载中，请稍候…</div>

    <template v-if="!loading && viewMode === 'period'">
      <!-- 统计卡 -->
      <div class="stat-cards">
        <div class="stat-card"><div class="stat-val">{{ ranking.total_people ?? 0 }}</div><div class="stat-label">评估人数</div></div>
        <div class="stat-card"><div class="stat-val">{{ ranking.total_logs ?? 0 }}</div><div class="stat-label">日志总数</div></div>
        <div class="stat-card"><div class="stat-val">{{ avgAll }}</div><div class="stat-label">全员综合评分</div></div>
        <div class="stat-card"><div class="stat-val">{{ gradeDist }}</div><div class="stat-label">评级 A/B 人数</div></div>
      </div>

      <!-- 排名表 -->
      <div class="section-title"><i class="ic ic-rank ic-indigo"></i> 管理人员日志综合评分排名（综合评分降序）</div>
      <div class="rank-table-wrap">
        <table class="rank-table">
          <thead>
            <tr>
              <th>排名</th><th>姓名</th><th>岗位</th><th>篇数</th><th>综合评分</th><th>日志均分</th><th>评级</th>
              <th>岗位书写维度</th><th>优点</th><th>需改进方向</th><th>综合点评</th><th>报告图片</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in ranking.people" :key="p.name"
                :class="['rank-row', { selected: selected === p.name }]"
                @click="selectPerson(p.name)">
              <td class="rank-cell" :class="'r' + (p.rank && p.rank <= 3 ? p.rank : 'x')">{{ p.rank || '—' }}</td>
              <td class="name-cell">{{ p.name }}</td>
              <td>{{ p.title || '—' }}</td>
              <td>{{ p.log_count }}</td>
              <td class="score-cell"><b>{{ p.comp_score || '—' }}</b></td>
              <td class="sub-score-cell">{{ p.avg_score || '—' }}</td>
              <td><span class="grade-badge" :class="'g' + p.grade">{{ p.grade_cn || '—' }}</span></td>
              <td><span v-if="writingRefScore(p) !== null" class="assess-chip" :class="assessCls(writingRefScore(p))" :title="p.writing_reference?.comment || ''">{{ writingRefScore(p) }}</span><span v-else class="assess-na">—</span></td>
              <td class="tip-cell good">{{ p.strengths }}</td>
              <td class="tip-cell warn">{{ p.improvements }}</td>
              <td class="tip-cell cmt">{{ p.comment }}</td>
              <td class="image-report-cell">
                <button class="image-report-btn" :disabled="downloadBusy" @click.stop="downloadComprehensive('person', p.name)">
                  {{ periodDownloading === `person:${p.name}` ? '生成中…' : '下载图片' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 个人综合评估分析报告（抽屉式） -->
      <div v-if="drawerOpen" class="drawer-mask" @click="closeDrawer"></div>
      <aside v-if="drawerOpen" class="drawer" :class="{ open: drawerOpen }">
        <div class="drawer-head">
          <span v-if="evalData" class="drawer-title">
            📋 {{ evalData.name }}（{{ evalData.title }}）— 综合评估分析报告
            <span class="detail-sub">周期内 {{ evalData.total }} 篇 · 日志均分 {{ evalData.avg_score }}</span>
            <span class="grade-badge lg" :class="'g' + evalData.grade">{{ evalData.grade_cn }}</span>
          </span>
          <button class="drawer-close" @click="closeDrawer" title="关闭">✕</button>
        </div>
        <div class="drawer-body">
          <div v-if="evalData && evalData.total > 0">

        <div class="focus-bar">
          <div class="focus-item"><span class="focus-label">综合评分</span><span class="focus-val">{{ evalData.comp_score }}</span></div>
          <div class="focus-item"><span class="focus-label">岗位职责契合</span><span class="focus-val">{{ evalData.role_fit }}/20</span></div>
          <div class="focus-item"><span class="focus-label">业绩导向</span><span class="focus-val">{{ evalData.perf_focus }}/20</span></div>
          <div class="focus-item"><span class="focus-label">团队管理</span><span class="focus-val">{{ evalData.mgmt_focus }}/20</span></div>
          <div class="focus-item"><span class="focus-label">岗位书写维度</span><span class="focus-val">{{ evalData.writing_reference?.score ?? 0 }}/20</span></div>
        </div>

        <!-- 五维雷达（全宽） -->
        <div class="panel radar-panel">
          <div class="panel-title">评分维度（五维雷达）</div>
          <div ref="radarEl" class="chart-box"></div>
        </div>

        <!-- 综合评估与周度评估共用四项评估维度 -->
        <div v-if="evalData.assess" class="assess-grid">
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">🏭 电商行业属性</span><span class="assess-score" :class="assessCls(evalData.assess.industry?.score)">{{ evalData.assess.industry?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ evalData.assess.industry?.comment || '周期内无日志，无法评估行业属性' }}</div>
          </div>
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">👤 岗位要求契合</span><span class="assess-score" :class="assessCls(evalData.assess.role?.score)">{{ evalData.assess.role?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ evalData.assess.role?.comment || '周期内无日志，无法评估岗位要求' }}</div>
          </div>
          <div class="assess-item writing-ref-assess">
            <div class="assess-head"><span class="assess-name">🧭 岗位书写维度</span><span class="assess-score" :class="assessCls(evalData.assess.writing_reference?.score)">{{ evalData.assess.writing_reference?.score ?? 0 }}/20</span></div>
            <div class="assess-template">{{ evalData.assess.writing_reference?.template || '管理岗参考模板' }}</div>
            <div class="assess-cmt">{{ evalData.assess.writing_reference?.comment || '周期内无日志，无法评估岗位书写维度' }}</div>
          </div>
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">✍️ 日报书写展现</span><span class="assess-score" :class="assessCls(evalData.assess.writing?.score)">{{ evalData.assess.writing?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ evalData.assess.writing?.comment || '周期内无日志，无法评估书写展现' }}</div>
          </div>
        </div>

        <!-- 管理岗日志书写参考维度：按岗位模板逐项覆盖并保留日志证据 -->
        <div v-if="evalData.writing_reference" class="writing-reference-panel">
          <div class="writing-reference-head">
            <div>
              <div class="panel-title">管理岗日志书写参考维度（{{ evalData.writing_reference.template }}）</div>
              <div class="writing-reference-core">核心要求：{{ evalData.writing_reference.core }}</div>
            </div>
            <span class="writing-reference-score" :class="assessCls(evalData.writing_reference.score)">{{ evalData.writing_reference.score }}/20</span>
          </div>
          <div class="writing-reference-grid">
            <div v-for="d in evalData.writing_reference.detail" :key="d.name" class="writing-reference-item" :class="d.covered ? 'covered' : 'missing'">
              <div class="writing-reference-name"><span class="role-dot" :class="d.covered ? 'ok' : 'no'">{{ d.covered ? '✓' : '✗' }}</span>{{ d.name }}</div>
              <div class="role-evidence" :class="d.covered ? '' : 'empty'">{{ d.covered ? d.evidence : '日志中未覆盖该书写板块' }}</div>
            </div>
          </div>
          <div class="writing-reference-comment">{{ evalData.writing_reference.comment }}</div>
        </div>

        <!-- 优点 / 需改进（融合岗位职责深度评估） -->
        <div class="report-grid">
          <div class="report-panel">
            <div class="report-title good-title">👍 优点</div>
            <div v-if="coveredRoles.length" class="role-mini">
              <div class="role-mini-title">✅ 岗位职责覆盖（{{ evalData.title }}）</div>
              <div v-for="d in coveredRoles" :key="d.name" class="role-mini-item">
                <span class="role-dot ok">✓</span><b class="role-mini-name">{{ d.name }}</b>
                <div class="role-evidence">{{ d.evidence }}</div>
              </div>
            </div>
            <ul class="report-list">
              <li v-for="(s, i) in strengthsList" :key="i" class="good-item">{{ s }}</li>
            </ul>
            <div v-if="evalData.deep_strengths?.length" class="deep-block">
              <div class="deep-title">🌟 深度亮点（结合电商行业与岗位）</div>
              <div v-for="(s, i) in evalData.deep_strengths" :key="'ds' + i" class="deep-item good">{{ s }}</div>
            </div>
          </div>
          <div class="report-panel">
            <div class="report-title warn-title">💡 需改进方向</div>
            <div v-if="uncovRoles.length" class="role-mini">
              <div class="role-mini-title warn">⬜ 岗位职责未覆盖</div>
              <div v-for="d in uncovRoles" :key="d.name" class="role-mini-item">
                <span class="role-dot no">✗</span><b class="role-mini-name">{{ d.name }}</b>
              </div>
            </div>
            <ul class="report-list">
              <li v-for="(s, i) in improvementsList" :key="i" class="warn-item">{{ s }}</li>
            </ul>
            <div v-if="evalData.deep_improvements?.length" class="deep-block">
              <div class="deep-title">🔍 深度分析建议（结合电商行业与岗位）</div>
              <div v-for="(s, i) in evalData.deep_improvements" :key="'di' + i" class="deep-item warn">{{ s }}</div>
            </div>
          </div>
        </div>

        <!-- 综合评估意见 -->
        <div class="comment-box">
          <div class="comment-label">📋 综合评估意见</div>
          <div class="comment-text">{{ evalData.comment }}</div>
        </div>
          </div>
          <div v-else-if="evalData" class="no-log-tip">
            {{ evalData.name }}（{{ evalData.title }}）在本周期内暂无日志记录
          </div>
        </div>
      </aside>
    </template>

    <!-- 周度周报视图 -->
    <WeeklyLogReport v-else-if="viewMode === 'weekly'" :key="weeklyRefreshKey" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'
import WeeklyLogReport from './WeeklyLogReport.vue'

const INDIGO = '#4f46e5'

const viewMode = ref('period')
const weeklyRefreshKey = ref(0)
const drawerOpen = ref(false)

const periods = [
  { value: 'month', label: '月度' },
  { value: 'quarter', label: '季度' },
  { value: 'half', label: '半年度' },
  { value: 'year', label: '年度' },
]
const period = ref('month')
function currentMonthValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}
const monthFilter = ref(currentMonthValue())
const ranking = ref({ people: [] })
const loading = ref(false)
const syncing = ref(false)
const updatedAt = ref('')
const selected = ref('')
const evalData = ref(null)
const radarEl = ref(null)
const periodDownloading = ref('')
const downloadBusy = computed(() => Boolean(periodDownloading.value))
let radarChart = null

const needSync = computed(() => (ranking.value.total_people ?? 0) === 0)
const rangeText = computed(() => (ranking.value.start ? `${ranking.value.start} ~ ${ranking.value.end}` : ''))
const monthLabel = computed(() => {
  const [year, month] = monthFilter.value.split('-')
  return year && month ? `${year}年${Number(month)}月` : monthFilter.value
})
const avgAll = computed(() => {
  const p = (ranking.value.people || []).filter(x => (x.log_count || 0) > 0)
  if (!p.length) return 0
  return (p.reduce((s, x) => s + (x.comp_score || 0), 0) / p.length).toFixed(1)
})
const gradeDist = computed(() => {
  const p = ranking.value.people || []
  const ab = p.filter(x => x.grade === 'A' || x.grade === 'B').length
  return p.length ? `${ab}/${p.length}` : 0
})
// 岗位职责深度评估 → 融合进优点/需改进（covered=优点带证据，未覆盖=需改进）
const coveredRoles = computed(() => (evalData.value?.role_detail || []).filter(d => d.covered))
const uncovRoles = computed(() => (evalData.value?.role_detail || []).filter(d => !d.covered))
const strengthsList = computed(() => (evalData.value?.strengths_list || []).filter(s => !s.startsWith('岗位职责覆盖')))
const improvementsList = computed(() => (evalData.value?.improvements_list || []).filter(s => !s.startsWith('岗位职责覆盖不足')))
const writingRefScore = (p) => (p.log_count && p.writing_reference) ? p.writing_reference.score : null
function assessCls(s) { return s == null ? '' : s >= 15 ? 'hi' : s >= 10 ? 'mid' : 'lo' }

async function loadRanking() {
  loading.value = true
  try {
    const res = await axios.get('/api/logs-ranking', { params: { period: period.value, month: monthFilter.value } })
    ranking.value = res.data
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (res.data.people?.length && !selected.value) {
      loadEvaluation(res.data.people[0].name)  // 静默预载，不打开抽屉
    } else if (selected.value) {
      await loadEvaluation(selected.value)
    }
  } catch (e) {
    console.error('加载日志排名失败', e)
  } finally {
    loading.value = false
  }
}

async function loadEvaluation(name) {
  selected.value = name
  try {
    const res = await axios.get('/api/logs-evaluation', { params: { name, period: period.value, month: monthFilter.value } })
    evalData.value = res.data
    await nextTick()
    renderCharts()
  } catch (e) {
    console.error('加载个人评估失败', e)
  }
}

function selectPerson(name) {
  drawerOpen.value = true
  loadEvaluation(name)
}

function closeDrawer() {
  drawerOpen.value = false
  radarChart?.dispose(); radarChart = null
}

function switchPeriod(p) {
  if (period.value === p) return
  period.value = p
  loadRanking()
}

function changeMonth() {
  if (!/^\d{4}-\d{2}$/.test(monthFilter.value)) return
  loadRanking()
}

function shiftMonth(delta) {
  const [year, month] = monthFilter.value.split('-').map(Number)
  if (!year || !month) return
  const shifted = new Date(year, month - 1 + delta, 1)
  monthFilter.value = `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, '0')}`
  loadRanking()
}

function switchView(mode) {
  if (viewMode.value === mode) return
  if (mode === 'weekly') closeDrawer()
  viewMode.value = mode
}

function refresh() {
  if (viewMode.value === 'weekly') {
    weeklyRefreshKey.value++  // 重挂载周报组件触发重新加载
  } else {
    loadRanking()
  }
}

function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encoded?.[1]) {
    try { return decodeURIComponent(encoded[1]) } catch (_) { return encoded[1] }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)
  return plain?.[1] || fallback
}

async function downloadComprehensive(kind, name = '') {
  const key = kind === 'person' ? `person:${name}` : kind
  if (periodDownloading.value) return
  const config = {
    excel: {
      url: '/api/logs-comprehensive-export',
      filename: `${monthFilter.value}_${period.value}_管理人员综合评估.xlsx`,
    },
    ranking: {
      url: '/api/logs-comprehensive-ranking-image',
      filename: `${monthFilter.value}_${period.value}_管理人员综合评估排名看板.png`,
    },
    batch: {
      url: '/api/logs-comprehensive-person-images-zip',
      filename: `${monthFilter.value}_${period.value}_管理人员综合评估报告.zip`,
    },
    person: {
      url: '/api/logs-comprehensive-person-image',
      filename: `${name}_${monthFilter.value}_${period.value}_综合评估报告.png`,
    },
  }[kind]
  if (!config) return

  periodDownloading.value = key
  try {
    const res = await axios.get(config.url, {
      params: kind === 'person'
        ? { period: period.value, month: monthFilter.value, name }
        : { period: period.value, month: monthFilter.value },
      responseType: 'blob',
      timeout: 300000,
    })
    const blob = res.data
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filenameFromDisposition(res.headers['content-disposition'], config.filename)
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    let detail = e.response?.data?.detail || e.message || '下载失败'
    if (e.response?.data instanceof Blob) {
      try { detail = JSON.parse(await e.response.data.text()).detail || detail } catch (_) { /* 保留原始错误 */ }
    }
    alert(`❌ ${detail}`)
  } finally {
    periodDownloading.value = ''
  }
}

async function syncLogs() {
  if (syncing.value) return
  syncing.value = true
  try {
    const res = await axios.post('/api/sync-logs', {}, { timeout: 300000 })
    const d = res.data
    alert(d.inserted != null ? `✅ 日志同步完成：新增 ${d.inserted} 条，更新 ${d.updated} 条` : `⚠️ ${d.error || '同步失败'}`)
    await loadRanking()
  } catch (e) {
    const detail = e.response?.data?.detail || e.message
    alert(`❌ 日志同步失败: ${detail}`)
  } finally {
    syncing.value = false
  }
}

function renderCharts() {
  if (!evalData.value || !radarEl.value) return
  const rd = evalData.value.radar || []
  radarChart = radarChart || echarts.init(radarEl.value)
  radarChart.setOption({
    tooltip: {},
    radar: {
      indicator: rd.map(d => ({ name: d.dimension, max: d.max })),
      radius: '65%',
      splitArea: { areaStyle: { color: ['#f5f7ff', '#eef2ff'] } },
      axisName: { color: '#1a1a2e', fontSize: 12 },
    },
    series: [{
      type: 'radar',
      data: [{ value: rd.map(d => d.score), name: evalData.value.name }],
      areaStyle: { color: 'rgba(79, 70, 229, 0.25)' },
      lineStyle: { color: INDIGO, width: 2 },
      itemStyle: { color: INDIGO },
    }],
  })
}

function onResize() {
  radarChart?.resize()
}

onMounted(() => {
  loadRanking()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  radarChart?.dispose()
})
</script>

<style scoped>
.log-eval { padding: 20px 24px; }
.page-header { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.page-header h1 { font-size: 20px; color: #1a1a2e; display: flex; align-items: center; gap: 8px; }
.update-tag { font-size: 12px; color: #059669; background: #ecfdf5; padding: 3px 10px; border-radius: 20px; }
.month-filter { display: inline-flex; align-items: center; gap: 5px; padding: 3px 6px 3px 10px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
.month-filter-label { color: #475569; font-size: 12px; white-space: nowrap; }
.month-input-wrap { display: inline-flex; align-items: center; gap: 4px; color: #4f46e5; }
.month-picker { border: none; background: transparent; color: #1f2937; font: inherit; font-size: 12px; min-width: 112px; padding: 3px 2px; outline: none; cursor: pointer; }
.month-nav-btn { width: 23px; height: 23px; border: none; border-radius: 6px; background: #eef2ff; color: #3730a3; cursor: pointer; font-size: 18px; line-height: 1; padding: 0; }
.month-nav-btn:hover { background: #e0e7ff; }
.update-time { font-size: 12px; color: #8b8fa8; }
.refresh-btn { border: none; background: #fff; border-radius: 8px; padding: 6px 10px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.download-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.period-download-btn { border: 1px solid transparent; border-radius: 8px; padding: 7px 11px; cursor: pointer; font-size: 12px; font-weight: 600; transition: all .2s; white-space: nowrap; }
.period-download-btn.excel { color: #047857; background: #ecfdf5; border-color: #a7f3d0; }
.period-download-btn.ranking { color: #3730a3; background: #eef2ff; border-color: #c7d2fe; }
.period-download-btn.batch { color: #9a3412; background: #fff7ed; border-color: #fed7aa; }
.period-download-btn:hover:not(:disabled) { filter: brightness(.97); transform: translateY(-1px); }
.period-download-btn:disabled, .image-report-btn:disabled { opacity: .55; cursor: wait; transform: none; }
.period-tabs { display: flex; gap: 4px; background: #fff; border-radius: 10px; padding: 3px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.period-tab { border: none; background: transparent; padding: 6px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; color: #555; }
.period-tab.active { background: #4f46e5; color: #fff; font-weight: 600; }

.sync-banner { display: flex; align-items: center; justify-content: space-between; background: #eef2ff; border: 1px solid #c7d2fe; color: #3730a3; padding: 10px 16px; border-radius: 10px; margin-bottom: 14px; font-size: 13px; }
.sync-banner.dim { background: #f9fafb; border-color: #e5e7eb; color: #6b7280; }
.sync-now { background: #4f46e5; color: #fff; border: none; border-radius: 8px; padding: 7px 16px; cursor: pointer; font-size: 13px; }
.sync-now:disabled { opacity: .5; cursor: wait; }

.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.stat-val { font-size: 28px; font-weight: 700; color: #4f46e5; }
.stat-label { font-size: 13px; color: #8b8fa8; margin-top: 4px; }

.section-title { font-size: 16px; font-weight: 700; color: #1a1a2e; margin: 20px 0 12px; display: flex; align-items: center; gap: 8px; }
.detail-sub { font-size: 12px; color: #8b8fa8; font-weight: 400; }

.rank-table-wrap { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.05); overflow-x: auto; }
.rank-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank-table th { background: #4f46e5; color: #fff; padding: 10px 12px; text-align: left; white-space: nowrap; font-weight: 600; }
.rank-table td { padding: 9px 12px; border-bottom: 1px solid #f3f4f6; white-space: nowrap; }
.rank-row { cursor: pointer; }
.rank-row:hover { background: #f5f7ff; }
.rank-row.selected { background: #eef2ff; }
.rank-cell { font-weight: 700; color: #8b8fa8; }
.rank-cell.r1 { color: #f59e0b; font-size: 16px; }
.rank-cell.r2 { color: #94a3b8; font-size: 15px; }
.rank-cell.r3 { color: #d97706; }
.name-cell { font-weight: 600; color: #1a1a2e; }
.score-cell b { font-size: 15px; color: #4f46e5; }
.tip-cell { white-space: normal; line-height: 1.5; font-size: 12px; min-width: 200px; }
.tip-cell.good { color: #059669; }
.tip-cell.warn { color: #b45309; }
.tip-cell.cmt { color: #1a1a2e; min-width: 260px; }
.image-report-cell { text-align: center; }
.image-report-btn { border: 1px solid #c7d2fe; background: #eef2ff; color: #3730a3; border-radius: 7px; padding: 5px 9px; cursor: pointer; font-size: 12px; white-space: nowrap; }
.image-report-btn:hover:not(:disabled) { background: #e0e7ff; }

.grade-badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; color: #fff; }
.grade-badge.gA { background: #059669; }
.grade-badge.gB { background: #4f46e5; }
.grade-badge.gC { background: #f59e0b; }
.grade-badge.gD { background: #dc2626; }
.grade-badge.lg { font-size: 14px; padding: 4px 14px; margin-left: 10px; }

.comment-box { background: #eef2ff; border-left: 4px solid #4f46e5; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.comment-label { font-size: 13px; font-weight: 700; color: #3730a3; margin-bottom: 6px; }
.comment-text { font-size: 14px; color: #1a1a2e; line-height: 1.7; }

.focus-bar { display: flex; gap: 10px; margin-bottom: 14px; }
.focus-item { flex: 1; background: #fff; border-radius: 10px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
.focus-label { font-size: 13px; color: #6b7280; }
.focus-val { font-size: 18px; font-weight: 700; color: #4f46e5; }

.assess-chip { display: inline-block; min-width: 28px; text-align: center; padding: 2px 6px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.assess-chip.hi { background: #ecfdf5; color: #047857; }
.assess-chip.mid { background: #eef2ff; color: #3730a3; }
.assess-chip.lo { background: #fef2f2; color: #b91c1c; }
.assess-na { color: #d1d5db; }
.assess-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.assess-item { background: #fff; border-radius: 10px; padding: 12px 14px; border: 1px solid #f3f4f6; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.assess-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; gap: 8px; }
.assess-name { font-size: 13px; font-weight: 700; color: #1a1a2e; white-space: nowrap; }
.assess-score { font-size: 16px; font-weight: 700; }
.assess-score.hi { color: #047857; }
.assess-score.mid { color: #3730a3; }
.assess-score.lo { color: #b91c1c; }
.assess-cmt { font-size: 12px; color: #4b5563; line-height: 1.55; }
.assess-template { font-size: 11px; color: #7c3aed; margin: -2px 0 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 管理岗日志书写参考维度覆盖 */
.writing-reference-panel { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.05); border-left: 4px solid #7c3aed; }
.writing-reference-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.writing-reference-head .panel-title { margin-bottom: 4px; }
.writing-reference-core { font-size: 12px; color: #6b7280; }
.writing-reference-score { font-size: 20px; font-weight: 700; white-space: nowrap; }
.writing-reference-score.hi { color: #047857; }
.writing-reference-score.mid { color: #3730a3; }
.writing-reference-score.lo { color: #b91c1c; }
.writing-reference-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.writing-reference-item { border: 1px solid #f3f4f6; border-radius: 8px; padding: 8px 10px; background: #fafafa; }
.writing-reference-item.covered { border-color: #d1fae5; background: #f0fdf4; }
.writing-reference-item.missing { border-color: #fed7aa; background: #fffaf5; }
.writing-reference-name { font-size: 13px; font-weight: 600; color: #1a1a2e; display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.writing-reference-comment { font-size: 12px; color: #4b5563; line-height: 1.6; margin-top: 10px; }

/* 岗位职责覆盖（融合进优点/需改进） */
.role-dot { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; color: #fff; flex-shrink: 0; }
.role-dot.ok { background: #059669; }
.role-dot.no { background: #d1d5db; }
.role-evidence { font-size: 12px; color: #4b5563; line-height: 1.5; margin-top: 3px; }
.role-mini { margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px dashed #f3f4f6; }
.role-mini-title { font-size: 12px; font-weight: 700; color: #059669; margin-bottom: 8px; }
.role-mini-title.warn { color: #b45309; }
.role-mini-item { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; font-size: 13px; }
.role-mini-name { color: #1a1a2e; white-space: nowrap; }

/* 优点/需改进 报告面板 */
.report-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.report-panel { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.report-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; }
.good-title { color: #059669; }
.warn-title { color: #b45309; }
.report-list { list-style: none; padding: 0; margin: 0; }
.report-list li { font-size: 13px; line-height: 1.6; padding: 6px 0; border-bottom: 1px dashed #f3f4f6; }
.report-list li:last-child { border-bottom: none; }
.good-item { color: #065f46; }
.warn-item { color: #92400e; }

/* 深度分析建议（结合电商行业与岗位） */
.deep-block { margin-top: 10px; }
.deep-title { font-size: 12px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #f3f4f6; }
.deep-item { font-size: 13px; line-height: 1.7; padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; }
.deep-item.good { background: #ecfdf5; border-left: 3px solid #059669; color: #065f46; }
.deep-item.warn { background: #fff7ed; border-left: 3px solid #ea580c; color: #7c2d12; }

.panel { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.radar-panel { margin-bottom: 14px; }
.panel-title { font-size: 14px; font-weight: 600; color: #1a1a2e; margin-bottom: 10px; }
.chart-box { height: 320px; }

.loading-tip { text-align: center; padding: 60px 0; color: #8b8fa8; font-size: 14px; }
.no-log-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 16px; border-radius: 10px; text-align: center; font-size: 14px; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #c7d2fe; border-top-color: #4f46e5; border-radius: 50%; animation: spin .8s linear infinite; vertical-align: -3px; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ===== 抽屉式个人报告 ===== */
.drawer-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, .38); z-index: 300; }
.drawer { position: fixed; top: 0; right: 0; height: 100vh; width: 720px; max-width: 94vw; background: #f0f2f5; z-index: 301; box-shadow: -6px 0 28px rgba(0,0,0,.16); transform: translateX(100%); transition: transform .28s ease; display: flex; flex-direction: column; }
.drawer.open { transform: translateX(0); }
.drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; background: #fff; border-bottom: 1px solid #e8e8e8; position: sticky; top: 0; z-index: 2; }
.drawer-title { font-size: 15px; font-weight: 700; color: #1a1a2e; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.drawer-close { border: none; background: #f3f4f6; color: #4b5563; width: 32px; height: 32px; border-radius: 50%; font-size: 14px; cursor: pointer; flex-shrink: 0; transition: all .2s; }
.drawer-close:hover { background: #fee2e2; color: #dc2626; }
.drawer-body { padding: 16px 20px 32px; overflow-y: auto; flex: 1; }
@media (max-width: 900px) {
  .month-filter { order: 3; }
  .period-tabs { order: 4; }
  .view-switch { order: 5; }
  .update-time { order: 6; }
  .refresh-btn { order: 7; }
  .download-actions { order: 8; width: 100%; }
}
</style>
