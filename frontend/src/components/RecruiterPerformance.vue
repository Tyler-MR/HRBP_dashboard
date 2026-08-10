<template>
  <div>
    <div ref="chartRef" style="height: 200px; width: 100%"></div>
    <div class="recruiter-table" v-if="recruiters.length">
      <div class="rt-row rt-header">
        <span class="rt-rank">#</span>
        <span class="rt-name">姓名</span>
        <span class="rt-dept">组别</span>
        <span class="rt-num">简历</span>
        <span class="rt-num">面试</span>
        <span class="rt-num">入职</span>
        <span class="rt-rate">Offer接受率</span>
      </div>
      <div class="rt-row" v-for="(rec, idx) in recruiters" :key="rec.id">
        <span class="rt-rank">
          <span class="rank-badge" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</span>
        </span>
        <span class="rt-name">{{ rec.name }}</span>
        <span class="rt-dept">{{ rec.department }}</span>
        <span class="rt-num">{{ rec.resumes_handled }}</span>
        <span class="rt-num">{{ rec.interviews_arranged }}</span>
        <span class="rt-num hires-num">{{ rec.hires }}</span>
        <span class="rt-rate">
          <span class="rate-tag" :class="rateClass(rec.offer_accept_rate)">{{ rec.offer_accept_rate }}%</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  recruiters: { type: Array, default: () => [] },
})

const chartRef = ref(null)
let chart = null

function renderChart() {
  if (!chartRef.value || !props.recruiters.length) return
  if (!chart) chart = echarts.init(chartRef.value)

  const names = props.recruiters.map(r => r.name)
  const hires = props.recruiters.map(r => r.hires)
  const interviews = props.recruiters.map(r => r.interviews_arranged)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['面试人数', '入职人数'],
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: { left: 40, right: 20, top: 15, bottom: 40 },
    xAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { fontSize: 11, color: '#6b7280' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
      axisLabel: { fontSize: 11, color: '#9ca3af' },
    },
    series: [
      {
        name: '面试人数',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { color: '#DAB374', width: 2 },
        itemStyle: { color: '#DAB374' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(218,179,116,0.25)' },
          { offset: 1, color: 'rgba(218,179,116,0.02)' },
        ]) },
        data: interviews,
      },
      {
        name: '入职人数',
        type: 'line',
        smooth: true,
        symbol: 'diamond',
        symbolSize: 9,
        lineStyle: { color: '#CCD582', width: 2 },
        itemStyle: { color: '#CCD582' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(204,213,130,0.25)' },
          { offset: 1, color: 'rgba(204,213,130,0.02)' },
        ]) },
        data: hires,
      },
    ],
  }
  chart.setOption(option, true)
  chart.resize()
}

watch(() => props.recruiters, renderChart, { deep: true })

onMounted(() => {
  renderChart()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})
function handleResize() { chart?.resize() }
function rateClass(rate) {
  if (rate >= 80) return 'tag-green'
  if (rate >= 50) return 'tag-yellow'
  return 'tag-red'
}
</script>

<style scoped>
.recruiter-table { margin-top: 8px; font-size: 12px; }
.rt-row {
  display: grid;
  grid-template-columns: 28px 50px 60px 1fr 1fr 1fr 1fr;
  gap: 4px; padding: 5px 4px; align-items: center;
  border-bottom: 1px solid #f8f9fa;
}
.rt-header {
  font-weight: 600; color: #6b7280; font-size: 11px;
  border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;
}
.rt-name { font-weight: 500; color: #1a1a2e; }
.rt-dept { color: #888; font-size: 11px; }
.rt-num { text-align: center; color: #374151; }
.rt-rate { text-align: center; }
.hires-num { font-weight: 700; color: #4f46e5; }
.rank-badge {
  width: 20px; height: 20px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; color: #fff;
}
.rank-1 { background: #f59e0b; }
.rank-2 { background: #94a3b8; }
.rank-3 { background: #d97706; }
.rate-tag {
  display: inline-block; padding: 1px 6px; border-radius: 6px;
  font-size: 11px; font-weight: 600;
}
.tag-green { background: #d1fae5; color: #059669; }
.tag-yellow { background: #fef3c7; color: #d97706; }
.tag-red { background: #fee2e2; color: #dc2626; }
</style>
