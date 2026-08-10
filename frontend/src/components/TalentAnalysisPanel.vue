<template>
  <div class="talent-panel">
    <!-- 面板头部 & 部门选择 -->
    <div class="panel-header">
      <h3>🧬 人才质量分析</h3>
      <div class="dept-selector">
        <select v-model="selectedDept" @change="onDeptChange" class="dept-select">
          <option value="" disabled>请选择部门</option>
          <option v-for="d in departments" :key="d.department" :value="d.department">
            {{ d.department }}（{{ d.employee_count }}人）
          </option>
        </select>
      </div>
    </div>

    <!-- 部门综合评分概览 -->
    <div class="dept-overview-card" v-if="currentDept">
      <div class="dept-score-main">
        <div class="score-ring" :style="{ borderColor: gradeColor(currentDept.grade) }">
          {{ currentDept.overall_score }}
        </div>
        <div class="score-info">
          <span class="dept-grade" :style="{ color: gradeColor(currentDept.grade) }">{{ currentDept.grade }}</span>
          <span class="dept-rank-label">综合评分 · 排名第{{ currentDept.rank }}</span>
          <span class="dept-name">{{ selectedDept }}</span>
        </div>
      </div>
      <div class="dept-dimensions">
        <div class="dim-item" v-for="dim in deptDims" :key="dim.label">
          <span class="dim-label">{{ dim.label }}</span>
          <div class="dim-bar-bg">
            <div class="dim-bar-fill" :style="{ width: dim.score + '%', background: dim.color }"></div>
          </div>
          <span class="dim-value">{{ dim.score }}</span>
        </div>
      </div>
    </div>

    <!-- 部门雷达图 -->
    <div class="chart-card" v-if="currentDept">
      <div class="chart-header"><h4>📡 部门能力雷达 — {{ selectedDept }}</h4></div>
      <v-chart :option="deptRadarOption" autoresize class="radar-chart" />
    </div>

    <!-- 部门员工列表 + 员工雷达 -->
    <div class="employee-section" v-if="deptEmployees.length > 0">
      <div class="chart-header">
        <h4>👥 团队成员（{{ deptEmployees.length }}人）</h4>
        <span class="badge">点击查看个人雷达</span>
      </div>
      <div class="emp-layout">
        <div class="emp-list">
          <div
            class="emp-item"
            v-for="emp in deptEmployees"
            :key="emp.employee_id"
            :class="{ selected: selectedEmp?.employee_id === emp.employee_id }"
            @click="selectedEmp = emp"
          >
            <span class="emp-avatar">{{ emp.name.charAt(0) }}</span>
            <div class="emp-meta">
              <span class="emp-name">{{ emp.name }}</span>
              <span class="emp-pos">{{ emp.position }}</span>
            </div>
            <span class="emp-score">{{ avgScore(emp) }}</span>
          </div>
        </div>
        <div class="emp-radar-wrap" v-if="selectedEmp">
          <div class="chart-header">
            <h4>🧬 {{ selectedEmp.name }} 人才雷达</h4>
            <span class="badge">{{ selectedEmp.position }}</span>
          </div>
          <v-chart :option="empRadarOption" autoresize class="radar-chart-sm" />
          <div class="emp-dim-detail">
            <div class="dim-tag" v-for="dim in empDims" :key="dim.label" :style="{ borderLeftColor: dim.color }">
              <span class="dim-tag-label">{{ dim.label }}</span>
              <span class="dim-tag-value">{{ dim.score }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 部门排名表 -->
    <div class="chart-card full-width">
      <div class="chart-header"><h4>🏆 部门人才质量排名</h4></div>
      <div class="table-wrapper">
        <table class="rank-table">
          <thead>
            <tr>
              <th>排名</th><th>部门</th><th>人数</th>
              <th>专业能力</th><th>沟通协作</th><th>创新能力</th>
              <th>执行力</th><th>学习能力</th><th>责任感</th>
              <th>综合分</th><th>等级</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in departments" :key="d.department"
                :class="{ highlight: d.department === selectedDept }">
              <td class="rank-cell">{{ d.rank }}</td>
              <td class="dept-cell">{{ d.department }}</td>
              <td>{{ d.employee_count }}</td>
              <td>{{ d.avg_professional }}</td>
              <td>{{ d.avg_communication }}</td>
              <td>{{ d.avg_innovation }}</td>
              <td>{{ d.avg_execution }}</td>
              <td>{{ d.avg_learning }}</td>
              <td>{{ d.avg_responsibility }}</td>
              <td class="score-cell">{{ d.overall_score }}</td>
              <td><span :class="'grade grade-' + d.grade.toLowerCase()">{{ d.grade }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import {
  TooltipComponent, LegendComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchTalentAnalysis } from '../api/index.js'

use([
  CanvasRenderer, RadarChart,
  TooltipComponent, LegendComponent,
])

// 莫兰迪色系维度颜色
const DIM_COLORS = {
  professional: '#4f46e5',
  communication: '#7c3aed',
  innovation: '#f59e0b',
  execution: '#10b981',
  learning: '#3b82f6',
  responsibility: '#ef4444',
}

const GRADE_COLORS = {
  S: '#10b981',
  A: '#3b82f6',
  B: '#f59e0b',
  C: '#ef4444',
}

const DIM_LABELS = [
  { key: 'professional', label: '专业能力', color: DIM_COLORS.professional },
  { key: 'communication', label: '沟通协作', color: DIM_COLORS.communication },
  { key: 'innovation', label: '创新能力', color: DIM_COLORS.innovation },
  { key: 'execution', label: '执行力', color: DIM_COLORS.execution },
  { key: 'learning', label: '学习能力', color: DIM_COLORS.learning },
  { key: 'responsibility', label: '责任感', color: DIM_COLORS.responsibility },
]

function gradeColor(grade) {
  return GRADE_COLORS[grade] || '#6b7280'
}

function avgScore(emp) {
  const scores = [emp.professional, emp.communication, emp.innovation, emp.execution, emp.learning, emp.responsibility]
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
}

const departments = ref([])
const selectedDept = ref('')
const deptEmployees = ref([])
const selectedEmp = ref(null)
let timer = null

const currentDept = computed(() => {
  return departments.value.find(d => d.department === selectedDept.value) || null
})

const deptDims = computed(() => {
  const d = currentDept.value
  if (!d) return []
  return DIM_LABELS.map(({ key, label, color }) => ({
    label,
    score: d[`avg_${key}`],
    color,
    key,
  }))
})

const empDims = computed(() => {
  const emp = selectedEmp.value
  if (!emp) return []
  return DIM_LABELS.map(({ key, label, color }) => ({
    label,
    score: emp[key],
    color,
    key,
  }))
})

// 部门雷达图
const deptRadarOption = computed(() => {
  const dims = deptDims.value
  if (!dims.length) return {}
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderWidth: 0,
      borderRadius: 8,
    },
    radar: {
      indicator: dims.map(d => ({ name: d.label, max: 100 })),
      center: ['50%', '50%'],
      radius: '65%',
      axisName: { color: '#4a5568', fontSize: 12, fontWeight: 500 },
      splitArea: {
        areaStyle: {
          color: ['rgba(79,70,229,0.02)', 'rgba(79,70,229,0.05)', 'rgba(79,70,229,0.02)', 'rgba(79,70,229,0.05)'],
        },
      },
      axisLine: { lineStyle: { color: 'rgba(79,70,229,0.2)' } },
      splitLine: { lineStyle: { color: 'rgba(79,70,229,0.15)' } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: dims.map(d => d.score),
        name: selectedDept.value,
        areaStyle: { color: 'rgba(79,70,229,0.2)' },
        lineStyle: { color: '#4f46e5', width: 2 },
        itemStyle: { color: '#4f46e5' },
      }],
    }],
  }
})

// 员工雷达图
const empRadarOption = computed(() => {
  const dims = empDims.value
  if (!dims.length) return {}
  // Use the department avg as comparison
  const dept = currentDept.value
  const deptValues = dept ? DIM_LABELS.map(({ key }) => dept[`avg_${key}`]) : []
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderWidth: 0,
      borderRadius: 8,
    },
    legend: {
      data: [selectedEmp.value?.name || '个人', '部门平均'],
      bottom: -4,
      icon: 'circle',
      itemWidth: 8,
      textStyle: { fontSize: 11, color: '#6b7280' },
    },
    radar: {
      indicator: dims.map(d => ({ name: d.label, max: 100 })),
      center: ['50%', '52%'],
      radius: '60%',
      axisName: { color: '#4a5568', fontSize: 11, fontWeight: 500 },
      splitArea: {
        areaStyle: {
          color: ['rgba(79,70,229,0.02)', 'rgba(79,70,229,0.05)', 'rgba(79,70,229,0.02)', 'rgba(79,70,229,0.05)'],
        },
      },
      axisLine: { lineStyle: { color: 'rgba(79,70,229,0.2)' } },
      splitLine: { lineStyle: { color: 'rgba(79,70,229,0.15)' } },
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: dims.map(d => d.score),
          name: selectedEmp.value?.name || '个人',
          areaStyle: { color: 'rgba(79,70,229,0.2)' },
          lineStyle: { color: '#4f46e5', width: 2 },
          itemStyle: { color: '#4f46e5' },
        },
        ...(deptValues.length ? [{
          value: deptValues,
          name: '部门平均',
          areaStyle: { color: 'rgba(16,185,129,0.1)' },
          lineStyle: { color: '#10b981', width: 2, type: 'dashed' },
          itemStyle: { color: '#10b981' },
        }] : []),
      ],
    }],
  }
})

function onDeptChange() {
  const dept = currentDept.value
  deptEmployees.value = dept?.employees || []
  // Preserve selected employee if they're still in the new department
  if (selectedEmp.value && !deptEmployees.value.find(e => e.employee_id === selectedEmp.value.employee_id)) {
    selectedEmp.value = deptEmployees.value[0] || null
  } else if (deptEmployees.value.length > 0 && !selectedEmp.value) {
    selectedEmp.value = deptEmployees.value[0]
  }
}

// Auto-select first department on load
watch(departments, (list) => {
  if (list.length > 0 && !selectedDept.value) {
    selectedDept.value = list[0].department
  }
}, { immediate: false })

async function loadData() {
  try {
    const data = await fetchTalentAnalysis()
    departments.value = data.departments || []
  } catch (err) {
    console.error('加载人才分析数据失败:', err)
  }
}

onMounted(() => { loadData(); timer = setInterval(loadData, 30000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.talent-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 面板头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}
.dept-select {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 32px 8px 12px;
  font-size: 13px;
  color: #1f2937;
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  transition: border-color 0.2s;
}
.dept-select:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

/* 部门综合评分概览 */
.dept-overview-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  display: flex;
  gap: 24px;
  align-items: center;
}
.dept-score-main {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.score-ring {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: 4px solid #4f46e5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  flex-shrink: 0;
}
.score-info {
  display: flex;
  flex-direction: column;
}
.dept-grade {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}
.dept-rank-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}
.dept-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  margin-top: 4px;
}
.dept-dimensions {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dim-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dim-label {
  font-size: 11px;
  color: #6b7280;
  width: 56px;
  text-align: right;
  flex-shrink: 0;
}
.dim-bar-bg {
  flex: 1;
  height: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
}
.dim-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}
.dim-value {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  width: 28px;
  text-align: right;
  flex-shrink: 0;
}

/* 图表卡片 */
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.chart-card.full-width {
  grid-column: 1 / -1;
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.chart-header h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0;
}
.badge {
  font-size: 11px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 3px 10px;
  border-radius: 10px;
}
.radar-chart {
  height: 300px;
  width: 100%;
}
.radar-chart-sm {
  height: 260px;
  width: 100%;
}

/* 员工区域 */
.employee-section {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.emp-layout {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 16px;
}

.emp-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 340px;
  overflow-y: auto;
  padding-right: 4px;
}
.emp-list::-webkit-scrollbar {
  width: 4px;
}
.emp-list::-webkit-scrollbar-thumb {
  background: #e5e7eb;
  border-radius: 2px;
}

.emp-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
  border: 1px solid transparent;
}
.emp-item:hover {
  background: #f3f0ff;
  border-color: rgba(79, 70, 229, 0.15);
}
.emp-item.selected {
  background: #f0edff;
  border-color: #4f46e5;
  box-shadow: 0 1px 4px rgba(79, 70, 229, 0.15);
}

.emp-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.emp-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.emp-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}
.emp-pos {
  font-size: 11px;
  color: #9ca3af;
}
.emp-score {
  font-size: 14px;
  font-weight: 700;
  color: #4f46e5;
  background: rgba(79, 70, 229, 0.08);
  padding: 2px 10px;
  border-radius: 8px;
}

.emp-radar-wrap {
  background: #fafafa;
  border-radius: 10px;
  padding: 14px;
}

/* 员工维度详情标签 */
.emp-dim-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.dim-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #fff;
  border-radius: 6px;
  border-left: 3px solid #4f46e5;
  font-size: 11px;
}
.dim-tag-label {
  color: #6b7280;
}
.dim-tag-value {
  font-weight: 700;
  color: #1f2937;
}

/* 排名表 */
.table-wrapper {
  overflow-x: auto;
}
.rank-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.rank-table th {
  background: #f8fafc;
  color: #374151;
  font-weight: 600;
  padding: 10px 8px;
  text-align: center;
  border-bottom: 2px solid #e5e7eb;
  white-space: nowrap;
}
.rank-table td {
  padding: 9px 8px;
  text-align: center;
  border-bottom: 1px solid #f3f4f6;
  color: #1f2937;
}
.rank-table tbody tr:hover {
  background: #f9fafb;
}
.rank-table tbody tr.highlight {
  background: rgba(79, 70, 229, 0.05);
}
.rank-cell {
  font-weight: 700;
  color: #4f46e5;
}
.dept-cell {
  font-weight: 600;
  color: #1f2937;
}
.score-cell {
  font-weight: 700;
  color: #4f46e5;
}

/* 等级标签 */
.grade {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 8px;
  font-weight: 700;
  font-size: 11px;
}
.grade-s {
  background: #dcfce7;
  color: #16a34a;
}
.grade-a {
  background: #dbeafe;
  color: #2563eb;
}
.grade-b {
  background: #fef3c7;
  color: #d97706;
}
.grade-c {
  background: #fee2e2;
  color: #dc2626;
}

@media (max-width: 960px) {
  .dept-overview-card {
    flex-direction: column;
    align-items: stretch;
  }
  .dept-score-main {
    justify-content: center;
  }
  .emp-layout {
    grid-template-columns: 1fr;
  }
  .panel-header {
    flex-direction: column;
    gap: 10px;
    align-items: stretch;
  }
  .dept-select {
    width: 100%;
  }
}
</style>
