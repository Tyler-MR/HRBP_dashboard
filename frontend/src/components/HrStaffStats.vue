<template>
  <div class="hr-staff-section">
    <!-- 在岗人数总览卡片 -->
    <div class="total-active-card">
      <div class="total-active-inner">
        <div class="total-icon">👥</div>
        <div class="total-info">
          <span class="total-label">在岗总人数</span>
          <span class="total-number">{{ totalActive }}</span>
        </div>
      </div>
      <div class="status-row">
        <div class="status-item">
          <span class="status-dot regular"></span>
          <span>转正 <strong>{{ regularCount }}</strong></span>
        </div>
        <div class="status-item">
          <span class="status-dot probation"></span>
          <span>试用 <strong>{{ probationCount }}</strong></span>
        </div>
      </div>
      <div class="total-detail">
        <span>覆盖 {{ deptCount }} 个部门</span>
        <span class="dot">·</span>
        <span>平均年龄 {{ avgAge }} 岁</span>
        <span class="dot">·</span>
        <span>本科及以上 {{ bachelorPercent }}%</span>
      </div>
    </div>

    <!-- 四图布局 -->
    <div class="chart-grid">
      <!-- 年龄分布 -->
      <div class="chart-card">
        <div class="chart-card-header">
          <h3>📊 年龄分布</h3>
        </div>
        <v-chart class="chart-instance" :option="ageOption" autoresize />
      </div>

      <!-- 学历分布 -->
      <div class="chart-card">
        <div class="chart-card-header">
          <h3>🎓 学历分布</h3>
        </div>
        <v-chart class="chart-instance" :option="educationOption" autoresize />
      </div>

      <!-- 司龄分布 -->
      <div class="chart-card">
        <div class="chart-card-header">
          <h3>⏳ 司龄分布</h3>
        </div>
        <v-chart class="chart-instance" :option="tenureOption" autoresize />
      </div>

      <!-- 各部门在职人数 -->
      <div class="chart-card">
        <div class="chart-card-header">
          <h3>🏢 各部门在职人数</h3>
        </div>
        <v-chart class="chart-instance" :option="deptOption" autoresize />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([PieChart, BarChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  data: { type: Object, default: () => ({}) }
})

// 莫兰迪色系
const colors = ['#7eb8da', '#6aa6c9', '#5b8db8', '#4a7aa3', '#3c688e', '#2e5679', '#1f4465']
const eduColors = ['#c2a5cf', '#9a7eb8', '#6a8fc0', '#4a7aa3', '#3c688e']
const deptColors = ['#7eb8da', '#81c4a8', '#d4a76a', '#c98b6b', '#b87c6a',
                     '#a8b4c0', '#9ab8a0', '#c4a882', '#b8987a', '#8aacb8',
                     '#7aa8c0', '#b0a0b0', '#90b0a0', '#c0a880']

const totalActive = computed(() => props.data?.total_active ?? 0)
const probationCount = computed(() => props.data?.probation_count ?? 0)
const regularCount = computed(() => props.data?.regular_count ?? 0)

const deptCount = computed(() => props.data?.dept_headcount?.length ?? 0)

const avgAge = computed(() => {
  const dist = props.data?.age_distribution ?? []
  if (!dist.length) return '--'
  const total = dist.reduce((s, d) => s + d.count, 0)
  if (!total) return '--'
  const weighted = dist.reduce((s, d) => {
    const nums = d.range.replace('+', '').split('-').map(Number)
    const mid = nums.length === 2 ? (nums[0] + nums[1]) / 2 : nums[0]
    return s + mid * d.count
  }, 0)
  return Math.round(weighted / total)
})

const bachelorPercent = computed(() => {
  const dist = props.data?.education_distribution ?? []
  if (!dist.length) return '--'
  const total = dist.reduce((s, d) => s + d.count, 0)
  if (!total) return '--'
  const higher = dist.filter(d => ['本科', '硕士', '博士'].includes(d.level))
                     .reduce((s, d) => s + d.count, 0)
  return Math.round(higher / total * 100)
})

// 年龄分布 — 环形图
const ageOption = computed(() => {
  const dist = props.data?.age_distribution ?? []
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)' },
    color: colors,
    series: [{
      type: 'pie',
      radius: ['45%', '72%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: {
        show: true,
        formatter: '{b}\n{d}%',
        fontSize: 11,
        color: '#4a5568',
        lineHeight: 16,
      },
      emphasis: {
        label: { show: true, fontSize: 13, fontWeight: 'bold' },
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' }
      },
      data: dist.map(d => ({ name: d.range, value: d.count })),
    }]
  }
})

// 学历分布 — 横向柱状图
const educationOption = computed(() => {
  const dist = props.data?.education_distribution ?? []
  const maxVal = Math.max(...dist.map(d => d.count), 1)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c}人' },
    grid: { left: 80, right: 20, top: 10, bottom: 10 },
    xAxis: { type: 'value', show: false, max: maxVal * 1.3 },
    yAxis: {
      type: 'category',
      data: dist.map(d => d.level),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 12, color: '#4a5568', fontWeight: 500 },
    },
    color: eduColors,
    series: [{
      type: 'bar',
      barWidth: 18,
      barCategoryGap: 10,
      itemStyle: {
        borderRadius: [0, 9, 9, 0],
      },
      label: {
        show: true,
        position: 'right',
        formatter: '{c}人',
        fontSize: 12,
        color: '#4a5568',
        fontWeight: 600,
      },
      data: dist.map((d, i) => ({
        value: d.count,
        itemStyle: { color: eduColors[i % eduColors.length] }
      })),
    }]
  }
})

// 司龄分布 — 横向柱状图
const tenureOption = computed(() => {
  const dist = props.data?.tenure_distribution ?? []
  const maxVal = Math.max(...dist.map(d => d.count), 1)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c}人' },
    grid: { left: 70, right: 20, top: 10, bottom: 10 },
    xAxis: { type: 'value', show: false, max: maxVal * 1.3 },
    yAxis: {
      type: 'category',
      data: dist.map(d => d.range),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 12, color: '#4a5568', fontWeight: 500 },
    },
    color: ['#81c4a8', '#6db894', '#5aac80', '#47a06c', '#349458'],
    series: [{
      type: 'bar',
      barWidth: 18,
      barCategoryGap: 10,
      itemStyle: { borderRadius: [0, 9, 9, 0] },
      label: {
        show: true,
        position: 'right',
        formatter: '{c}人',
        fontSize: 12,
        color: '#4a5568',
        fontWeight: 600,
      },
      data: dist.map((d, i) => ({
        value: d.count,
        itemStyle: { color: ['#81c4a8', '#6db894', '#5aac80', '#47a06c', '#349458'][i % 5] }
      })),
    }]
  }
})

// 各部门在职人数 — 竖版柱状图
const deptOption = computed(() => {
  const dist = props.data?.dept_headcount ?? []
  const maxVal = Math.max(...dist.map(d => d.count), 1)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c}人' },
    grid: { left: 10, right: 30, top: 10, bottom: 60 },
    xAxis: {
      type: 'category',
      data: dist.map(d => d.department),
      axisLabel: {
        fontSize: 10,
        color: '#6b7280',
        interval: 0,
        rotate: dist.length > 8 ? 35 : 0,
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      show: false,
      max: maxVal * 1.35,
    },
    color: deptColors,
    series: [{
      type: 'bar',
      barWidth: dist.length > 10 ? 18 : 24,
      barCategoryGap: '30%',
      itemStyle: { borderRadius: [4, 4, 0, 0] },
      label: {
        show: true,
        position: 'top',
        formatter: (p) => `${p.value}人`,
        fontSize: 10,
        color: '#4a5568',
        fontWeight: 600,
      },
      data: dist.map((d, i) => ({
        value: d.count,
        itemStyle: { color: deptColors[i % deptColors.length] }
      })),
    }]
  }
})
</script>

<style scoped>
.hr-staff-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 在岗人数总览 */
.total-active-card {
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  border-radius: 14px;
  padding: 18px 24px;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.total-active-inner {
  display: flex;
  align-items: center;
  gap: 18px;
}
.total-icon {
  font-size: 32px;
  width: 56px;
  height: 56px;
  background: rgba(255,255,255,0.15);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.total-info {
  display: flex;
  flex-direction: column;
}
.total-label {
  font-size: 14px;
  opacity: 0.9;
  font-weight: 400;
}
.total-number {
  font-size: 40px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -1px;
}
.status-row {
  display: flex;
  gap: 16px;
  align-items: center;
}
.status-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: rgba(255,255,255,0.9);
  white-space: nowrap;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.status-dot.regular { background: #10b981; }
.status-dot.probation { background: #f59e0b; }
.status-item strong { color: #fff; font-weight: 700; }
.total-detail {
  font-size: 13px;
  opacity: 0.85;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.total-detail .dot {
  opacity: 0.5;
}

/* 四图网格 */
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.chart-card-header {
  margin-bottom: 10px;
}
.chart-card-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
}
.chart-instance {
  width: 100%;
  height: 200px;
}

@media (max-width: 960px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .total-active-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
