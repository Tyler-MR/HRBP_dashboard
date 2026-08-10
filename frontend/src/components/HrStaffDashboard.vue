<template>
  <div class="staff-dashboard">
    <!-- 头部 -->
    <header class="dashboard-header">
      <div class="header-left">
        <h1>👥 人员结构统计</h1>
        <span class="update-tag">实时更新</span>
        <label class="month-label">📅
          <input type="month" v-model="month" @change="loadData()" class="month-picker" />
        </label>
      </div>
      <div class="header-right">
        <span class="update-time">🕐 {{ updatedAt }}</span>
        <button class="refresh-btn" @click="loadData" :disabled="loading">
          {{ loading ? '⏳ 加载中' : '🔄 刷新' }}
        </button>
      </div>
    </header>

    <!-- 粒度切换：年度 / 半年度 / 季度 / 月度 -->
    <div class="period-bar">
      <button v-for="p in periods" :key="p.value"
        :class="['period-btn', { active: staffPeriod === p.value }]"
        @click="setPeriod(p.value)">
        {{ p.label }}
      </button>
    </div>

    <!-- 趋势：入职/在岗 -->
    <div class="trend-card" v-if="trendData.length">
      <div class="trend-title">📈 入职人数 / 在岗趋势（{{ periodText }}） <span class="trend-note">（历史月在岗为近似值，当前月精确）</span></div>
      <div ref="trendChartRef" class="trend-chart"></div>
    </div>

    <!-- 学历筛选栏 -->
    <div class="filter-bar" v-if="eduOptions.length">
      <span class="filter-label">学历筛选：</span>
      <button v-for="opt in eduOptions" :key="opt.level"
        :class="['filter-chip', { active: selectedEdu.includes(opt.level) }]"
        @click="toggleEduFilter(opt.level)">
        {{ opt.level }}（{{ opt.total }}）
      </button>
      <button v-if="selectedEdu.length" class="filter-clear" @click="selectedEdu=[]; loadData()">
        ✕ 清除筛选
      </button>
    </div>

    <!-- 人员结构内容 -->
    <HrStaffStats :data="hrStaff" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { fetchDashboard } from '../api/index.js'
import HrStaffStats from './HrStaffStats.vue'

const loading = ref(false)
const updatedAt = ref('--')
const hrStaff = ref({})
const selectedEdu = ref([])
// 看板设定月份：人员结构按该月末快照 + 月度趋势
const month = ref(new Date().toISOString().slice(0, 7))
const trendChartRef = ref(null)
let trendChart = null

const eduOptions = computed(() => hrStaff.value?.available_educations ?? [])
const trendData = computed(() => hrStaff.value?.monthly_trend ?? [])

// 粒度切换：年度/半年度/季度/月度（趋势图）
const periods = [
  { value: 'year', label: '年度' },
  { value: 'half', label: '半年度' },
  { value: 'quarter', label: '季度' },
  { value: 'month', label: '月度' },
]
const staffPeriod = ref('month')
const periodText = computed(() => periods.find(p => p.value === staffPeriod.value)?.label || '月度')
function setPeriod(v) {
  staffPeriod.value = v
  loadData()
}

function toggleEduFilter(level) {
  const idx = selectedEdu.value.indexOf(level)
  if (idx >= 0) {
    selectedEdu.value.splice(idx, 1)
  } else {
    selectedEdu.value.push(level)
  }
  loadData()
}

function renderTrend() {
  if (!trendChartRef.value || !trendData.value.length) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)
  const t = trendData.value
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['入职人数', '月末在岗'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 44, top: 30, bottom: 24 },
    xAxis: { type: 'category', data: t.map(x => x.month), axisLabel: { fontSize: 10, interval: 0 } },
    yAxis: [
      { type: 'value', name: '入职', minInterval: 1, axisLabel: { fontSize: 10 } },
      { type: 'value', name: '在岗', minInterval: 1, axisLabel: { fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      { name: '入职人数', type: 'bar', barMaxWidth: 16, data: t.map(x => x.hires), itemStyle: { color: '#4f46e5', borderRadius: [3, 3, 0, 0] } },
      { name: '月末在岗', type: 'line', smooth: true, yAxisIndex: 1, data: t.map(x => x.headcount), lineStyle: { width: 2.5, color: '#059669' }, itemStyle: { color: '#059669' } },
    ],
  }, true)
  trendChart.resize()
}

let timer = null

async function loadData() {
  loading.value = true
  try {
    const params = { month: month.value, staff_period: staffPeriod.value }
    if (selectedEdu.value.length) {
      params.edu_filter = selectedEdu.value.join(',')
    }
    const data = await fetchDashboard(params)
    hrStaff.value = data.hr_staff || {}
    updatedAt.value = data.updated_at || new Date().toLocaleString()
    nextTick(renderTrend)
  } catch (err) {
    console.error('加载人员结构数据失败:', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
  timer = setInterval(loadData, 30000)
  window.addEventListener('resize', () => trendChart?.resize())
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (trendChart) { trendChart.dispose(); trendChart = null }
})
</script>

<style scoped>
.dashboard-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; padding-bottom: 14px;
  border-bottom: 2px solid #e8e8e8;
}
.header-left { display: flex; align-items: center; gap: 10px; }
.header-left h1 { font-size: 22px; font-weight: 700; }
.month-label { font-size: 12px; color: #555; display: flex; align-items: center; gap: 4px; }
.month-picker { padding: 3px 6px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 12px; color: #374151; background: #fff; cursor: pointer; }
.month-picker:focus { border-color: #4f46e5; outline: none; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
.update-tag {
  font-size: 11px; background: #4f46e5; color: #fff;
  padding: 2px 10px; border-radius: 10px; font-weight: 500;
}
.header-right { display: flex; align-items: center; gap: 14px; }
.update-time { font-size: 13px; color: #888; }
.refresh-btn {
  padding: 7px 16px; border: none; border-radius: 6px;
  background: #4f46e5; color: #fff; font-size: 13px;
  cursor: pointer; transition: 0.2s;
}
.refresh-btn:hover { background: #4338ca; }
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.filter-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 16px; padding: 10px 14px;
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
/* 月度趋势图 */
.trend-card { background: #fff; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
.trend-title { font-size: 13px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }
.trend-note { font-size: 11px; font-weight: 400; color: #9ca3af; }
.trend-chart { width: 100%; height: 220px; }
/* 粒度切换 */
.period-bar { display: flex; gap: 6px; margin-bottom: 12px; }
.period-btn {
  padding: 6px 16px; border: 1px solid #d1d5db; border-radius: 8px;
  background: #fff; color: #374151; font-size: 12px; font-weight: 500; cursor: pointer; transition: 0.15s;
}
.period-btn:hover { border-color: #4f46e5; color: #4f46e5; }
.period-btn.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }
.filter-label { font-size: 13px; color: #6b7280; font-weight: 500; white-space: nowrap; }
.filter-chip {
  padding: 4px 12px; border: 1px solid #d1d5db; border-radius: 16px;
  background: #fff; color: #374151; font-size: 12px; cursor: pointer;
  transition: all 0.2s;
}
.filter-chip.active {
  background: #4f46e5; color: #fff; border-color: #4f46e5;
}
.filter-chip:hover:not(.active) { border-color: #4f46e5; color: #4f46e5; }
.filter-clear {
  padding: 4px 10px; border: none; border-radius: 16px;
  background: #fee2e2; color: #ef4444; font-size: 11px; cursor: pointer;
}
.filter-clear:hover { background: #fecaca; }
</style>
