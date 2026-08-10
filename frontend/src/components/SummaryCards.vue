<template>
  <div class="summary-grid">
    <div class="summary-card" v-for="item in cardList" :key="item.key">
      <div class="card-icon" :style="{ background: item.bg }">{{ item.icon }}</div>
      <div class="card-body">
        <div class="card-value">{{ data[item.key] ?? 0 }}</div>
        <div class="card-label">{{ item.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  data: { type: Object, default: () => ({}) },
})

const cardList = [
  { key: 'total_interviews', label: '到面量', icon: '👤', bg: '#dbeafe' },
  { key: 'first_round_passes', label: '初试通过', icon: '✅', bg: '#d1fae5' },
  { key: 'second_round_passes', label: '复试通过', icon: '🏆', bg: '#ede9fe' },
  { key: 'offers_accepted', label: 'Offer接收', icon: '👍', bg: '#ccfbf1' },
  { key: 'onboarded', label: '到岗人数', icon: '🎉', bg: '#fef9c3' },
  { key: 'retention_7day', label: '满7天', icon: '💪', bg: '#e0e7ff' },
]
</script>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.summary-card {
  display: flex; align-items: center; gap: 10px;
  background: #fff; border-radius: 10px;
  padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  transition: transform 0.15s;
}
.summary-card:hover { transform: translateY(-2px); }
.card-icon {
  width: 40px; height: 40px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.card-body { min-width: 0; }
.card-value { font-size: 20px; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.card-label { font-size: 11px; color: #888; white-space: nowrap; }
</style>
