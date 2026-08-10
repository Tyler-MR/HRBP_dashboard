<template>
  <div class="table-wrapper">
    <table class="pos-table" v-if="positions.length">
      <thead>
        <tr>
          <th>招聘岗位</th>
          <th>需求部门</th>
          <th>编制</th>
          <th>到面</th>
          <th>初试</th>
          <th>复试</th>
          <th>复试通过率</th>
          <th>offer接受</th>
          <th>offer接受率</th>
          <th>试岗</th>
          <th>入职</th>
          <th>入职率</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pos in positions" :key="pos.id">
          <td class="cell-name">{{ pos.name }}</td>
          <td>{{ pos.department }}</td>
          <td class="cell-num">{{ pos.headcount }}</td>
          <td class="cell-num">{{ pos.到面 }}</td>
          <td class="cell-num">{{ pos.初试 }}</td>
          <td class="cell-num">{{ pos.复试 }}</td>
          <td class="cell-num">
            <span v-if="pos.到面 > 0" class="rate-cell"
                  :class="rateClass(pos.复试通过率)">{{ pos.复试通过率 }}%</span>
            <span v-else class="rate-null">--</span>
          </td>
          <td class="cell-num">{{ pos.offer接受 }}</td>
          <td class="cell-num">
            <span v-if="pos.到面 > 0" class="rate-cell"
                  :class="rateClass(pos.offer接受率)">{{ pos.offer接受率 }}%</span>
            <span v-else class="rate-null">--</span>
          </td>
          <td class="cell-num">{{ pos.试岗 }}</td>
          <td class="cell-num">{{ pos.入职 }}</td>
          <td class="cell-num">
            <span v-if="pos.offer接受 > 0" class="rate-cell"
                  :class="rateClass(pos.入职率)">{{ pos.入职率 }}%</span>
            <span v-else class="rate-null">--</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">暂无岗位数据</div>
  </div>
</template>

<script setup>
defineProps({
  positions: { type: Array, default: () => [] },
})

function passRateTooltip(pos) {
  return pos.到面 > 0
}
function rateClass(rate) {
  if (rate >= 80) return 'rate-high'
  if (rate >= 50) return 'rate-mid'
  return 'rate-low'
}
</script>

<style scoped>
.table-wrapper { overflow-x: auto; }
.pos-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
  min-width: 1100px;
}
.pos-table th {
  background: #f8fafc; padding: 8px 8px; text-align: center;
  font-weight: 600; color: #555; font-size: 11px;
  border-bottom: 2px solid #e2e8f0; white-space: nowrap;
}
.pos-table th:first-child, .pos-table td:first-child { text-align: left; padding-left: 12px; }
.pos-table td { padding: 7px 8px; border-bottom: 1px solid #f1f5f9; text-align: center; }
.pos-table tbody tr:hover { background: #f8fafc; }
.group-header {
  background: #eef2ff !important; color: #4f46e5 !important;
  font-size: 11px !important; border-bottom: none !important;
}
.cell-name { font-weight: 600; color: #1a1a2e; text-align: left !important; white-space: nowrap; }
.cell-num { font-weight: 600; color: #374151; }
.rate-cell {
  display: inline-block; padding: 1px 8px; border-radius: 8px;
  font-size: 11px; font-weight: 700;
}
.rate-high { background: #d1fae5; color: #059669; }
.rate-mid { background: #fef3c7; color: #d97706; }
.rate-low { background: #fee2e2; color: #dc2626; }
.rate-null { color: #d1d5db; }
.empty { text-align: center; padding: 40px; color: #999; }
</style>
