<template>
  <div class="card">
    <div class="card-header">
      <h2>📊 招聘达成进度一览</h2>
      <span class="badge">{{ monthLabel }} 目标 vs 实际</span>
    </div>

    <!-- 达成率卡片 -->
    <div class="rate-bar-wrapper" v-if="summary">
      <div class="rate-card">
        <span class="rate-label">面试通过达成率</span>
        <span class="rate-value" :class="rateClass(summary.interview_rate)">{{ summary.interview_rate }}%</span>
        <div class="rate-track">
          <div class="rate-fill" :style="{ width: Math.min(summary.interview_rate, 100) + '%' }"></div>
        </div>
        <span class="rate-detail">{{ summary.actual_interview }}/{{ summary.target_interview }}</span>
      </div>
      <div class="rate-card">
        <span class="rate-label">试岗达成率</span>
        <span class="rate-value" :class="rateClass(summary.probation_rate)">{{ summary.probation_rate }}%</span>
        <div class="rate-track">
          <div class="rate-fill fill-green" :style="{ width: Math.min(summary.probation_rate, 100) + '%' }"></div>
        </div>
        <span class="rate-detail">{{ summary.actual_probation }}/{{ summary.target_onboarding }}</span>
      </div>
    </div>

    <div class="table-wrapper">
      <table class="progress-table" v-if="activeItems.length">
        <thead>
          <tr>
            <th>部门</th>
            <th>需求岗位</th>
            <th>目标面试通过</th>
            <th>实际面试通过</th>
            <th>目标到岗</th>
            <th>实际试岗</th>
            <th>试岗中</th>
            <th>满7天留存</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in activeItems" :key="idx">
            <td v-if="isDeptStart(idx)" class="cell-dept" :rowspan="deptSpan(idx)">{{ item.department }}</td>
            <td class="cell-pos">{{ item.position }}</td>
            <td class="cell-num">{{ item.target_interview }}</td>
            <td class="cell-num" :class="highlight(item.actual_interview, item.target_interview)">{{ item.actual_interview }}</td>
            <td class="cell-num">{{ item.target_onboarding }}</td>
            <td class="cell-num" :class="highlight(item.actual_probation, item.target_onboarding)">
              {{ item.actual_probation }}
              <span v-if="item.names" class="names">({{ item.names }})</span>
            </td>
            <td class="cell-num">{{ item.probationing }}</td>
            <td class="cell-num">{{ item.retention_7day }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">暂无数据</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  summary: { type: Object, default: null },
})

// 月份标签：优先用传入的 month（YYYY-MM），否则默认当前月
const monthLabel = computed(() => {
  const m = props.month
  if (m && /^\d{4}-\d{2}$/.test(m)) {
    const [y, mm] = m.split('-')
    return `${y}年${Number(mm)}月`
  }
  const now = new Date()
  return `${now.getFullYear()}年${now.getMonth() + 1}月`
})

// 过滤掉取消招聘的行
const activeItems = computed(() => props.items.filter(i => !i.cancelled))

// 计算每个部门的合并行数
const deptGroups = computed(() => {
  const map = {}
  activeItems.value.forEach((item) => {
    if (!item.department) return
    if (!map[item.department]) map[item.department] = 0
    map[item.department]++
  })
  return map
})

function isDeptStart(idx) {
  if (idx === 0) return true
  return activeItems.value[idx].department !== activeItems.value[idx - 1].department
}

function deptSpan(idx) {
  const dept = activeItems.value[idx].department
  if (!dept) return 1
  return deptGroups.value[dept] || 1
}

function highlight(actual, target) {
  if (target === 0) return ''
  return actual >= target ? 'cell-high' : 'cell-low'
}
function rateClass(rate) {
  if (rate >= 80) return 'rate-green'
  if (rate >= 50) return 'rate-yellow'
  return 'rate-red'
}
</script>

<style scoped>
.card {
  background: #fff; border-radius: 12px;
  padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  margin-bottom: 16px;
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

/* 达成率 */
.rate-bar-wrapper {
  display: flex; gap: 24px; margin-bottom: 16px;
  padding: 14px 16px; background: #f8fafc; border-radius: 8px;
}
.rate-card { flex: 1; }
.rate-label { font-size: 12px; color: #6b7280; display: block; }
.rate-value { font-size: 22px; font-weight: 700; margin: 2px 0; display: block; }
.rate-green { color: #059669; }
.rate-yellow { color: #d97706; }
.rate-red { color: #dc2626; }
.rate-track {
  height: 6px; background: #e5e7eb; border-radius: 3px; margin: 4px 0;
}
.rate-fill {
  height: 100%; background: linear-gradient(90deg, #3b82f6, #2563eb);
  border-radius: 3px; transition: width 0.6s;
}
.fill-green { background: linear-gradient(90deg, #10b981, #059669); }
.rate-detail { font-size: 11px; color: #9ca3af; }

.table-wrapper { overflow-x: auto; }
.progress-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
  min-width: 800px;
}
.progress-table th {
  background: #eef2ff; padding: 8px 10px; text-align: center;
  font-weight: 600; color: #4338ca; font-size: 11px;
  border-bottom: 2px solid #c7d2fe; white-space: nowrap;
}
.progress-table th:first-child,
.progress-table td:first-child { text-align: left; padding-left: 12px; }
.progress-table td {
  padding: 7px 10px; border-bottom: 1px solid #f1f5f9;
  text-align: center;
}
.progress-table tbody tr:hover { background: #f8fafc; }
.cell-dept { font-weight: 600; color: #1a1a2e; white-space: nowrap; }
.cell-pos { color: #374151; text-align: center !important; }
.cell-num { font-weight: 600; color: #374151; }
.cell-high { color: #059669; }
.cell-low { color: #dc2626; }
.names { font-size: 10px; color: #6b7280; font-weight: 400; }
.empty { text-align: center; padding: 40px; color: #999; }
</style>
