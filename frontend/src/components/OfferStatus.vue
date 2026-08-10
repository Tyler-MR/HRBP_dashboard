<template>
  <div ref="chartRef" style="height: 190px; width: 100%"></div>
  <div class="offer-legend" v-if="items.length">
    <div class="legend-item" v-for="item in items" :key="item.status">
      <span class="dot" :style="{ background: COLOR_MAP[item.status] }"></span>
      <span class="legend-label">{{ item.status }}</span>
      <span class="legend-value">{{ item.count }}</span>
      <span class="legend-pct">{{ calcPct(item.count) }}%</span>
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

const COLOR_MAP = {
  '已发送': '#8FB359',   // 橄榄绿/草绿（漏斗最底层）
  '已接收': '#DAB374',   // 香槟金/卡其色（漏斗第7层）
  '已拒绝': '#CCD582',   // 嫩芽绿（漏斗第8层）
}

const total = computed(() => props.items.reduce((s, i) => s + i.count, 0))

function calcPct(n) {
  if (!total.value) return 0
  return Math.round(n / total.value * 100)
}

function renderChart() {
  if (!chartRef.value || !props.items.length) return
  if (!chart) chart = echarts.init(chartRef.value)

  const option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['40%', '72%'],             // 标准环形
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      padAngle: 4,
      itemStyle: {
        borderColor: '#fff',
        borderWidth: 2,
      },
      label: {
        show: true,
        formatter: '{d}%',
        fontSize: 13,
        fontWeight: 700,
        color: '#374151',
      },
      emphasis: {
        label: { show: true, fontSize: 15 },
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0,0,0,0.18)',
        },
      },
      data: props.items.map(item => ({
        name: item.status,
        value: item.count,
        itemStyle: { color: COLOR_MAP[item.status] || '#999' },
      })),
    }],
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
.offer-legend {
  display: flex; justify-content: center; gap: 14px;
  margin-top: 6px;
}
.legend-item {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; color: #6b7280;
}
.dot { width: 10px; height: 10px; border-radius: 50%; }
.legend-label { color: #888; }
.legend-value { font-weight: 700; color: #1a1a2e; }
.legend-pct { font-weight: 600; color: #2E8B57; }
</style>
