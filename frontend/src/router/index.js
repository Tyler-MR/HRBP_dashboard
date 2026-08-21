import { createRouter, createWebHistory } from 'vue-router'
import RecruitmentDashboard from '../components/RecruitmentDashboard.vue'
import HrEfficiencyDashboard from '../components/HrEfficiencyDashboard.vue'
import HrStaffDashboard from '../components/HrStaffDashboard.vue'
import AttritionDashboard from '../components/AttritionDashboard.vue'
import DeptEfficiencyDashboard from '../components/DeptEfficiencyDashboard.vue'
import LogEvaluationDashboard from '../components/LogEvaluationDashboard.vue'
import OnDutyDashboard from '../components/OnDutyDashboard.vue'

const routes = [
  { path: '/', name: 'recruitment', component: RecruitmentDashboard },
  { path: '/efficiency', name: 'efficiency', component: HrEfficiencyDashboard },
  { path: '/staff', name: 'staff', component: HrStaffDashboard },
  { path: '/attrition', name: 'attrition', component: AttritionDashboard },
  { path: '/dept-efficiency', name: 'dept-efficiency', component: DeptEfficiencyDashboard },
  { path: '/logs', name: 'logs', component: LogEvaluationDashboard },
  { path: '/onduty', name: 'onduty', component: OnDutyDashboard },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
