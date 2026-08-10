<template>
  <div class="dashboard">
    <!-- 头部 -->
    <header class="dashboard-header">
      <div class="header-left">
        <h1>📊 招聘数据看板</h1>
        <span class="update-tag">实时更新</span>
        <div class="view-toggle">
          <button :class="['toggle-btn', { active: viewType === 'monthly' }]" @click="switchView('monthly')">月度</button>
          <button :class="['toggle-btn', { active: viewType === 'yearly' }]" @click="switchView('yearly')">年度</button>
        </div>
        <input v-if="viewType === 'monthly'" type="month" class="month-picker"
               v-model="currentMonth" @change="onViewChange" />
        <input v-else type="number" class="year-picker"
               v-model.number="currentYear" @change="onViewChange" min="2020" max="2030" />
      </div>
      <div class="header-right">
        <span class="update-time">🕐 {{ updatedAt }}</span>
        <button class="refresh-btn" @click="loadData" :disabled="loading">
          {{ loading ? '⏳ 加载中' : '🔄 刷新' }}
        </button>
      </div>
    </header>

    <!-- Row 1: 概览卡片 -->
    <SummaryCards :data="overview" />

    <!-- Row 2: 图表区域（左侧大漏斗 + 右侧Offer饼图+招聘人员排行） -->
    <div class="chart-row">
      <div class="card funnel-card">
        <div class="card-header">
          <h2>🔻 招聘漏斗</h2>
          <span class="badge">邀约 → 初试 → 复试 → 已接收 → 到岗 → 满7天</span>
        </div>
        <RecruitmentFunnel :stages="funnel.stages" />
      </div>
      <div class="right-cards">
        <div class="card">
          <div class="card-header">
            <h2>✅ Offer 状态</h2>
          </div>
          <OfferStatus :items="offerStatus.items" />
        </div>
        <div class="card">
          <div class="card-header">
            <h2>👥 招聘人员产出</h2>
          </div>
          <RecruiterPerformance :recruiters="sortedRecruiters" />
        </div>
      </div>
    </div>

    <!-- Row 3: 岗位明细表（全部数据列） -->
    <div class="card">
      <div class="card-header">
        <h2>📋 岗位招聘明细</h2>
        <span class="badge">各岗位全流程数据一览</span>
      </div>
      <PositionTable :positions="positions" />
    </div>

    <!-- Row 4: 复试通过及Offer复盘明细 -->
    <OfferReviewTable :items="offerReview" />

    <!-- Row 5: 招聘达成进度一览 -->
    <ProgressTable :items="progressItems" :summary="progressSummary" :month="displayMonth" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchDashboard } from '../api/index.js'
import SummaryCards from './SummaryCards.vue'
import RecruitmentFunnel from './RecruitmentFunnel.vue'
import OfferStatus from './OfferStatus.vue'
import PositionTable from './PositionTable.vue'
import RecruiterPerformance from './RecruiterPerformance.vue'
import OfferReviewTable from './OfferReviewTable.vue'
import ProgressTable from './ProgressTable.vue'

const loading = ref(false)
const updatedAt = ref('--')
const viewType = ref('monthly')
const currentMonth = ref('')
const currentYear = ref(2026)
const overview = ref({})
const funnel = ref({ stages: [] })
const offerStatus = ref({ items: [] })
const positions = ref([])
const recruiters = ref([])
const offerReview = ref([])
const progressItems = ref([])
const progressSummary = ref(null)

const sortedRecruiters = computed(() => {
  return [...recruiters.value].sort((a, b) => b.hires - a.hires)
})

// 当前展示的月份（月度视图显示所选月份；年度视图显示当前年）
const displayMonth = computed(() => {
  if (viewType.value === 'yearly') return `${currentYear.value}-12`
  return currentMonth.value || formatMonth(new Date())
})

let timer = null

function formatMonth(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

async function loadData() {
  loading.value = true
  try {
    const params = { viewType: viewType.value }
    if (viewType.value === 'yearly') {
      params.year = String(currentYear.value)
    } else {
      params.month = currentMonth.value || undefined
    }
    const data = await fetchDashboard(params)
    overview.value = data.overview || {}
    funnel.value = data.funnel || { stages: [] }
    offerStatus.value = data.offer_status || { items: [] }
    positions.value = data.positions || []
    recruiters.value = data.recruiters || []
    offerReview.value = data.offer_review || []
    progressItems.value = data.progress_items || []
    progressSummary.value = data.progress_summary || null
    updatedAt.value = data.updated_at || new Date().toLocaleString()
  } catch (err) {
    console.error('加载看板数据失败:', err)
  } finally {
    loading.value = false
  }
}

function onViewChange() {
  loadData()
}

function switchView(type) {
  viewType.value = type
  loadData()
}

onMounted(() => {
  currentMonth.value = formatMonth(new Date())
  currentYear.value = new Date().getFullYear()
  loadData()
  timer = setInterval(loadData, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
/* 头部 */
.dashboard-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; padding-bottom: 14px;
  border-bottom: 2px solid #e8e8e8;
}
.header-left { display: flex; align-items: center; gap: 10px; }
.header-left h1 { font-size: 22px; font-weight: 700; }
.update-tag {
  font-size: 11px; background: #4f46e5; color: #fff;
  padding: 2px 10px; border-radius: 10px; font-weight: 500;
}
.month-picker {
  font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db;
  border-radius: 6px; background: #fff; color: #374151;
  cursor: pointer; outline: none; margin-left: 4px;
}
.month-picker:focus { border-color: #4f46e5; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
.year-picker {
  font-size: 13px; padding: 4px 8px; border: 1px solid #d1d5db;
  border-radius: 6px; background: #fff; color: #374151;
  cursor: pointer; outline: none; margin-left: 4px; width: 80px;
}
.year-picker:focus { border-color: #4f46e5; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
.view-toggle {
  display: inline-flex; border: 1px solid #d1d5db; border-radius: 6px;
  overflow: hidden; margin-left: 4px;
}
.toggle-btn {
  padding: 4px 12px; font-size: 12px; border: none; cursor: pointer;
  background: #fff; color: #6b7280; font-weight: 500;
  transition: all 0.15s;
}
.toggle-btn.active { background: #4f46e5; color: #fff; }
.toggle-btn:not(.active):hover { background: #f3f4f6; }
.header-right { display: flex; align-items: center; gap: 14px; }
.update-time { font-size: 13px; color: #888; }
.refresh-btn {
  padding: 7px 16px; border: none; border-radius: 6px;
  background: #4f46e5; color: #fff; font-size: 13px;
  cursor: pointer; transition: 0.2s;
}
.refresh-btn:hover { background: #4338ca; }
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* 卡片通用 */
.card {
  background: #fff; border-radius: 12px;
  padding: 20px; margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.card-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.card-header h2 { font-size: 15px; font-weight: 600; color: #1a1a2e; }
.badge {
  font-size: 11px; color: #6b7280; background: #f3f4f6;
  padding: 3px 10px; border-radius: 10px;
}

/* 图表行布局 */
.chart-row {
  display: grid; grid-template-columns: 2fr 1fr; gap: 16px;
  margin-bottom: 16px;
}
.funnel-card { min-height: 400px; }
.right-cards { display: flex; flex-direction: column; gap: 16px; }
.right-cards .card { flex: 1; }

@media (max-width: 960px) {
  .chart-row { grid-template-columns: 1fr; }
}
</style>
