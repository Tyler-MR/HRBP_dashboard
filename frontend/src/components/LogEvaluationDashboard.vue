<template>
  <div class="log-eval">
    <header class="page-header">
      <h1><i class="ic ic-chart"></i> 管理人员日志评分</h1>
      <span class="update-tag">实时更新</span>
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
    </header>

    <!-- 同步入口 -->
    <div v-if="needSync" class="sync-banner">
      <i class="ic ic-alert"></i> 暂无日志数据，请先同步钉钉日志
      <button class="sync-now" @click="syncLogs" :disabled="syncing">{{ syncing ? '⏳ 同步中…' : '🔄 同步钉钉日志' }}</button>
    </div>
    <div v-else class="sync-banner dim">
      <span>数据范围：{{ rangeText }}</span>
      <button class="sync-now" @click="syncLogs" :disabled="syncing">{{ syncing ? '⏳ 同步中…' : '🔄 重新同步' }}</button>
    </div>

    <div v-if="loading" class="loading-tip"><span class="spinner"></span> 数据加载中，请稍候…</div>

    <template v-if="!loading && viewMode === 'period'">
      <!-- 统计卡 -->
      <div class="stat-cards">
        <div class="stat-card"><div class="stat-val">{{ ranking.total_people ?? 0 }}</div><div class="stat-label">评估人数</div></div>
        <div class="stat-card"><div class="stat-val">{{ ranking.total_logs ?? 0 }}</div><div class="stat-label">日志总数</div></div>
        <div class="stat-card"><div class="stat-val">{{ avgAll }}</div><div class="stat-label">全员平均分</div></div>
        <div class="stat-card"><div class="stat-val">{{ gradeDist }}</div><div class="stat-label">评级 A/B 人数</div></div>
      </div>

      <!-- 排名表 -->
      <div class="section-title"><i class="ic ic-rank ic-indigo"></i> 管理人员日志综合排名（综合评估，平均分降序）</div>
      <div class="rank-table-wrap">
        <table class="rank-table">
          <thead>
            <tr>
              <th>排名</th><th>姓名</th><th>岗位</th><th>篇数</th><th>平均分</th><th>评级</th>
              <th>优点</th><th>需改进方向</th><th>综合点评</th>
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
              <td class="score-cell"><b>{{ p.avg_score || '—' }}</b></td>
              <td><span class="grade-badge" :class="'g' + p.grade">{{ p.grade_cn || '—' }}</span></td>
              <td class="tip-cell good">{{ p.strengths }}</td>
              <td class="tip-cell warn">{{ p.improvements }}</td>
              <td class="tip-cell cmt">{{ p.comment }}</td>
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
        </div>

        <!-- 五维雷达（全宽） -->
        <div class="panel radar-panel">
          <div class="panel-title">评分维度（五维雷达）</div>
          <div ref="radarEl" class="chart-box"></div>
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
  { value: 'month', label: '本月' },
  { value: 'quarter', label: '本季' },
  { value: 'half', label: '半年' },
  { value: 'year', label: '今年' },
]
const period = ref('month')
const ranking = ref({ people: [] })
const loading = ref(false)
const syncing = ref(false)
const updatedAt = ref('')
const selected = ref('')
const evalData = ref(null)
const radarEl = ref(null)
let radarChart = null

const needSync = computed(() => (ranking.value.total_people ?? 0) === 0)
const rangeText = computed(() => (ranking.value.start ? `${ranking.value.start} ~ ${ranking.value.end}` : ''))
const avgAll = computed(() => {
  const p = ranking.value.people || []
  if (!p.length) return 0
  return (p.reduce((s, x) => s + (x.avg_score || 0), 0) / p.length).toFixed(1)
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

async function loadRanking() {
  loading.value = true
  try {
    const res = await axios.get('/api/logs-ranking', { params: { period: period.value } })
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
    const res = await axios.get('/api/logs-evaluation', { params: { name, period: period.value } })
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
.update-time { font-size: 12px; color: #8b8fa8; }
.refresh-btn { border: none; background: #fff; border-radius: 8px; padding: 6px 10px; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
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
</style>
