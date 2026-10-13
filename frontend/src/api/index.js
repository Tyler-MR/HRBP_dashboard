import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 90000,
})

export async function fetchDashboard({ month, viewType, year, edu_filter, staff_period } = {}) {
  const params = {}
  params.view_type = viewType || 'monthly'
  if (viewType === 'yearly' && year) {
    params.year = year
  } else if (month) {
    params.month = month
  }
  if (edu_filter) {
    params.edu_filter = edu_filter
  }
  if (staff_period) {
    params.staff_period = staff_period
  }
  const res = await api.get('/dashboard', { params })
  return res.data
}

export async function fetchHrEfficiency(period, { force = false } = {}) {
  const params = {}
  if (period) params.period = period
  if (force) params.force = true
  const res = await api.get('/hr-efficiency', { params })
  return res.data
}

export async function fetchTalentAnalysis() {
  const res = await api.get('/talent-analysis')
  return res.data
}

export default api
