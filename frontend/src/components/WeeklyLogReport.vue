<template>
  <div class="weekly-report">
    <!-- 工具栏 -->
    <div class="weekly-toolbar">
      <div class="week-picker">
        <span class="picker-label">📅 周报周期</span>
        <select v-model="week" @change="loadWeekly" class="week-select">
          <option v-for="w in weeks" :key="w" :value="w">{{ weekLabel(w) }}</option>
        </select>
        <span v-if="weekly.start" class="range-tip">{{ weekly.start }} ~ {{ weekly.end }}</span>
      </div>
      <div class="toolbar-actions">
        <button class="export-btn" @click="exportWeekly" :disabled="!weekly.people?.length">
          📥 导出 Excel（通晒）
        </button>
        <button class="ranking-image-btn" @click="downloadRankingBoard" :disabled="!weekly.people?.length || rankingDownloading">
          {{ rankingDownloading ? '⏳ 正在生成…' : '🖼️ 下载排名看板（PNG）' }}
        </button>
        <button class="batch-image-btn" @click="downloadAllReports" :disabled="!weekly.people?.length || batchDownloading">
          {{ batchDownloading ? '⏳ 正在打包…' : '🗂️ 批量下载图片（ZIP）' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-tip"><span class="spinner"></span> 周报加载中，请稍候…</div>

    <template v-else>
      <!-- 统计卡 -->
      <div class="stat-cards">
        <div class="stat-card"><div class="stat-val">{{ submitCount }}</div><div class="stat-label">本周提交人数</div></div>
        <div class="stat-card"><div class="stat-val">{{ weekly.total_logs ?? 0 }}</div><div class="stat-label">本周日志总数</div></div>
        <div class="stat-card"><div class="stat-val">{{ weekAvg }}</div><div class="stat-label">全员周均分</div></div>
        <div class="stat-card"><div class="stat-val">{{ gradeDist }}</div><div class="stat-label">评级 A/B 人数</div></div>
      </div>

      <!-- 通晒汇总表 -->
      <div class="section-title"><i class="ic ic-rank ic-indigo"></i> 📣 周度通晒汇总（{{ weekLabel(week) }} · 周均分降序）
        <span class="detail-sub">点击行查看个人周报</span>
      </div>
      <div class="rank-table-wrap">
        <table class="rank-table">
          <thead>
            <tr>
              <th>排名</th><th>姓名</th><th>岗位</th><th>职级</th><th>部门</th><th>篇数</th>
            <th>周均分</th><th>评级</th><th>行业属性</th><th>岗位要求</th><th>岗位书写维度</th><th>书写展现</th><th>核心优点</th><th>需改进</th><th>整改建议</th><th>周报图片</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in weekly.people" :key="p.name"
                :class="['rank-row', { selected: selected === p.name }]"
                @click="selectPerson(p.name)">
              <td class="rank-cell" :class="'r' + (p.rank && p.rank <= 3 ? p.rank : 'x')">{{ p.rank || '—' }}</td>
              <td class="name-cell">{{ p.name }}</td>
              <td>{{ p.title || '—' }}</td>
              <td><span class="level-tag">{{ p.level || '—' }}</span></td>
              <td>{{ p.dept || '—' }}</td>
              <td>{{ p.log_count }}</td>
              <td class="score-cell"><b>{{ p.avg_score || '—' }}</b></td>
              <td><span class="grade-badge" :class="'g' + p.grade">{{ p.grade_cn || '—' }}</span></td>
              <td><span v-if="aScore(p, 'industry') !== null" class="assess-chip" :class="assessCls(aScore(p, 'industry'))" :title="aCmt(p, 'industry')">{{ aScore(p, 'industry') }}</span><span v-else class="assess-na">—</span></td>
              <td><span v-if="aScore(p, 'role') !== null" class="assess-chip" :class="assessCls(aScore(p, 'role'))" :title="aCmt(p, 'role')">{{ aScore(p, 'role') }}</span><span v-else class="assess-na">—</span></td>
              <td><span v-if="aScore(p, 'writing_reference') !== null" class="assess-chip" :class="assessCls(aScore(p, 'writing_reference'))" :title="aCmt(p, 'writing_reference')">{{ aScore(p, 'writing_reference') }}</span><span v-else class="assess-na">—</span></td>
              <td><span v-if="aScore(p, 'writing') !== null" class="assess-chip" :class="assessCls(aScore(p, 'writing'))" :title="aCmt(p, 'writing')">{{ aScore(p, 'writing') }}</span><span v-else class="assess-na">—</span></td>
              <td class="tip-cell good">{{ p.strengths }}</td>
              <td class="tip-cell warn">{{ p.improvements }}</td>
              <td class="tip-cell rect">{{ (p.rectify || []).join('；') }}</td>
              <td class="image-report-cell"><button class="image-report-btn" @click.stop="downloadPersonReport(p.name)">📷 下载</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 个人周报（抽屉式） -->
      <div v-if="drawerOpen" class="drawer-mask" @click="closeDrawer"></div>
      <aside v-if="drawerOpen" class="drawer" :class="{ open: drawerOpen }">
        <div class="drawer-head">
          <span v-if="person" class="drawer-title">
            📋 {{ person.name }}（{{ person.title }}）— 周度日志评分报告
            <span class="level-tag lg">{{ person.level }}</span>
            <span class="grade-badge lg" :class="'g' + person.grade">{{ person.grade_cn }}</span>
            <span class="detail-sub">本周 {{ person.total }} 篇 · 周均分 {{ person.avg_score }}
              <span v-if="person.prev_week" class="week-delta" :class="deltaCls">
                {{ person.prev_week.delta > 0 ? '▲' : person.prev_week.delta < 0 ? '▼' : '—' }} {{ Math.abs(person.prev_week.delta) }} vs 上周({{ person.prev_week.avg_score }}分/{{ person.prev_week.grade_cn }})
              </span>
              <span v-else class="week-delta">上周无日志可环比</span>
            </span>
          </span>
          <div class="drawer-actions">
            <button v-if="person" class="image-report-btn" @click="downloadPersonReport(person.name)">📷 下载图片报告</button>
            <button class="drawer-close" @click="closeDrawer" title="关闭">✕</button>
          </div>
        </div>
        <div class="drawer-body">
          <div v-if="person && person.total > 0">

        <!-- 整改建议（醒目） -->
        <div class="rectify-box">
          <div class="rectify-label">🔧 本周整改建议（通晒/跟进）</div>
          <ul class="rectify-list">
            <li v-for="(r, i) in person.rectify" :key="i">{{ r }}</li>
          </ul>
          <div class="level-req-row">
            <span class="req-label">职级要求覆盖：</span>
            <span class="req-chip" :class="i < person.level_covered ? 'ok' : 'no'"
                  v-for="(rq, i) in person.level_req" :key="i">{{ rq }}</span>
            <span class="req-count">{{ person.level_covered }}/{{ person.level_req.length }}</span>
          </div>
        </div>

        <!-- 综合分数条 -->
        <div class="focus-bar">
          <div class="focus-item"><span class="focus-label">综合评分</span><span class="focus-val">{{ person.comp_score }}</span></div>
          <div class="focus-item"><span class="focus-label">岗位职责契合</span><span class="focus-val">{{ person.role_fit }}/20</span></div>
          <div class="focus-item"><span class="focus-label">业绩导向</span><span class="focus-val">{{ person.perf_focus }}/20</span></div>
          <div class="focus-item"><span class="focus-label">团队管理</span><span class="focus-val">{{ person.mgmt_focus }}/20</span></div>
        </div>

        <!-- 四维评估：电商行业属性 / 岗位要求 / 岗位书写参考维度 / 日报书写展现 -->
        <div class="assess-grid">
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">🏭 电商行业属性</span><span class="assess-score" :class="assessCls(person.assess?.industry?.score)">{{ person.assess?.industry?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ person.assess?.industry?.comment || '本周无日志，无法评估行业属性' }}</div>
          </div>
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">👤 岗位要求契合</span><span class="assess-score" :class="assessCls(person.assess?.role?.score)">{{ person.assess?.role?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ person.assess?.role?.comment || '本周无日志，无法评估岗位要求' }}</div>
          </div>
          <div class="assess-item writing-ref-assess">
            <div class="assess-head"><span class="assess-name">🧭 岗位书写维度</span><span class="assess-score" :class="assessCls(person.assess?.writing_reference?.score)">{{ person.assess?.writing_reference?.score ?? 0 }}/20</span></div>
            <div class="assess-template">{{ person.assess?.writing_reference?.template || '管理岗参考模板' }}</div>
            <div class="assess-cmt">{{ person.assess?.writing_reference?.comment || '本周无日志，无法评估岗位书写维度' }}</div>
          </div>
          <div class="assess-item">
            <div class="assess-head"><span class="assess-name">✍️ 日报书写展现</span><span class="assess-score" :class="assessCls(person.assess?.writing?.score)">{{ person.assess?.writing?.score ?? 0 }}/20</span></div>
            <div class="assess-cmt">{{ person.assess?.writing?.comment || '本周无日志，无法评估书写展现' }}</div>
          </div>
        </div>

        <div class="detail-grid">
          <div class="panel">
            <div class="panel-title">评分维度（五维雷达）</div>
            <div ref="radarEl" class="chart-box"></div>
          </div>
          <div class="panel">
            <div class="panel-title">岗位职责覆盖（{{ person.title }}）</div>
            <div class="role-table">
              <div v-for="d in person.role_detail" :key="d.name" class="role-row">
                <div class="role-name">
                  <span class="role-dot" :class="d.covered ? 'ok' : 'no'">{{ d.covered ? '✓' : '✗' }}</span>
                  {{ d.name }}
                </div>
                <div class="role-evidence" :class="d.covered ? '' : 'empty'">
                  {{ d.covered ? d.evidence : '日志中未覆盖该职责板块' }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="report-grid">
          <div class="report-panel">
            <div class="report-title good-title">👍 优点</div>
            <ul class="report-list">
              <li v-for="(s, i) in person.strengths_list" :key="i" class="good-item">{{ s }}</li>
            </ul>
          </div>
          <div class="report-panel">
            <div class="report-title warn-title">💡 需改进方向</div>
            <ul class="report-list">
              <li v-for="(s, i) in person.improvements_list" :key="i" class="warn-item">{{ s }}</li>
            </ul>
          </div>
        </div>

        <div class="comment-box">
          <div class="comment-label">📋 综合评估意见</div>
          <div class="comment-text">{{ person.comment }}</div>
        </div>
          </div>
          <div v-else-if="person" class="no-log-tip">
            {{ person.name }}（{{ person.title }}）本周暂无日志记录
          </div>
        </div>
      </aside>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

const INDIGO = '#4f46e5'

const weeks = ref([])
const week = ref('')
const weekly = ref({ people: [] })
const loading = ref(false)
const selected = ref('')
const person = ref(null)
const drawerOpen = ref(false)
const rankingDownloading = ref(false)
const batchDownloading = ref(false)
const radarEl = ref(null)
let radarChart = null

const weekLabel = (w) => (w || '').replace('-W', '年第') + '周'
const submitCount = computed(() => (weekly.value.people || []).filter(p => p.log_count > 0).length)
const weekAvg = computed(() => {
  const p = (weekly.value.people || []).filter(x => x.log_count > 0)
  if (!p.length) return 0
  return (p.reduce((s, x) => s + (x.avg_score || 0), 0) / p.length).toFixed(1)
})
const gradeDist = computed(() => {
  const p = (weekly.value.people || []).filter(x => x.log_count > 0)
  const ab = p.filter(x => x.grade === 'A' || x.grade === 'B').length
  return p.length ? `${ab}/${p.length}` : 0
})
const deltaCls = computed(() => {
  const d = person.value?.prev_week?.delta
  if (!d) return ''
  return d > 0 ? 'up' : d < 0 ? 'down' : ''
})

async function loadWeeks() {
  try {
    const res = await axios.get('/api/logs-weekly-weeks')
    weeks.value = res.data.weeks || []
    if (weeks.value.length && !weeks.value.includes(week.value)) {
      week.value = weeks.value[0]
    }
  } catch (e) {
    console.error('加载周列表失败', e)
  }
}

async function loadWeekly() {
  if (!week.value) return
  loading.value = true
  try {
    const res = await axios.get('/api/logs-weekly', { params: { week: week.value } })
    weekly.value = res.data
    if (res.data.people?.length) {
      const first = res.data.people.find(p => p.log_count > 0)
      await loadPerson((first || res.data.people[0]).name)  // 静默预载，不打开抽屉
    } else {
      person.value = null
    }
  } catch (e) {
    console.error('加载周报失败', e)
  } finally {
    loading.value = false
  }
}

async function loadPerson(name) {
  selected.value = name
  try {
    const res = await axios.get('/api/logs-weekly', { params: { week: week.value, name } })
    person.value = res.data
    await nextTick()
    renderCharts()
  } catch (e) {
    console.error('加载个人周报失败', e)
  }
}

function selectPerson(name) {
  drawerOpen.value = true
  loadPerson(name)
}

function closeDrawer() {
  drawerOpen.value = false
  radarChart?.dispose(); radarChart = null
}

function exportWeekly() {
  const a = document.createElement('a')
  a.href = `/api/logs-weekly-export?week=${encodeURIComponent(week.value)}`
  a.click()
}

function downloadPersonReport(name) {
  if (!name || !week.value) return
  const a = document.createElement('a')
  a.href = `/api/logs-weekly-person-image?week=${encodeURIComponent(week.value)}&name=${encodeURIComponent(name)}`
  a.download = `${name}_${week.value}_周度日志评分报告.png`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function downloadRankingBoard() {
  if (!week.value || !weekly.value.people?.length || rankingDownloading.value) return
  rankingDownloading.value = true
  try {
    const res = await axios.get('/api/logs-weekly-ranking-image', {
      params: { week: week.value },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${week.value}_管理人员周度评分排名看板.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('下载周度排名看板失败', e)
    window.alert('下载排名看板失败，请稍后重试')
  } finally {
    rankingDownloading.value = false
  }
}

async function downloadAllReports() {
  if (!week.value || !weekly.value.people?.length || batchDownloading.value) return
  batchDownloading.value = true
  try {
    const res = await axios.get('/api/logs-weekly-person-images-zip', {
      params: { week: week.value },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${week.value}_管理人员周度日志评分报告.zip`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('批量下载周报图片失败', e)
    window.alert('批量下载失败，请稍后重试')
  } finally {
    batchDownloading.value = false
  }
}

// 三维评估辅助：aScore 返回分数(无日志→null)，aCmt 返回评语，assessCls 返回配色档位
const aScore = (p, key) => (p.log_count && p.assess?.[key]) ? p.assess[key].score : null
const aCmt = (p, key) => (p.assess?.[key])?.comment || ''
function assessCls(s) { return s == null ? '' : s >= 15 ? 'hi' : s >= 10 ? 'mid' : 'lo' }

function renderCharts() {
  if (!person.value || !radarEl.value) return
  const rd = person.value.radar || []
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
      data: [{ value: rd.map(d => d.score), name: person.value.name }],
      areaStyle: { color: 'rgba(79, 70, 229, 0.25)' },
      lineStyle: { color: INDIGO, width: 2 },
      itemStyle: { color: INDIGO },
    }],
  })
}

function onResize() {
  radarChart?.resize()
}

onMounted(async () => {
  await loadWeeks()
  await loadWeekly()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  radarChart?.dispose()
})
</script>

<style scoped>
.weekly-report { padding: 4px 0; }
.weekly-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.week-picker { display: flex; align-items: center; gap: 10px; }
.toolbar-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.picker-label { font-size: 14px; font-weight: 600; color: #1a1a2e; }
.week-select { padding: 7px 12px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 13px; background: #fff; color: #1a1a2e; outline: none; cursor: pointer; }
.week-select:focus { border-color: #4f46e5; }
.range-tip { font-size: 12px; color: #8b8fa8; }
.export-btn { background: #059669; color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
.export-btn:hover:not(:disabled) { background: #047857; }
.export-btn:disabled { opacity: .5; cursor: not-allowed; }
.batch-image-btn { background: #4f46e5; color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
.batch-image-btn:hover:not(:disabled) { background: #4338ca; }
.batch-image-btn:disabled { opacity: .6; cursor: not-allowed; }
.ranking-image-btn { background: #0f766e; color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
.ranking-image-btn:hover:not(:disabled) { background: #115e59; }
.ranking-image-btn:disabled { opacity: .6; cursor: not-allowed; }
.image-report-cell { text-align: center; }
.image-report-btn { border: none; border-radius: 7px; padding: 5px 9px; background: #eef2ff; color: #3730a3; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.image-report-btn:hover { background: #e0e7ff; color: #312e81; }

.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.stat-val { font-size: 28px; font-weight: 700; color: #4f46e5; }
.stat-label { font-size: 13px; color: #8b8fa8; margin-top: 4px; }

.section-title { font-size: 16px; font-weight: 700; color: #1a1a2e; margin: 20px 0 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
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
.tip-cell.rect { color: #92400e; }

.level-tag { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; background: #eef2ff; color: #3730a3; }
.level-tag.lg { font-size: 13px; margin-left: 8px; }
.grade-badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 700; color: #fff; }
.grade-badge.gA { background: #059669; }
.grade-badge.gB { background: #4f46e5; }
.grade-badge.gC { background: #f59e0b; }
.grade-badge.gD { background: #dc2626; }
.grade-badge.lg { font-size: 14px; padding: 4px 14px; margin-left: 10px; }
.week-delta { margin-left: 8px; font-weight: 600; }
.week-delta.up { color: #059669; }
.week-delta.down { color: #dc2626; }

/* 整改建议框 */
.rectify-box { background: #fff7ed; border: 1px solid #fed7aa; border-left: 4px solid #ea580c; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.rectify-label { font-size: 13px; font-weight: 700; color: #9a3412; margin-bottom: 8px; }
.rectify-list { list-style: none; padding: 0; margin: 0 0 10px; }
.rectify-list li { font-size: 13px; color: #7c2d12; line-height: 1.7; padding: 3px 0; }
.rectify-list li::before { content: '▸ '; color: #ea580c; }
.level-req-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.req-label { color: #9a3412; font-weight: 600; }
.req-chip { padding: 2px 8px; border-radius: 20px; font-size: 12px; }
.req-chip.ok { background: #ecfdf5; color: #047857; }
.req-chip.no { background: #fef2f2; color: #b91c1c; }
.req-count { color: #8b8fa8; margin-left: 4px; }

.focus-bar { display: flex; gap: 10px; margin-bottom: 14px; }
.focus-item { flex: 1; background: #fff; border-radius: 10px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
.focus-label { font-size: 13px; color: #6b7280; }
.focus-val { font-size: 18px; font-weight: 700; color: #4f46e5; }

/* 四维评估（电商行业属性 / 岗位要求 / 岗位书写参考维度 / 日报书写展现） */
.assess-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
.assess-item { background: #fff; border-radius: 10px; padding: 12px 14px; border: 1px solid #f3f4f6; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.assess-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; gap: 8px; }
.assess-name { font-size: 13px; font-weight: 700; color: #1a1a2e; white-space: nowrap; }
.assess-score { font-size: 16px; font-weight: 700; }
.assess-score.hi { color: #047857; }
.assess-score.mid { color: #3730a3; }
.assess-score.lo { color: #b91c1c; }
.assess-cmt { font-size: 12px; color: #4b5563; line-height: 1.55; }
.assess-template { font-size: 11px; color: #7c3aed; margin: -2px 0 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.assess-chip { display: inline-block; min-width: 28px; text-align: center; padding: 2px 6px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.assess-chip.hi { background: #ecfdf5; color: #047857; }
.assess-chip.mid { background: #eef2ff; color: #3730a3; }
.assess-chip.lo { background: #fef2f2; color: #b91c1c; }
.assess-na { color: #d1d5db; }

.role-table { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.role-row { border: 1px solid #f3f4f6; border-radius: 8px; padding: 8px 12px; background: #fafafa; }
.role-name { font-size: 13px; font-weight: 600; color: #1a1a2e; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.role-dot { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; font-size: 11px; color: #fff; }
.role-dot.ok { background: #059669; }
.role-dot.no { background: #d1d5db; }
.role-evidence { font-size: 12px; color: #4b5563; line-height: 1.5; }
.role-evidence.empty { color: #9ca3af; font-style: italic; }

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

.comment-box { background: #eef2ff; border-left: 4px solid #4f46e5; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.comment-label { font-size: 13px; font-weight: 700; color: #3730a3; margin-bottom: 6px; }
.comment-text { font-size: 14px; color: #1a1a2e; line-height: 1.7; }

.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.panel { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.05); }
.panel-title { font-size: 14px; font-weight: 600; color: #1a1a2e; margin-bottom: 10px; }
.chart-box { height: 300px; }

.loading-tip { text-align: center; padding: 60px 0; color: #8b8fa8; font-size: 14px; }
.no-log-tip { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 16px; border-radius: 10px; text-align: center; font-size: 14px; }
.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #c7d2fe; border-top-color: #4f46e5; border-radius: 50%; animation: spin .8s linear infinite; vertical-align: -3px; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ===== 抽屉式个人周报 ===== */
.drawer-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, .38); z-index: 300; }
.drawer { position: fixed; top: 0; right: 0; height: 100vh; width: 720px; max-width: 94vw; background: #f0f2f5; z-index: 301; box-shadow: -6px 0 28px rgba(0,0,0,.16); transform: translateX(100%); transition: transform .28s ease; display: flex; flex-direction: column; }
.drawer.open { transform: translateX(0); }
.drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; background: #fff; border-bottom: 1px solid #e8e8e8; position: sticky; top: 0; z-index: 2; }
.drawer-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.drawer-title { font-size: 15px; font-weight: 700; color: #1a1a2e; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.drawer-close { border: none; background: #f3f4f6; color: #4b5563; width: 32px; height: 32px; border-radius: 50%; font-size: 14px; cursor: pointer; flex-shrink: 0; transition: all .2s; }
.drawer-close:hover { background: #fee2e2; color: #dc2626; }
.drawer-body { padding: 16px 20px 32px; overflow-y: auto; flex: 1; }
</style>
