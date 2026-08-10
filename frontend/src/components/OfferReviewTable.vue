<template>
  <div class="card">
    <div class="card-header">
      <h2>📊 复试通过及 Offer 接受复盘</h2>
      <span class="badge">终面 → Offer 链路</span>
    </div>

    <!-- 总览卡片 -->
    <div class="overview-row" v-if="items.length">
      <div class="ov-card">
        <div class="ov-num" style="color:#7c3aed">{{ totals.second_round_passes }}</div>
        <div class="ov-label">复试通过</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:#059669">{{ totals.offers_accepted }}</div>
        <div class="ov-label">接受Offer</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:#d97706">{{ totals.offers_declined }}</div>
        <div class="ov-label">放弃Offer</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:#2563eb">{{ acceptRate }}%</div>
        <div class="ov-label">接受率</div>
      </div>
    </div>

    <!-- 竖向柱状图 -->
    <div ref="chartRef" style="height: 200px; width: 100%; margin-top: 4px"></div>

    <!-- 放弃原因汇总 -->
    <div class="reasons-wrap" v-if="hasReasons">
      <div class="reason-title">⛔ 放弃原因汇总（共{{ totalDeclined }}人）</div>
      <div class="reason-grid">
        <div class="reason-card" v-for="item in reasonList" :key="item.department + item.position">
          <div class="rc-head">
            <span class="rc-dept">{{ item.department }}</span>
            <span class="rc-pos">{{ item.position }}</span>
            <span class="rc-count">-{{ item.offers_declined }}</span>
          </div>
          <div class="rc-body">{{ item.decline_reason }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  items: { type: Array, default: () => [] },
})

const chartRef = ref(null)
let chart = null

const totals = computed(() => props.items.find(i => !i.department) || {})

const acceptRate = computed(() => {
  const t = totals.value
  if (!t.offers_accepted || !t.second_round_passes) return 0
  return Math.round(t.offers_accepted / t.second_round_passes * 100)
})

const dataRows = computed(() =>
  props.items.filter(i => i.department && i.position !== '合计')
)

const hasReasons = computed(() => props.items.some(i => i.decline_reason))

const reasonList = computed(() =>
  props.items.filter(i => i.decline_reason && i.department)
)

const totalDeclined = computed(() =>
  reasonList.value.reduce((s, i) => s + i.offers_declined, 0)
)

function renderChart() {
  if (!chartRef.value || !dataRows.value.length) return
  if (!chart) chart = echarts.init(chartRef.value)

  const names = dataRows.value.map(i => i.department + '\n' + i.position)
  const passes = dataRows.value.map(i => i.second_round_passes)
  const accepts = dataRows.value.map(i => i.offers_accepted)
  const declines = dataRows.value.map(i => i.offers_declined)
  const maxV = Math.max(...passes, ...accepts, ...declines, 1)

  const option = {
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'shadow' },
    },
    legend: {
      data: ['复试通过', '接受Offer', '放弃Offer'],
      bottom: 0,
      textStyle: { fontSize: 10 },
      itemWidth: 10,
      itemHeight: 8,
    },
    grid: {
      left: 8, right: 8, top: 8, bottom: 48,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        fontSize: 10,
        rotate: 0,
        interval: 0,
        lineHeight: 14,
        width: 64,
        overflow: 'break',
        color: '#1a1a2e',
        fontWeight: 500,
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'value',
      max: maxV + 1,
      splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        name: '复试通过',
        type: 'bar',
        barWidth: 10,
        barGap: '20%',
        itemStyle: { color: '#7c3aed', borderRadius: [4, 4, 0, 0] },
        data: passes,
      },
      {
        name: '接受Offer',
        type: 'bar',
        barWidth: 10,
        itemStyle: { color: '#059669', borderRadius: [4, 4, 0, 0] },
        data: accepts,
      },
      {
        name: '放弃Offer',
        type: 'bar',
        barWidth: 10,
        itemStyle: { color: '#d97706', borderRadius: [4, 4, 0, 0] },
        data: declines,
      },
    ],
  }

  chart.setOption(option, true)
  chart.resize()
}

watch(() => props.items, renderChart, { deep: true })
onMounted(() => {
  renderChart()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
function handleResize() { chart?.resize() }
</script>

<style scoped>
.card {
  background: #fff; border-radius: 12px;
  padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  margin-bottom: 16px;
}
.card-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.card-header h2 { font-size: 15px; font-weight: 600; color: #1a1a2e; }
.badge {
  font-size: 11px; color: #6b7280; background: #f3f4f6;
  padding: 3px 10px; border-radius: 10px;
}

.overview-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  margin-bottom: 4px;
}
.ov-card {
  text-align: center; padding: 10px 8px;
  background: #f8fafc; border-radius: 10px;
}
.ov-num { font-size: 22px; font-weight: 700; line-height: 1.2; }
.ov-label { font-size: 11px; color: #6b7280; margin-top: 2px; }

.reasons-wrap {
  margin-top: 8px; padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
.reason-title {
  font-size: 12px; font-weight: 600; color: #1a1a2e; margin-bottom: 8px;
}
.reason-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
}
.reason-card {
  padding: 8px 10px; background: #fffbeb; border-radius: 6px;
  border-left: 3px solid #d97706;
}
.rc-head {
  display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
}
.rc-dept { font-weight: 600; font-size: 11px; color: #92400e; }
.rc-pos { font-size: 11px; color: #6b7280; }
.rc-count { font-size: 11px; color: #dc2626; font-weight: 700; margin-left: auto; }
.rc-body { font-size: 11px; line-height: 1.4; color: #6b7280; }
</style>
