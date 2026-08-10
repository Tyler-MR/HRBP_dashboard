<template>
  <div class="app-shell">
    <!-- 顶部导航栏 -->
    <nav class="nav-bar">
      <router-link to="/" class="nav-logo">
        <span class="logo-icon">📊</span>
        <span class="logo-text">人力数据平台</span>
      </router-link>
      <div class="nav-links">
        <router-link to="/staff" class="nav-link" active-class="nav-active">
          📊 公司人力现状整体分析
        </router-link>
        <router-link to="/" class="nav-link" active-class="nav-active">
          📋 招聘数据看板
        </router-link>
        <router-link to="/efficiency" class="nav-link" active-class="nav-active">
          📈 公司人效数据看板
        </router-link>
        <router-link to="/dept-efficiency" class="nav-link" active-class="nav-active">
          🏢 部门人效看板
        </router-link>
      </div>
      <button class="sync-btn" @click="syncDingTalk" :disabled="syncing">
        {{ syncing ? '⏳ 同步中' : '🔄 同步钉钉' }}
      </button>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const syncing = ref(false)

async function syncDingTalk() {
  if (syncing.value) return
  syncing.value = true
  try {
    // 1. 同步花名册（员工数据）
    const res = await axios.post('/api/sync-roster', {}, { timeout: 120000 })
    const data = res.data
    let msg = data.synced
      ? `✅ 花名册同步成功: ${data.synced} 名员工`
      : `⚠️ ${data.message || data.error || '花名册同步未返回数据'}`

    // 2. 同步招聘数据（面试记录）
    try {
      const recRes = await axios.post('/api/sync-recruitment', {}, { timeout: 120000 })
      const recData = recRes.data
      if (recData.synced != null) {
        msg += `\n✅ 招聘数据同步成功: ${recData.synced} 条面试记录`
      } else if (recData.error) {
        msg += `\n⚠️ 招聘数据同步: ${recData.error}`
      }
    } catch (recErr) {
      const detail = recErr.response?.data?.detail || recErr.message
      msg += `\n⚠️ 招聘数据同步失败: ${detail}`
    }

    alert(msg)
    // 刷新当前页面
    window.location.reload()
  } catch (err) {
    const detail = err.response?.data?.detail || err.message
    alert(`❌ 同步失败: ${detail}`)
  } finally {
    syncing.value = false
  }
}
</script>

<style>
/* ===== 全局重置 ===== */
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f0f2f5;
  color: #1a1a2e;
}

/* ===== 导航栏 ===== */
.nav-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  position: sticky;
  top: 0;
  z-index: 100;
}
.nav-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
}
.logo-icon { font-size: 22px; }
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: #1a1a2e;
}
.nav-links {
  display: flex;
  gap: 4px;
}
.nav-link {
  padding: 8px 18px;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  color: #6b7280;
  transition: all 0.2s;
}
.nav-link:hover {
  background: #f3f4f6;
  color: #374151;
}
.nav-active {
  background: #4f46e5 !important;
  color: #fff !important;
  font-weight: 600;
}

/* 同步按钮 */
.sync-btn {
  padding: 6px 16px;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  background: transparent;
  color: #4f46e5;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.sync-btn:hover:not(:disabled) {
  background: #4f46e5;
  color: #fff;
}
.sync-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 主内容区 ===== */
.main-content {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 24px;
}
</style>
