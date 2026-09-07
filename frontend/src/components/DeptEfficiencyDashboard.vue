<template>
  <div class="dept-eff">
    <header class="page-header">
      <h1><i class="ic ic-chart"></i> 部门人效看板</h1>
      <span class="update-tag">每日 00:05 自动更新 · 支持手动同步</span>
      <label class="month-label"><i class="ic ic-cal"></i>
        <input type="month" v-model="month" @change="loadData()" class="month-picker" />
      </label>
      <span class="update-time"><i class="ic ic-clock"></i> {{ updatedAt }}</span>
      <button class="refresh-btn" @click="syncData" :disabled="loading" title="立即同步钉钉产品/设计/拼多多打品数据">
        <i class="ic ic-refresh"></i>{{ loading ? ' 同步中' : ' 同步' }}
      </button>
    </header>

    <!-- 部门选择 -->
    <div class="dept-tabs">
      <button v-for="d in departments" :key="d.department"
              :class="['dept-tab', { active: current === d.department }]"
              @click="current = d.department">
        {{ d.department }}
        <span class="tab-score">{{ d.score }}</span>
      </button>
    </div>

    <!-- 加载中提示（首次拉取外部数据源较慢，避免误以为白屏） -->
    <div v-if="loading && !departments.length" class="loading-tip">
      <span class="spinner"></span> 数据加载中，请稍候…
    </div>

    <div v-if="!loading && !departments.length" class="loading-tip">暂无数据，请点击刷新或检查数据源</div>

    <div v-if="activeDept" class="dept-detail">
      <!-- 团队概况 -->
      <div class="dept-head">
        <div class="dept-title">{{ activeDept.department }}
          <span v-if="activeDept.source" class="src-tag"><i class="ic ic-link"></i> {{ srcLabel(activeDept.source) }}</span>
        </div>
        <div class="dept-meta">
          <span class="meta-tag"><i class="ic ic-users"></i> {{ activeDept.team_size }}人</span>
          <span class="meta-tag score-tag"><i class="ic ic-star"></i> 综合评分 {{ activeDept.score ?? '—' }}</span>
        </div>
      </div>

      <div v-if="activeDept.source_error" class="source-error">
        <i class="ic ic-alert"></i> 数据源连接失败，已自动重试 3 次仍未成功。为避免展示虚假数据，本部门指标与成员暂不显示，请检查数据源后点击刷新。
      </div>

      <!-- 团队指标：产品团队按维度分两行（产品部/设计部），其余部门沿用原网格 -->
      <div v-if="isGroupedDept" class="dimension-rows">
        <div class="dimension-row" v-for="g in metricGroups" :key="g.group">
          <div class="dimension-label">{{ g.group }}</div>
          <div class="dimension-cards">
            <div class="metric-card" v-for="m in g.metrics" :key="m.name">
              <div class="metric-ring">
                <svg viewBox="0 0 120 120" class="ring-svg">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="#f0f0f0" stroke-width="10"/>
                  <circle cx="60" cy="60" r="50" fill="none" :stroke="ringColor(m)" stroke-width="10"
                          :stroke-dasharray="circ" :stroke-dashoffset="ringOff(m)"
                          stroke-linecap="round" transform="rotate(-90,60,60)"/>
                </svg>
                <div class="ring-center">
                  <div class="ring-val">{{ fmt(m) }}</div>
                  <div class="ring-unit">{{ m.unit }}</div>
                </div>
              </div>
              <div class="metric-info">
                <div class="metric-name">{{ m.name }}</div>
                <div class="metric-target" v-if="m.target">目标 {{ m.target }}{{ m.unit }}</div>
                <div class="metric-trend" :class="'t-'+m.trend">{{ trendLbl(m.trend) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="activeDept.metrics.length" class="metrics-grid">
        <div class="metric-card" v-for="m in activeDept.metrics" :key="m.name">
          <div class="metric-ring">
            <svg viewBox="0 0 120 120" class="ring-svg">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#f0f0f0" stroke-width="10"/>
              <circle cx="60" cy="60" r="50" fill="none" :stroke="ringColor(m)" stroke-width="10"
                      :stroke-dasharray="circ" :stroke-dashoffset="ringOff(m)"
                      stroke-linecap="round" transform="rotate(-90,60,60)"/>
            </svg>
            <div class="ring-center">
              <div class="ring-val">{{ fmt(m) }}</div>
              <div class="ring-unit">{{ m.unit }}</div>
            </div>
          </div>
          <div class="metric-info">
            <div class="metric-name">{{ m.name }}</div>
            <div class="metric-target" v-if="m.target">目标 {{ m.target }}{{ m.unit }}</div>
            <div class="metric-trend" :class="'t-'+m.trend">{{ trendLbl(m.trend) }}</div>
          </div>
        </div>
      </div>

      <!-- 拼多多打品分析：钉钉 AI 多维表「拼多多打品成功率」 -->
      <section v-if="isPddDept && pddAnalysis" class="pdd-analysis-panel">
        <div class="pdd-analysis-head">
          <div>
            <div class="section-title pdd-section-title"><i class="ic ic-trend"></i> 拼多多打品成功率分析</div>
            <div class="pdd-analysis-subtitle">{{ pddAnalysis.period || month }} · {{ pddAnalysis.source_sheet }} · 每日 00:05 更新，可手动同步</div>
          </div>
          <span class="pdd-source-tag"><i class="ic ic-link"></i> 钉钉多维表</span>
        </div>
        <div v-if="pddAnalysis.source_error" class="pdd-analysis-error">
          <i class="ic ic-alert"></i> {{ pddAnalysis.source_error }}
        </div>
        <template v-else>
          <div class="pdd-view-title"><span class="pdd-step">1</span> 团队打品成功率与波动趋势</div>
          <div class="pdd-kpi-grid">
            <div class="pdd-kpi-card success-kpi">
              <span class="pdd-kpi-label">综合打品成功率</span>
              <strong>{{ Number(pddAnalysis.success_rate || 0).toFixed(1) }}</strong><em>%</em>
              <small>A款{{ Number(pddAnalysis.a_rate || 0).toFixed(1) }}%×60% + B款{{ Number(pddAnalysis.b_rate || 0).toFixed(1) }}%×40%</small>
            </div>
            <div class="pdd-kpi-card b-kpi">
              <span class="pdd-kpi-label">B款成功率</span>
              <strong>{{ Number(pddAnalysis.b_rate || 0).toFixed(1) }}</strong><em>%</em>
              <small>{{ pddAnalysis.b_count }} 个链接 · 日销 500 元+</small>
            </div>
            <div class="pdd-kpi-card a-kpi">
              <span class="pdd-kpi-label">A款成功率</span>
              <strong>{{ Number(pddAnalysis.a_rate || 0).toFixed(1) }}</strong><em>%</em>
              <small>{{ pddAnalysis.a_count }} 个链接 · 日销 1000 元+</small>
            </div>
            <div class="pdd-kpi-card efficiency-kpi">
              <span class="pdd-kpi-label">团队人效</span>
              <strong>{{ Number(pddAnalysis.team_person_efficiency || 0).toFixed(2) }}</strong><em>万元/人</em>
              <small>销售额 {{ Number(pddAnalysis.team_sales_revenue || 0).toFixed(2) }} 万元 · {{ pddAnalysis.team_size || 0 }}人</small>
            </div>
          </div>
          <div class="pdd-trend-summary" :class="{ 'trend-positive': pddAnalysis.trend_delta > 0, 'trend-negative': pddAnalysis.trend_delta < 0 }">
            <i class="ic ic-trend"></i>
            <span v-if="pddAnalysis.trend_delta !== null && pddAnalysis.trend_delta !== undefined">综合成功率较上一个有效月份{{ pddAnalysis.trend_delta > 0 ? '上升' : pddAnalysis.trend_delta < 0 ? '下降' : '持平' }} {{ pddAnalysis.trend_delta > 0 ? '+' : '' }}{{ Number(pddAnalysis.trend_delta).toFixed(1) }} 个百分点</span>
            <span v-else>当前仅有一个有效月份，暂无环比波动；后续按月沉淀趋势</span>
          </div>
          <div class="pdd-analysis-grid">
            <div class="pdd-trend-card">
              <div class="pdd-card-title">近 6 个月团队趋势（综合成功率 / A款 / B款）</div>
              <div v-if="pddAnalysis.trend.length" ref="pddTrendRef" class="pdd-trend-chart"></div>
              <div v-else class="pdd-empty">暂无趋势数据</div>
            </div>
          </div>

          <div class="pdd-owner-card">
            <div class="pdd-view-title"><span class="pdd-step">2</span> {{ pddAnalysis.period }} 运营打品与业绩综合排名</div>
            <div class="pdd-ranking-basis">{{ pddAnalysis.ranking_basis }}</div>
            <div v-if="pddAnalysis.owners.length" class="pdd-owner-table-wrap">
              <table class="pdd-owner-table">
                <thead>
                  <tr><th>排名</th><th>运营</th><th>打品质量</th><th>月销售额</th><th>利润率</th><th>ROI</th><th>综合分</th><th>状态</th></tr>
                </thead>
                <tbody>
                  <tr v-for="owner in pddAnalysis.owners" :key="owner.name" :class="{ 'pdd-owner-pending': !owner.product_data_available || !owner.performance_available }">
                    <td><span class="pdd-owner-rank">{{ owner.rank || '—' }}</span></td>
                    <td><div class="pdd-owner-person"><b>{{ owner.name }}</b><small>{{ owner.product_data_available ? `${owner.product_count}个产品` : '暂无打品记录' }}</small></div></td>
                    <td><b v-if="owner.product_data_available">{{ Number(owner.success_score || 0).toFixed(1) }}%</b><span v-else>—</span><small v-if="owner.product_data_available">A {{ Number(owner.a_rate || 0).toFixed(1) }}%（{{ owner.a_count }}个） · B {{ Number(owner.b_rate || 0).toFixed(1) }}%（{{ owner.b_count }}个）</small></td>
                    <td>{{ owner.performance_available ? `${Number(owner.sales_revenue || 0).toFixed(2)}万` : '—' }}</td>
                    <td :class="Number(owner.profit_margin) < 0 ? 'pdd-negative' : ''">{{ owner.performance_available ? `${Number(owner.profit_margin || 0).toFixed(2)}%` : '—' }}</td>
                    <td>{{ owner.performance_available ? Number(owner.roi || 0).toFixed(2) : '—' }}</td>
                    <td><b v-if="owner.rank">{{ Number(owner.combined_score || 0).toFixed(1) }}</b><span v-else>—</span></td>
                    <td><span class="pdd-owner-status" :class="owner.rank ? 'status-ranked' : 'status-pending'">{{ owner.rank ? '可排名' : (!owner.product_data_available ? '待补打品' : '待补业绩') }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="pdd-empty">当期暂无可按运营统计的记录</div>
          </div>

          <div v-if="pddAnalysis.report" class="pdd-report-card">
            <div class="pdd-view-title"><span class="pdd-step">3</span> 打品成功率 × 人效综合分析报告</div>
            <div class="pdd-report-headline">{{ pddAnalysis.report.headline }}</div>
            <p class="pdd-report-conclusion">{{ pddAnalysis.report.conclusion }}</p>
            <div class="pdd-report-grid">
              <div><div class="pdd-report-label">关键判断</div><ul><li v-for="item in pddAnalysis.report.highlights" :key="item">{{ item }}</li></ul></div>
              <div><div class="pdd-report-label">管理建议</div><ul><li v-for="item in pddAnalysis.report.actions" :key="item">{{ item }}</li></ul></div>
            </div>
          </div>

          <div v-if="pddAnalysis.supervisor_analysis" class="pdd-supervisor-card">
            <div class="pdd-view-title"><span class="pdd-step">4</span> 拼多多主管分析 vs AI分析</div>
            <div class="pdd-supervisor-meta">{{ pddAnalysis.supervisor_analysis.name }} · {{ pddAnalysis.supervisor_analysis.title }} · {{ pddAnalysis.supervisor_analysis.period }} · 来源：管理人员日报</div>
            <div v-if="pddAnalysis.supervisor_analysis.supervisor_brief" class="pdd-supervisor-brief">
              <div class="pdd-brief-head">
                <div class="pdd-supervisor-label">主管补充分析 · {{ pddAnalysis.supervisor_analysis.supervisor_brief.period }}</div>
                <span class="pdd-brief-source">主管提供</span>
              </div>
              <p class="pdd-brief-overall">{{ pddAnalysis.supervisor_analysis.supervisor_brief.overall }}</p>
              <div class="pdd-brief-grid">
                <div><div class="pdd-brief-label">人员判断</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.supervisor_brief.people" :key="item">{{ item }}</li></ul></div>
                <div><div class="pdd-brief-label">本月重点</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.supervisor_brief.focus" :key="item">{{ item }}</li></ul></div>
              </div>
              <div class="pdd-brief-compare"><div class="pdd-brief-label">这段文字与AI分析的差异</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.supervisor_brief.ai_comparison" :key="item">{{ item }}</li></ul></div>
            </div>
            <div v-if="pddAnalysis.supervisor_analysis.status === 'source_error'" class="pdd-analysis-error">
              <i class="ic ic-alert"></i> {{ pddAnalysis.supervisor_analysis.source_error }}
            </div>
            <template v-else>
              <div v-if="pddAnalysis.supervisor_analysis.status === 'no_data'" class="pdd-supervisor-empty">
                <b>当前周期暂无朱康的主管日报原文</b>
                <span>AI 分析仍基于钉钉打品数据和 MySQL 业绩数据生成，不能替代主管原文或主管判断。</span>
              </div>
              <div class="pdd-supervisor-columns">
                <div class="pdd-supervisor-block supervisor-block">
                  <div class="pdd-supervisor-label">主管分析（日志维度提炼）</div>
                  <div v-if="pddAnalysis.supervisor_analysis.status === 'available'" class="pdd-supervisor-covered">
                    已覆盖：{{ pddAnalysis.supervisor_analysis.covered_dimensions.join('、') || '暂无' }}
                    <span v-if="pddAnalysis.supervisor_analysis.missing_dimensions.length">；待补：{{ pddAnalysis.supervisor_analysis.missing_dimensions.join('、') }}</span>
                  </div>
                  <ul v-if="pddAnalysis.supervisor_analysis.supervisor_focus.length"><li v-for="item in pddAnalysis.supervisor_analysis.supervisor_focus" :key="item">{{ item }}</li></ul>
                  <span v-else class="pdd-supervisor-muted">暂无主管侧可提炼内容</span>
                </div>
                <div class="pdd-supervisor-block ai-block">
                  <div class="pdd-supervisor-label">AI分析（数据量化）</div>
                  <ul><li v-for="item in pddAnalysis.supervisor_analysis.ai_focus" :key="item">{{ item }}</li></ul>
                </div>
              </div>
              <div class="pdd-diff-grid">
                <div class="pdd-diff-block consensus-block"><div class="pdd-supervisor-label">一致判断</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.consensus" :key="item">{{ item }}</li></ul></div>
                <div class="pdd-diff-block difference-block"><div class="pdd-supervisor-label">核心差异点</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.differences" :key="item">{{ item }}</li></ul></div>
                <div class="pdd-diff-block"><div class="pdd-supervisor-label">主管独有信息</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.supervisor_only" :key="item">{{ item }}</li></ul></div>
                <div class="pdd-diff-block"><div class="pdd-supervisor-label">AI独有信息</div><ul><li v-for="item in pddAnalysis.supervisor_analysis.ai_only" :key="item">{{ item }}</li></ul></div>
              </div>
              <details v-if="pddAnalysis.supervisor_analysis.raw_text" class="pdd-supervisor-source">
                <summary>查看主管日报原文（{{ pddAnalysis.supervisor_analysis.log_count }}篇）</summary>
                <pre>{{ pddAnalysis.supervisor_analysis.raw_text }}</pre>
              </details>
              <div v-if="pddAnalysis.supervisor_analysis.conclusion" class="pdd-supervisor-conclusion"><b>对照结论：</b>{{ pddAnalysis.supervisor_analysis.conclusion }}</div>
            </template>
          </div>

          <div class="pdd-analysis-note">数据口径：团队成功率按钉钉多维表的 A/B 链接数 ÷ 产品数汇总重算；综合打品成功率 = A款60% + B款40%。运营综合排名 = 打品质量分50% + 月销售额指数50%；业绩列同步展示销售额、利润率和 ROI。无完整两类数据的运营保留展示但不纳入排名。</div>
        </template>
      </section>

      <!-- 部门雷达由员工个人评分逐维汇总（人力行政部按 招聘组/行政组 分两个雷达） -->
      <div class="section-title"><i class="ic ic-radar ic-indigo"></i> 人才雷达图 — 团队成员个人评分汇总</div>
      <div class="score-panel">
        <div class="radar-group" v-for="g in radarGroups" :key="g.group || 'default'">
          <div class="rg-title" v-if="g.group">{{ g.group }}</div>
          <div class="rg-body">
            <div :ref="el => setRadarRef(g.group || 'default', el)" class="rg-radar"></div>
            <div class="score-controls">
              <div class="sc-item" v-for="(e, idx) in g.items" :key="e.group + '|' + e.dimension">
                <div class="sc-dim">{{ e.dimension }}</div>
                <div class="sc-slider dept-score-progress"
                     role="progressbar"
                     :aria-valuenow="e.score"
                     aria-valuemin="0"
                     aria-valuemax="20"
                     :style="scoreProgressStyle(e.score, 20)"></div>
                <input type="number" class="sc-num" min="0" max="20" :value="e.score" readonly />
                <span class="sc-badge" :class="scBadge(e.score, 20)">{{ e.score }}</span>
              </div>
              <div class="sc-hint">部门分数 = 本部门员工个人雷达评分的逐维平均值；五维合计上限100分</div>
            </div>
          </div>
        </div>
        <div class="sc-hint" v-if="savedMsg">{{ savedMsg }}</div>
      </div>

      <!-- 成员人效 -->
      <div v-if="activeDept.members.length" class="section-title"><i class="ic ic-users"></i> 成员人效详情</div>
      <div v-if="activeDept.members.length" class="member-table-wrap">
        <table class="member-table">
          <thead>
            <tr>
              <th>姓名</th>
              <th>职位</th>
              <th>评分</th>
              <th>雷达评估维度</th>
              <th>关键指标</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(m, i) in sortedMembers" :key="m.name"
                :class="{ 'top-row': i === 0 }"
                @click="openDrawer(m)" style="cursor:pointer">
              <td class="m-name">{{ m.name }}</td>
              <td class="m-pos">{{ m.position }}</td>
              <td class="m-score">
                <span class="score-badge" :class="scoreClass(m.score, m.score_max)">{{ m.score }}<em class="sc-max">/{{ m.score_max }}</em></span>
              </td>
              <td class="m-radar-dims">
                <span class="mrd-chip" v-for="d in (memberRadarDims[m.name] || [])" :key="d.dimension"
                      :class="d.score > 0 ? 'mrd-scored' : 'mrd-empty'"
                      :title="d.standard || d.dimension">
                  <span class="mrd-dim">{{ d.dimension }}</span>
                  <em class="mrd-score">{{ d.score }}<i class="mrd-max">/{{ d.max }}</i></em>
                </span>
                <span v-if="!(memberRadarDims[m.name] || []).length" class="mrd-none">—</span>
              </td>
              <td class="m-metrics">
                <span class="mm-item" v-for="mt in m.metrics" :key="mt.name">
                  <span class="mm-label">{{ mt.name }}</span>
                  <span class="mm-val">{{ mt.value }}{{ mt.unit }}</span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 成员详情抽屉：点击成员行从右侧滑出（上半=每日产出图，下半=评估+雷达+评分） -->
    <transition name="drawer-fade">
      <div v-if="drawerOpen" class="drawer-mask" @click="closeDrawer"></div>
    </transition>
    <transition name="drawer-slide">
      <aside v-if="drawerOpen && drawerMember" class="member-drawer">
        <div class="drawer-header">
          <div class="drawer-title"><i class="ic ic-user"></i> {{ drawerMember.name }}（{{ drawerMember.position }}）</div>
          <button class="drawer-close" @click="closeDrawer">✕</button>
        </div>
        <div class="drawer-scroll">
          <!-- 上半部分：每日产出波动（真实数据） -->
          <div class="drawer-section">
            <div class="drawer-section-title"><i class="ic ic-trend"></i> {{ dailyData?.title || '每日产出' }}（{{ month }}）</div>
            <div v-if="dailyData?.series?.length" ref="dailyChartRef" class="daily-chart"></div>
            <div v-else class="daily-empty">当月暂无每日数据</div>
          </div>
          <!-- 下半部分：部门负责人评估（现有内容迁移） -->
          <div class="drawer-section">
            <div class="drawer-section-title"><i class="ic ic-doc"></i> {{ drawerMember.manager_evaluation ? '采购主管人员评价' : '部门负责人评估' }}</div>
            <div class="eval-box">
              <span class="eval-label"><i class="ic ic-doc"></i> {{ drawerMember.manager_evaluation ? '采购主管评价' : '部门负责人评估' }}</span>
              <span class="eval-text">{{ drawerMember.manager_evaluation || drawerMember.evaluation }}</span>
              <span v-if="drawerMember.manager_evaluation && drawerMember.evaluation" class="eval-meta">花名册信息：{{ drawerMember.evaluation }}</span>
            </div>
          </div>
          <!-- 下半部分：个人人才雷达图（左图右控件） -->
          <div class="member-radar-panel">
            <div class="mr-title"><i class="ic ic-radar"></i> {{ drawerMember.name }}（{{ drawerMember.position }}）个人人才雷达图</div>
            <div class="mr-body">
              <div ref="memberRadarRef" class="mr-radar-box"></div>
              <div class="mr-controls">
                <div class="sc-item" v-for="s in memberScores" :key="s.dimension">
                  <div class="sc-dim">
                    {{ s.dimension }}
                    <span v-if="s.standard" class="sc-std" :title="s.standard">ⓘ</span>
                  </div>
                  <input type="range" class="sc-slider" min="0" :max="s.max" step="1" v-model.number="s.score" @input="renderMemberRadar" />
                  <input type="number" class="sc-num" min="0" :max="s.max" v-model.number="s.score" @input="renderMemberRadar" />
                  <span class="sc-badge" :class="scBadge(s.score, s.max)">{{ s.score }}</span>
                </div>
                <div class="sc-actions">
                  <button class="sc-btn save" @click="saveMemberScores">💾 保存 {{ drawerMember.name }} 评分</button>
                </div>
                <div class="sc-hint" v-if="memberSavedAt">已保存于 {{ memberSavedAt }}</div>
                <div class="sc-hint" v-if="!memberAnyScored">🔵 尚未评分，拖动滑块为 {{ drawerMember.name }} 打分后保存</div>
              </div>
            </div>
            <div v-if="activeDept.department === '财务团队' && memberScores.some(s => s.standard)" class="mr-standards">
              <div class="mr-standards-title">岗位重点监控指标</div>
              <div class="mr-standard-list">
                <div v-for="s in memberScores" :key="`standard-${s.dimension}`" class="mr-standard-item">
                  <b>{{ s.dimension }}</b><span>{{ s.standard }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 90000 })
const loading = ref(false)
const updatedAt = ref('--')
const departments = ref([])
const current = ref('')
// 看板设定月份；首次打开留空，由后端按各真实数据源最新月份返回，避免新月份尚未沉淀数据时白屏
const month = ref('')
const radarRef = ref(null)
const circ = 2 * Math.PI * 50

const activeDept = computed(() => departments.value.find(d => d.department === current.value))
// 成员人效按贡献数值（评分）从高到低排列（评分动态变化，实时排序）
const sortedMembers = computed(() => {
  const members = activeDept.value?.members || []
  return [...members].sort((a, b) => (b.score || 0) - (a.score || 0))
})
// 拼多多团队：指标圆环深蓝填充（无目标值，按用户要求整环填充）
const isPddDept = computed(() => activeDept.value?.department === '拼多多团队')
const pddAnalysis = computed(() => activeDept.value?.pdd_product_analysis || null)
// 产品团队：指标带 group（产品部/设计部）→ 按维度分两行展示
const isGroupedDept = computed(() => activeDept.value?.metrics?.some(m => m.group) ?? false)
const metricGroups = computed(() => {
  if (!isGroupedDept.value) return []
  const groups = []
  const seen = []
  for (const m of activeDept.value.metrics) {
    const idx = seen.indexOf(m.group)
    if (idx === -1) {
      seen.push(m.group)
      groups.push({ group: m.group, metrics: [m] })
    } else {
      groups[idx].metrics.push(m)
    }
  }
  return groups
})
// 部门雷达图：支持分组（人力行政部=招聘组/行政组），每组独立 radar DOM + echarts 实例
const radarRefs = {}
const radarCharts = {}

// 可编辑的打分数据
let editScores = ref([])
const savedMsg = ref('')
let saveTimer = null
const expandedEval = ref(null)

// 按 group 分组（无 group 时单组，兼容原有部门）
const radarGroups = computed(() => {
  const map = {}
  editScores.value.forEach(s => { const g = s.group || ''; (map[g] = map[g] || []).push(s) })
  return Object.keys(map).map(g => ({ group: g, items: map[g] }))
})
function setRadarRef(group, el) {
  if (el) radarRefs[group] = el
  else delete radarRefs[group]
}
function disposeRadarCharts() {
  Object.values(radarCharts).forEach(c => { try { c.dispose() } catch (e) {} })
  for (const k of Object.keys(radarCharts)) delete radarCharts[k]
}

// 成员详情抽屉（点击成员行滑出）
const drawerOpen = ref(false)
const drawerMember = ref(null)
const dailyChartRef = ref(null)
let dailyChart = null
const dailyData = ref(null)
const pddTrendRef = ref(null)
let pddTrendChart = null

// 个人人才雷达图（每人独立打分入口；财务由后端按姓名匹配核算/经营报表/数据审核/发货/出纳岗位五维，未配置人员使用通用财务五维；其他部门沿用各自岗位维度）
const memberRadarRef = ref(null)
const memberScores = ref([])
const memberSavedAt = ref('')
let memberRadarChart = null
const memberAnyScored = computed(() => memberScores.value.some(s => s.score > 0))

function openDrawer(m) {
  drawerMember.value = m
  drawerOpen.value = true
  expandedEval.value = m  // 复用雷达图/评分绑定
  nextTick(async () => {
    await loadMemberRadar(m)
    await loadDaily(m)
  })
}

function closeDrawer() {
  drawerOpen.value = false
  drawerMember.value = null
  expandedEval.value = null
  memberScores.value = []
  memberSavedAt.value = ''
  if (dailyChart) { dailyChart.dispose(); dailyChart = null }
  dailyData.value = null
  if (memberRadarChart) { memberRadarChart.dispose(); memberRadarChart = null }
}

async function loadDaily(m) {
  try {
    const res = await api.get('/dept-efficiency/member-daily', {
      params: { department: activeDept.value.department, member: m.name, month: month.value },
    })
    dailyData.value = res.data?.series?.length ? res.data : null
    nextTick(renderDaily)
  } catch (e) {
    console.error(e)
    dailyData.value = null
  }
}

function renderDaily() {
  if (!dailyChartRef.value || !dailyData.value?.series?.length) return
  if (!dailyChart) dailyChart = echarts.init(dailyChartRef.value)
  const d = dailyData.value
  dailyChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: d.series.map(s => s.name), top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 36, right: 14, top: 28, bottom: 24 },
    xAxis: { type: 'category', data: d.days.map(x => x + '日'), axisLabel: { fontSize: 10, interval: 1 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: d.series.map(s => s.type === 'line'
      ? { name: s.name, type: 'line', smooth: true, data: s.data, lineStyle: { width: 2, color: '#059669' }, itemStyle: { color: '#059669' } }
      : { name: s.name, type: 'bar', barMaxWidth: 14, data: s.data, itemStyle: { color: '#4f46e5', borderRadius: [3, 3, 0, 0] } }),
  }, true)
  dailyChart.resize()
}

function renderPddTrend() {
  if (!pddTrendRef.value || !pddAnalysis.value?.trend?.length) return
  if (!pddTrendChart) pddTrendChart = echarts.init(pddTrendRef.value)
  const trend = pddAnalysis.value.trend
  pddTrendChart.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: value => `${Number(value).toFixed(1)}%`,
    },
    legend: { data: ['综合打品成功率', 'A款成功率', 'B款成功率'], top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 38, right: 14, top: 30, bottom: 26 },
    xAxis: { type: 'category', data: trend.map(item => item.month), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', min: 0, max: 100, interval: 20, axisLabel: { fontSize: 10, formatter: '{value}%' } },
    series: [
      { name: '综合打品成功率', type: 'line', smooth: true, data: trend.map(item => item.success_rate), lineStyle: { width: 3, color: '#1e3a8a' }, itemStyle: { color: '#1e3a8a' }, areaStyle: { color: 'rgba(30,58,138,0.10)' } },
      { name: 'B款成功率', type: 'line', smooth: true, data: trend.map(item => item.b_rate), lineStyle: { width: 2, color: '#2563eb' }, itemStyle: { color: '#2563eb' }, areaStyle: { color: 'rgba(37,99,235,0.08)' } },
      { name: 'A款成功率', type: 'line', smooth: true, data: trend.map(item => item.a_rate), lineStyle: { width: 2, color: '#059669' }, itemStyle: { color: '#059669' } },
    ],
  }, true)
  pddTrendChart.resize()
}

async function loadMemberRadar(m) {
  try {
    const res = await api.get('/member-radar', { params: { department: activeDept.value.department } })
    const item = res.data.items.find(x => x.name === m.name)
    // 维度/满分/评分标准以后端返回为准（成员维度=该成员所属组/岗位，统一20分制）
    const dimsMap = Object.fromEntries((res.data.dims || []).map(d => [d.dimension, d]))
    const keys = Object.keys(item?.scores ?? [])
    memberScores.value = keys.map(dim => ({
      dimension: dim,
      max: dimsMap[dim]?.max || 20,
      standard: dimsMap[dim]?.standard || '',
      score: item?.scores?.[dim] ?? 0,
    }))
    memberSavedAt.value = item?.updated_at || ''
  } catch (e) {
    memberScores.value = []
    memberSavedAt.value = ''
  }
  nextTick(renderMemberRadar)
}

// ── 雷达图统一美化（accent 主色 hex，部门=#4f46e5 / 个人=#059669）──
function radarOption(sub, accent, chartName, defaultMax = 20) {
  const rgba = (h, a) => {
    const n = parseInt(h.slice(1), 16)
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
  }
  return {
    tooltip: { trigger: 'item' },
    radar: {
      indicator: sub.map(e => ({ name: e.dimension, max: e.max || defaultMax })),
      shape: 'circle',
      center: ['50%', '50%'],
      radius: '66%',
      splitNumber: 4,
      name: { textStyle: { color: '#374151', fontSize: 12, fontWeight: 600 } },
      axisLine: { lineStyle: { color: rgba(accent, 0.18) } },
      splitLine: { lineStyle: { color: rgba(accent, 0.22), type: 'dashed' } },
      splitArea: {
        areaStyle: { color: [0.05, 0.10, 0.16, 0.22].map(a => rgba(accent, a)) },
      },
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: { color: accent, borderColor: '#fff', borderWidth: 2, shadowBlur: 12, shadowColor: rgba(accent, 0.4) },
      lineStyle: { color: accent, width: 2.5 },
      areaStyle: { color: rgba(accent, 0.16) },
      data: [{ value: sub.map(e => e.score), name: chartName }],
    }],
  }
}

function renderMemberRadar() {
  if (!memberRadarRef.value || !memberScores.value.length) return
  if (!memberRadarChart) memberRadarChart = echarts.init(memberRadarRef.value)
  memberRadarChart.setOption(radarOption(memberScores.value, '#059669', expandedEval.value?.name || ''), true)
  memberRadarChart.resize()
}

async function saveMemberScores() {
  if (!expandedEval.value) return
  const scores = {}
  memberScores.value.forEach(s => { scores[s.dimension] = s.score })
  try {
    const res = await api.put('/member-radar', {
      department: activeDept.value.department,
      member: expandedEval.value.name,
      position: expandedEval.value.position || '',
      scores,
    })
    memberSavedAt.value = res.data.updated_at
  } catch (e) { console.error(e) }
}

watch(activeDept, (dept) => {
  if (dept?.subjective) {
    editScores.value = dept.subjective.map(s => ({ ...s }))
    savedMsg.value = ''
  }
  expandedEval.value = null
  memberScores.value = []
  memberSavedAt.value = ''
  disposeRadarCharts()
  if (memberRadarChart) { memberRadarChart.dispose(); memberRadarChart = null }
  if (drawerOpen.value) closeDrawer()  // 切换部门时关闭成员抽屉
  nextTick(() => { renderRadar(); renderPddTrend() })
}, { deep: true, immediate: false })

watch(pddAnalysis, () => nextTick(renderPddTrend), { deep: true })

function ringColor(m) {
  // 统一翠绿：所有部门圆环与采购人效一致（原按达成率分档：≥90%绿/≥70%蓝/≥50%橙/<50%红、拼多多深蓝）
  return '#059669'
}
function ringOff(m) {
  if (!m.target || isPddDept.value) return 0
  const p = Math.min(m.value / m.target, 1)
  return circ * (1 - p)
}
function fmt(m) {
  return m.value >= 1000 ? (m.value / 1000).toFixed(1) + 'k' : m.value.toFixed(m.value % 1 === 0 ? 0 : 1)
}
function trendLbl(t) { return { up: '↑ 上升', down: '↓ 下降', stable: '→ 持平' }[t] || '' }
function srcLabel(s) { return { mysql: 'MySQL 实时', pdd: 'MySQL 实时', dingtalk: '钉钉多维表 每日更新' }[s] || (s + ' 实时') }
function subjColor(s) { return s >= 80 ? '#059669' : s >= 60 ? '#d97706' : '#dc2626' }
function scoreClass(s, max = 100) { const p = max ? s / max : 0; return p >= 0.9 ? 'sc-a' : p >= 0.7 ? 'sc-b' : p >= 0.5 ? 'sc-c' : 'sc-d' }
function scBadge(s, max = 20) { return s / max >= 0.8 ? 'badge-green' : s / max >= 0.6 ? 'badge-amber' : 'badge-red' }
function scoreProgressStyle(s, max = 20) {
  const score = Number(s) || 0
  const pct = Math.max(0, Math.min(100, (score / max) * 100))
  return { '--progress-width': `${pct}%` }
}

function saveScores() {
  savedMsg.value = '✅ 评分已保存（演示模式）'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { savedMsg.value = '' }, 3000)
}
function resetScores() {
  if (activeDept.value?.subjective) {
    editScores.value = activeDept.value.subjective.map(s => ({ ...s }))
    renderRadar()
  }
}

function renderRadar() {
  radarGroups.value.forEach(g => {
    const key = g.group || 'default'
    const el = radarRefs[key]
    if (!el || !g.items.length) return
    if (!radarCharts[key]) radarCharts[key] = echarts.init(el)
    const name = activeDept.value.department + (g.group ? ' · ' + g.group : '')
    radarCharts[key].setOption(radarOption(g.items, '#4f46e5', name), true)
    radarCharts[key].resize()
  })
}

watch(activeDept, () => { nextTick(renderRadar) }, { deep: true })

// 成员表格雷达评估维度（每人 5 维 + 已评分数 + 评分标准，来自 /member-radar）
const memberRadarDims = ref({})

async function loadMemberRadarDims() {
  const deptName = activeDept.value?.department
  if (!deptName) return
  try {
    const res = await api.get('/member-radar', { params: { department: deptName } })
    const dimsMap = Object.fromEntries((res.data.dims || []).map(d => [d.dimension, d]))
    const map = {}
    for (const it of res.data.items || []) {
      map[it.name] = Object.keys(it.scores || {}).map(dim => ({
        dimension: dim,
        max: dimsMap[dim]?.max || 20,
        standard: dimsMap[dim]?.standard || '',
        score: it.scores?.[dim] ?? 0,
      }))
    }
    memberRadarDims.value = map
  } catch (e) {
    console.error(e)
    memberRadarDims.value = {}
  }
}

function applyDeptData(data) {
  departments.value = data.items || []
  updatedAt.value = data.updated_at
  const latestPddPeriod = departments.value.find(d => d.department === '拼多多团队')?.pdd_product_analysis?.period
  if (!month.value && latestPddPeriod) month.value = latestPddPeriod
  if (!current.value && departments.value.length) current.value = departments.value[0].department
}

async function loadData() {
  loading.value = true
  try {
    const res = await api.get('/dept-efficiency', { params: { month: month.value } })
    applyDeptData(res.data)
  } catch (e) { console.error(e) } finally { loading.value = false }
}

async function syncData() {
  loading.value = true
  try {
    const res = await api.post('/sync-dept-efficiency', null, {
      params: { month: month.value },
      timeout: 120000,
    })
    if (res.data.sync && !res.data.sync.ok) {
      console.error(res.data.sync.message)
      return
    }
    applyDeptData(res.data)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 切换部门/加载数据后刷新成员雷达维度列
watch(activeDept, () => { nextTick(loadMemberRadarDims) }, { deep: true })
const handleResize = () => { Object.values(radarCharts).forEach(c => c?.resize()); memberRadarChart?.resize(); dailyChart?.resize(); pddTrendChart?.resize() }
onMounted(() => { loadData(); window.addEventListener('resize', handleResize) })
onUnmounted(() => { window.removeEventListener('resize', handleResize); pddTrendChart?.dispose() })
</script>

<style scoped>
.dept-eff { max-width: 1200px; margin: 0 auto; padding: 0; }
.page-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #e8e8e8; }
.page-header h1 { font-size: 20px; font-weight: 700; margin-right: 4px; }
.update-tag { font-size: 11px; background: #4f46e5; color: #fff; padding: 2px 10px; border-radius: 10px; }
.update-time { font-size: 13px; color: #888; margin-left: auto; }
.month-label { font-size: 12px; color: #555; display: flex; align-items: center; gap: 4px; }
.month-picker { padding: 3px 6px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 12px; color: #374151; background: #fff; cursor: pointer; }
.loading-tip { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 60px 0; color: #6b7280; font-size: 14px; }
.loading-tip .spinner { width: 18px; height: 18px; border: 3px solid #e0e7ff; border-top-color: #4f46e5; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.month-picker:focus { border-color: #4f46e5; outline: none; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
.refresh-btn { padding: 5px 12px; border: none; border-radius: 6px; background: #4f46e5; color: #fff; font-size: 13px; cursor: pointer; }
/* ── 彩色图标（SVG mask，颜色跟随主题：靛蓝主色/翠绿/琥珀/蓝）── */
.ic { display: inline-block; width: 1em; height: 1em; vertical-align: -0.18em; background: currentColor; -webkit-mask: var(--ic) center / contain no-repeat; mask: var(--ic) center / contain no-repeat; }
.ic-chart  { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='18' y1='20' x2='18' y2='10'/%3E%3Cline x1='12' y1='20' x2='12' y2='4'/%3E%3Cline x1='6' y1='20' x2='6' y2='14'/%3E%3C/svg%3E"); color: #4f46e5; }
.ic-cal     { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='18' rx='2' ry='2'/%3E%3Cline x1='16' y1='2' x2='16' y2='6'/%3E%3Cline x1='8' y1='2' x2='8' y2='6'/%3E%3Cline x1='3' y1='10' x2='21' y2='10'/%3E%3C/svg%3E"); color: #4f46e5; }
.ic-clock   { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpolyline points='12 6 12 12 16 14'/%3E%3C/svg%3E"); color: #6b7280; }
.ic-refresh { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='23 4 23 10 17 10'/%3E%3Cpath d='M20.49 15a9 9 0 1 1-2.12-9.36L23 10'/%3E%3C/svg%3E"); color: #fff; }
.ic-users   { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2'/%3E%3Ccircle cx='9' cy='7' r='4'/%3E%3Cpath d='M23 21v-2a4 4 0 0 0-3-3.87'/%3E%3Cpath d='M16 3.13a4 4 0 0 1 0 7.75'/%3E%3C/svg%3E"); color: #4f46e5; }
.ic-user    { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'/%3E%3Ccircle cx='12' cy='7' r='4'/%3E%3C/svg%3E"); color: #4f46e5; }
.ic-star    { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2'/%3E%3C/svg%3E"); color: #d97706; }
.ic-link    { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/%3E%3Cpath d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/%3E%3C/svg%3E"); color: #1d4ed8; }
.ic-trend   { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='23 6 13.5 15.5 8.5 10.5 1 18'/%3E%3Cpolyline points='17 6 23 6 23 12'/%3E%3C/svg%3E"); color: #059669; }
.ic-doc     { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpolyline points='14 2 14 8 20 8'/%3E%3Cline x1='16' y1='13' x2='8' y2='13'/%3E%3Cline x1='16' y1='17' x2='8' y2='17'/%3E%3C/svg%3E"); color: #4f46e5; }
.ic-radar   { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Ccircle cx='12' cy='12' r='6'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3C/svg%3E"); color: #059669; }
.ic-alert   { --ic: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z'/%3E%3Cline x1='12' y1='9' x2='12' y2='13'/%3E%3Cline x1='12' y1='17' x2='12.01' y2='17'/%3E%3C/svg%3E"); color: #dc2626; }
.ic-indigo  { color: #4f46e5; }
.dept-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.dept-tab { display: flex; align-items: center; gap: 6px; padding: 8px 14px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; font-size: 13px; font-weight: 500; color: #374151; cursor: pointer; transition: 0.15s; }
.dept-tab:hover { border-color: #4f46e5; color: #4f46e5; }
.dept-tab.active { background: #4f46e5; color: #fff; border-color: #4f46e5; }
.tab-score { font-size: 11px; background: rgba(255,255,255,0.2); padding: 1px 6px; border-radius: 6px; font-weight: 600; }
.dept-tab.active .tab-score { background: rgba(255,255,255,0.25); }
.dept-tab:not(.active) .tab-score { background: #f3f4f6; color: #6b7280; }

.dept-detail { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.dept-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.dept-title { font-size: 18px; font-weight: 700; color: #1a1a2e; }
.dept-meta { display: flex; gap: 8px; }
.meta-tag { font-size: 12px; background: #f3f4f6; padding: 4px 10px; border-radius: 6px; color: #374151; }
.score-tag { background: #fef3c7; color: #92400e; font-weight: 600; }
.src-tag { font-size: 10px; background: #dbeafe; color: #1d4ed8; padding: 2px 8px; border-radius: 8px; margin-left: 8px; font-weight: 600; vertical-align: middle; }
.source-error { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c; border-radius: 8px; padding: 10px 14px; font-size: 12px; margin-bottom: 16px; font-weight: 500; line-height: 1.6; }

/* 拼多多打品成功率分析 */
.pdd-analysis-panel { margin-bottom: 18px; border: 1px solid #dbeafe; border-radius: 12px; padding: 14px; background: linear-gradient(135deg, #f8fbff, #f8fffc); }
.pdd-analysis-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.pdd-section-title { border-top: 0; padding-top: 0; margin-bottom: 3px; color: #1e3a8a; }
.pdd-analysis-subtitle { font-size: 11px; color: #64748b; }
.pdd-source-tag { flex-shrink: 0; font-size: 10px; color: #1d4ed8; background: #dbeafe; padding: 4px 8px; border-radius: 8px; }
.pdd-analysis-error { margin-top: 12px; padding: 9px 12px; border-radius: 8px; color: #92400e; background: #fffbeb; border: 1px solid #fde68a; font-size: 12px; }
.pdd-view-title { display: flex; align-items: center; gap: 7px; margin: 14px 0 9px; color: #1f2937; font-size: 13px; font-weight: 700; }
.pdd-step { display: inline-flex; width: 20px; height: 20px; align-items: center; justify-content: center; border-radius: 50%; background: #1e3a8a; color: #fff; font-size: 11px; }
.pdd-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.pdd-kpi-card { min-height: 82px; padding: 12px; border-radius: 9px; background: #fff; border: 1px solid #e5e7eb; }
.pdd-kpi-label { display: block; font-size: 11px; color: #64748b; margin-bottom: 5px; }
.pdd-kpi-card strong { font-size: 24px; line-height: 1; color: #1e3a8a; }
.pdd-kpi-card em { margin-left: 3px; font-size: 11px; color: #64748b; font-style: normal; }
.pdd-kpi-card small { display: block; margin-top: 7px; color: #94a3b8; font-size: 10px; }
.b-kpi { border-top: 3px solid #2563eb; }
.a-kpi { border-top: 3px solid #059669; }
.success-kpi { border-top: 3px solid #1e3a8a; }
.efficiency-kpi { border-top: 3px solid #d97706; }
.b-kpi strong { color: #2563eb; }
.a-kpi strong { color: #059669; }
.success-kpi strong { color: #1e3a8a; }
.efficiency-kpi strong { color: #b45309; }
.pdd-trend-summary { display: flex; align-items: center; gap: 6px; margin-top: 10px; padding: 8px 10px; border-radius: 7px; background: #f8fafc; color: #64748b; font-size: 11px; }
.pdd-trend-summary .ic { color: #64748b; }
.pdd-trend-summary.trend-positive { color: #047857; background: #ecfdf5; }
.pdd-trend-summary.trend-positive .ic { color: #059669; }
.pdd-trend-summary.trend-negative { color: #b91c1c; background: #fef2f2; }
.pdd-trend-summary.trend-negative .ic { color: #dc2626; }
.pdd-analysis-grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }
.pdd-trend-card, .pdd-owner-card { min-width: 0; padding: 11px 12px; border-radius: 9px; background: #fff; border: 1px solid #e5e7eb; }
.pdd-card-title { font-size: 12px; color: #1f2937; font-weight: 700; margin-bottom: 4px; }
.pdd-trend-chart { height: 210px; width: 100%; }
.pdd-owner-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.pdd-owner-row { display: grid; grid-template-columns: 22px minmax(58px, 1fr) 42px 58px 58px; align-items: center; gap: 5px; font-size: 11px; }
.pdd-owner-rank { width: 20px; height: 20px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; color: #1d4ed8; background: #eff6ff; font-weight: 700; }
.pdd-owner-name { color: #1f2937; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pdd-owner-products { color: #64748b; text-align: right; }
.pdd-owner-rate { display: flex; flex-direction: column; align-items: flex-end; }
.pdd-owner-rate b { color: #059669; font-size: 11px; }
.pdd-owner-rate small { color: #94a3b8; font-size: 9px; }
.pdd-ranking-basis { margin: -2px 0 9px; color: #64748b; font-size: 10px; }
.pdd-owner-table-wrap { overflow-x: auto; }
.pdd-owner-table { width: 100%; border-collapse: collapse; min-width: 760px; font-size: 11px; }
.pdd-owner-table th { padding: 8px 7px; color: #64748b; background: #f8fafc; border-bottom: 1px solid #e5e7eb; text-align: left; white-space: nowrap; font-weight: 600; }
.pdd-owner-table td { padding: 8px 7px; border-bottom: 1px solid #f1f5f9; color: #374151; white-space: nowrap; }
.pdd-owner-table tbody tr:hover { background: #f8fbff; }
.pdd-owner-table td:nth-child(1), .pdd-owner-table th:nth-child(1) { text-align: center; width: 44px; }
.pdd-owner-table td:nth-child(3) b, .pdd-owner-table td:nth-child(7) b { color: #1e3a8a; }
.pdd-owner-table td small { display: block; margin-top: 2px; color: #94a3b8; font-size: 9px; }
.pdd-owner-person { display: flex; flex-direction: column; gap: 2px; }
.pdd-owner-person b { color: #1f2937; }
.pdd-owner-rank { width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; color: #1d4ed8; background: #eff6ff; font-weight: 700; }
.pdd-owner-pending td { color: #94a3b8; background: #fafafa; }
.pdd-owner-pending .pdd-owner-rank { color: #9ca3af; background: #f3f4f6; }
.pdd-negative { color: #dc2626 !important; font-weight: 600; }
.pdd-owner-status { display: inline-block; padding: 2px 6px; border-radius: 6px; font-size: 10px; }
.status-ranked { color: #047857; background: #d1fae5; }
.status-pending { color: #92400e; background: #fef3c7; }
.pdd-report-card { margin-top: 12px; padding: 12px; border-radius: 9px; border: 1px solid #d1fae5; background: #f0fdf4; }
.pdd-report-card .pdd-view-title { margin-top: 0; }
.pdd-report-headline { color: #065f46; font-size: 13px; font-weight: 700; line-height: 1.5; }
.pdd-report-conclusion { margin: 6px 0 10px; color: #374151; font-size: 11px; line-height: 1.7; }
.pdd-report-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pdd-report-label { color: #047857; font-size: 11px; font-weight: 700; }
.pdd-report-grid ul { margin: 5px 0 0; padding-left: 17px; color: #4b5563; font-size: 11px; line-height: 1.7; }
.pdd-supervisor-card { margin-top: 12px; padding: 12px; border-radius: 9px; border: 1px solid #fed7aa; background: linear-gradient(135deg, #fffaf3, #fff); }
.pdd-supervisor-card .pdd-view-title { margin-top: 0; }
.pdd-supervisor-meta { margin: -3px 0 10px; color: #9a3412; font-size: 10px; }
.pdd-supervisor-brief { margin: 0 0 10px; padding: 10px; border: 1px solid #fcd34d; border-radius: 8px; background: #fffdf5; }
.pdd-brief-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pdd-brief-source { flex-shrink: 0; padding: 2px 6px; border-radius: 5px; color: #92400e; background: #fef3c7; font-size: 9px; }
.pdd-brief-overall { margin: 6px 0 8px; color: #78350f; font-size: 11px; line-height: 1.7; font-weight: 600; }
.pdd-brief-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.pdd-brief-label { color: #92400e; font-size: 10px; font-weight: 700; }
.pdd-brief-grid ul, .pdd-brief-compare ul { margin: 4px 0 0; padding-left: 17px; color: #4b5563; font-size: 10px; line-height: 1.65; }
.pdd-brief-compare { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #fcd34d; }
.pdd-supervisor-empty { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border: 1px dashed #fdba74; border-radius: 7px; color: #92400e; background: #fff7ed; font-size: 11px; line-height: 1.6; }
.pdd-supervisor-columns, .pdd-diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.pdd-supervisor-block, .pdd-diff-block { min-width: 0; padding: 10px; border: 1px solid #e5e7eb; border-radius: 7px; background: #fff; }
.supervisor-block { border-color: #fde68a; background: #fffdf5; }
.ai-block { border-color: #bfdbfe; background: #f8fbff; }
.pdd-supervisor-label { color: #7c2d12; font-size: 11px; font-weight: 700; }
.ai-block .pdd-supervisor-label { color: #1e40af; }
.pdd-supervisor-block ul, .pdd-diff-block ul { margin: 5px 0 0; padding-left: 17px; color: #4b5563; font-size: 11px; line-height: 1.65; }
.pdd-supervisor-covered { margin-top: 5px; color: #92400e; font-size: 10px; line-height: 1.6; }
.pdd-supervisor-covered span { color: #b45309; }
.pdd-supervisor-muted { display: inline-block; margin-top: 6px; color: #9ca3af; font-size: 11px; }
.consensus-block { border-color: #bbf7d0; background: #f0fdf4; }
.difference-block { border-color: #fecaca; background: #fff7f7; }
.consensus-block .pdd-supervisor-label { color: #047857; }
.difference-block .pdd-supervisor-label { color: #b91c1c; }
.pdd-supervisor-source { margin-top: 10px; border-top: 1px solid #fed7aa; padding-top: 8px; color: #7c2d12; font-size: 11px; }
.pdd-supervisor-source summary { cursor: pointer; font-weight: 600; }
.pdd-supervisor-source pre { max-height: 260px; overflow: auto; margin: 7px 0 0; padding: 9px; white-space: pre-wrap; word-break: break-word; border-radius: 6px; background: #fff; color: #4b5563; font: inherit; line-height: 1.6; }
.pdd-supervisor-conclusion { margin-top: 10px; padding: 8px 10px; border-radius: 7px; color: #7c2d12; background: #fffbeb; font-size: 11px; line-height: 1.7; }
.pdd-empty { padding: 35px 0; text-align: center; color: #94a3b8; font-size: 12px; }
.pdd-analysis-note { margin-top: 10px; color: #64748b; font-size: 10px; line-height: 1.6; }

.metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; margin-bottom: 20px; }
/* 产品团队两行布局：部门标签 + 3 数据项 */
.dimension-rows { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.dimension-row { display: flex; align-items: center; gap: 16px; background: #f8fafc; border-radius: 10px; padding: 12px 14px; }
.dimension-label { flex-shrink: 0; min-width: 72px; text-align: center; font-size: 15px; font-weight: 700; color: #4338ca; background: #eef2ff; border: 1px solid #e0e7ff; border-radius: 8px; padding: 8px 10px; letter-spacing: 1px; }
.dimension-cards { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; }
.dimension-cards .metric-card { background: #fff; border: 1px solid #f0f0f0; }
.dimension-cards .metric-card:hover { border-color: #dbeafe; }
.metric-card { background: #f8fafc; border-radius: 10px; padding: 12px; display: flex; align-items: center; gap: 10px; }
.metric-ring { position: relative; width: 56px; height: 56px; flex-shrink: 0; }
.ring-svg { width: 56px; height: 56px; }
.ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.ring-val { font-size: 14px; font-weight: 700; color: #1a1a2e; line-height: 1; }
.ring-unit { font-size: 9px; color: #9ca3af; }
.metric-info { flex: 1; min-width: 0; }
.metric-name { font-size: 11px; font-weight: 600; color: #1a1a2e; }
.metric-target { font-size: 10px; color: #9ca3af; margin-top: 1px; }
.metric-trend { font-size: 10px; font-weight: 600; margin-top: 2px; }
.t-up { color: #059669; }
.t-down { color: #2563eb; }
.t-stable { color: #6b7280; }

/* 打分面板（支持分组：人力行政部=招聘组/行政组 各一个雷达+滑块组） */
.score-panel { display: flex; gap: 20px; margin-bottom: 16px; align-items: flex-start; flex-wrap: wrap; }
.radar-group { flex: 1 1 480px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 14px; background: #fafafa; }
.rg-title { font-size: 13px; font-weight: 700; color: #4f46e5; margin-bottom: 10px; padding-left: 8px; border-left: 3px solid #4f46e5; }
.rg-body { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.rg-radar { height: 240px; width: 45%; min-width: 240px; }
.score-controls { flex: 1; min-width: 240px; }
.sc-item { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.sc-dim { font-size: 12px; font-weight: 500; color: #374151; width: 96px; flex-shrink: 0; line-height: 1.35; }
.sc-std { cursor: help; color: #9ca3af; margin-left: 2px; font-size: 11px; }
.sc-slider { flex: 1; height: 6px; accent-color: #4f46e5; cursor: pointer; }
.dept-score-progress { border-radius: 999px; background: linear-gradient(to right, #4f46e5 0 var(--progress-width), #e5e7eb var(--progress-width) 100%); cursor: default; }
.sc-num { width: 48px; padding: 2px 4px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 12px; text-align: center; }
.sc-num:focus { border-color: #4f46e5; outline: none; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
.sc-badge { font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 6px; width: 28px; text-align: center; }
.badge-green { background: #d1fae5; color: #059669; }
.badge-amber { background: #fef3c7; color: #d97706; }
.badge-red { background: #fee2e2; color: #dc2626; }
.sc-actions { display: flex; gap: 8px; margin-top: 10px; }
.sc-btn { padding: 6px 14px; border: none; border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; transition: 0.15s; }
.sc-btn.save { background: #4f46e5; color: #fff; }
.sc-btn.save:hover { background: #4338ca; }
.sc-btn.reset { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
.sc-btn.reset:hover { background: #e5e7eb; }
.sc-hint { font-size: 11px; color: #059669; margin-top: 6px; font-weight: 500; }

/* 主观评价（旧，保留兼容） */
.section-title { font-size: 14px; font-weight: 700; color: #1a1a2e; margin-bottom: 10px; padding-top: 4px; border-top: 1px solid #f0f0f0; padding-top: 14px; }
.subj-row { display: flex; gap: 16px; margin-bottom: 16px; align-items: center; }
.subj-list { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.subj-item { display: flex; align-items: center; gap: 6px; }
.subj-dim { font-size: 12px; font-weight: 500; color: #374151; width: 68px; flex-shrink: 0; }
.subj-bar-wrap { flex: 1; height: 10px; background: #f0f0f0; border-radius: 5px; overflow: hidden; }
.subj-bar { height: 100%; border-radius: 5px; transition: width 0.5s; }
.subj-score { font-size: 13px; font-weight: 700; color: #1a1a2e; width: 28px; text-align: right; }
.subj-trend { font-size: 10px; width: 48px; text-align: right; font-weight: 600; }

.eval-row td { padding: 0 8px 10px 8px !important; }
.eval-box {
  background: #f8f6ff; border: 1px solid #e8e4f0; border-radius: 10px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 6px;
}
.eval-label { font-size: 11px; font-weight: 600; color: #6b5b9e; }
.eval-text { font-size: 12px; color: #374151; line-height: 1.7; }
.eval-meta { font-size: 10px; color: #9ca3af; line-height: 1.5; }

/* 个人人才雷达图 */
.member-radar-panel { margin-top: 10px; background: #f0fdf4; border: 1px solid #d1fae5; border-radius: 10px; padding: 12px 14px; }
.mr-title { font-size: 13px; font-weight: 700; color: #065f46; margin-bottom: 10px; }
.mr-body { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.mr-controls { flex: 1; min-width: 240px; }

/* 成员 */
.member-table-wrap { overflow-x: auto; }
/* 成员详情抽屉（右侧滑出） */
.drawer-mask { position: fixed; inset: 0; background: rgba(15,23,42,0.45); z-index: 100; }
.member-drawer { position: fixed; top: 0; right: 0; bottom: 0; width: 480px; max-width: 92vw; background: #fff; box-shadow: -8px 0 24px rgba(0,0,0,0.14); z-index: 101; display: flex; flex-direction: column; }
.drawer-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #eef0f3; flex-shrink: 0; }
.drawer-title { font-size: 15px; font-weight: 700; color: #1a1a2e; }
.drawer-close { border: none; background: #f3f4f6; color: #374151; width: 26px; height: 26px; border-radius: 6px; cursor: pointer; font-size: 13px; line-height: 1; }
.drawer-close:hover { background: #e5e7eb; }
.drawer-scroll { flex: 1; overflow-y: auto; padding: 14px 18px 24px; }
.drawer-section { margin-bottom: 14px; }
.drawer-section-title { font-size: 13px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }
.daily-chart { width: 100%; height: 180px; }
.daily-empty { font-size: 12px; color: #9ca3af; background: #f8fafc; border-radius: 8px; padding: 26px 0; text-align: center; }
.mr-radar-box { height: 230px; width: 45%; min-width: 240px; }
.mr-standards { margin-top: 12px; padding-top: 10px; border-top: 1px solid #d1fae5; }
.mr-standards-title { font-size: 12px; font-weight: 700; color: #065f46; margin-bottom: 7px; }
.mr-standard-list { display: grid; gap: 6px; }
.mr-standard-item { display: grid; grid-template-columns: 142px 1fr; gap: 8px; align-items: start; font-size: 11px; line-height: 1.5; color: #4b5563; }
.mr-standard-item b { color: #047857; font-weight: 700; }
/* 抽屉过渡动画 */
.drawer-fade-enter-active, .drawer-fade-leave-active { transition: opacity 0.25s; }
.drawer-fade-enter-from, .drawer-fade-leave-to { opacity: 0; }
.drawer-slide-enter-active, .drawer-slide-leave-active { transition: transform 0.28s ease; }
.drawer-slide-enter-from, .drawer-slide-leave-to { transform: translateX(100%); }
.member-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.member-table th { background: #f8fafc; padding: 8px 10px; text-align: left; font-weight: 600; color: #555; border-bottom: 2px solid #e2e8f0; white-space: nowrap; font-size: 11px; }
.member-table td { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; }
.member-table tbody tr:hover { background: #f8fafc; }
.top-row td { background: #fffbeb; }
.m-name { font-weight: 600; color: #1a1a2e; }
.m-pos { color: #6b7280; }
.m-score { text-align: center; }
/* 雷达评估维度列：维度 chips（已评分=翠绿底+分数，未评分=灰底；文字过长自动换行） */
.m-radar-dims { display: flex; flex-wrap: wrap; gap: 4px; max-width: 430px; }
.mrd-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; padding: 2px 8px; border-radius: 9px; cursor: help; line-height: 1.45; text-align: left; overflow-wrap: break-word; word-break: break-all; }
.mrd-scored { background: #d1fae5; color: #047857; border: 1px solid #a7f3d0; }
.mrd-empty { background: #f3f4f6; color: #9ca3af; border: 1px solid #e5e7eb; }
.mrd-dim { font-weight: 500; }
.mrd-score { font-style: normal; font-weight: 700; font-size: 10px; color: #065f46; flex-shrink: 0; }
.mrd-empty .mrd-score { color: #9ca3af; }
.mrd-max { font-style: normal; font-size: 9px; font-weight: 400; opacity: 0.6; margin-left: 1px; }
.mrd-none { color: #d1d5db; font-size: 11px; }
.score-badge { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 12px; font-weight: 700; }
.sc-max { font-style: normal; font-size: 10px; font-weight: 500; opacity: 0.6; margin-left: 1px; }
.sc-a { background: #d1fae5; color: #059669; }
.sc-b { background: #dbeafe; color: #2563eb; }
.sc-c { background: #fef3c7; color: #d97706; }
.sc-d { background: #fee2e2; color: #dc2626; }
.m-metrics { display: flex; flex-wrap: wrap; gap: 6px; }
.mm-item { display: inline-flex; align-items: center; gap: 3px; background: #f3f4f6; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.mm-label { color: #6b7280; }
.mm-val { color: #1a1a2e; font-weight: 600; }
@media (max-width: 760px) {
  .pdd-kpi-grid, .pdd-analysis-grid, .pdd-report-grid, .pdd-brief-grid, .pdd-supervisor-columns, .pdd-diff-grid { grid-template-columns: 1fr; }
  .pdd-owner-row { grid-template-columns: 22px minmax(50px, 1fr) 38px 52px 52px; }
}
</style>
