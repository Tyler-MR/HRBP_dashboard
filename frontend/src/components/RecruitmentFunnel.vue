<template>
  <div class="funnel-wrap">
    <div class="cf-container">
      <div v-for="(s, i) in stages" :key="s.name" class="cf-row">
        <!-- 标签（左侧） -->
        <div class="cf-label-col">
          <span class="cf-stage-name">{{ s.name }}</span>
        </div>
        <!-- 圆柱（中间） -->
        <div class="cf-cylinder-col">
          <div class="cf-cylinder-track">
            <div
              class="cf-cylinder"
              :style="{
                width: cylinderWidth(i),
                background: cylinderGradient(i),
                boxShadow: `0 4px 14px ${COLORS[i]}44`,
              }"
            >
              <div class="cf-value-badge">{{ s.value }}</div>
            </div>
          </div>
        </div>
        <!-- 转化率（右侧） -->
        <div class="cf-rate-col">
          <span v-if="i > 0" class="cf-rate-pill">{{ s.rate }}%</span>
          <span v-else class="cf-rate-pill cf-base">基数</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  stages: { type: Array, default: () => [] },
})

const COLORS = [
  '#3B82F6',
  '#0EA5E9',
  '#06B6D4',
  '#14B8A6',
  '#10B981',
  '#34D399',
]

function cylinderWidth(idx) {
  const steps = props.stages.length
  const minPct = 30
  const maxPct = 98
  const w = maxPct - (idx / Math.max(steps - 1, 1)) * (maxPct - minPct)
  return `${w}%`
}

function cylinderGradient(idx) {
  return COLORS[idx % COLORS.length]
}

</script>

<style scoped>
.funnel-wrap {
  background: #fff;
  border-radius: 12px;
  padding: 8px 0;
}

.cf-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 12px 20px;
}

.cf-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

/* 左侧标签 */
.cf-label-col {
  width: 72px;
  flex-shrink: 0;
  text-align: right;
}
.cf-stage-name {
  font-size: 13px;
  font-weight: 700;
  color: #1a1a2e;
  white-space: nowrap;
}

/* 圆柱轨道 */
.cf-cylinder-col {
  flex: 1;
  min-width: 0;
}
.cf-cylinder-track {
  width: 100%;
  display: flex;
  align-items: center;
}

.cf-cylinder {
  height: 44px;
  border-radius: 22px;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 16px;
  transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  min-width: 60px;
}

/* 数值徽章 */
.cf-value-badge {
  position: relative;
  z-index: 1;
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0,0,0,0.25);
  letter-spacing: 0.5px;
}

.cf-value-badge::after {
  content: '人';
  font-size: 10px;
  font-weight: 500;
  opacity: 0.8;
  margin-left: 2px;
}

/* 右侧转化率 */
.cf-rate-col {
  width: 56px;
  flex-shrink: 0;
  text-align: left;
}
.cf-rate-pill {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  color: #059669;
  background: #ecfdf5;
  padding: 3px 10px;
  border-radius: 20px;
  white-space: nowrap;
}
.cf-rate-pill.cf-base {
  color: #6b7280;
  background: #f3f4f6;
  font-weight: 500;
}
</style>
