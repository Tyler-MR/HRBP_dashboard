import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 90000,
})

export async function fetchDashboard({ month, viewType, year, edu_filter } = {}) {
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
  const res = await api.get('/dashboard', { params })
  return res.data
}

export async function fetchHrEfficiency(period) {
  const params = {}
  if (period) params.period = period
  const res = await api.get('/hr-efficiency', { params })
  return res.data
}

export async function fetchTalentAnalysis() {
  const res = await api.get('/talent-analysis')
  return res.data
}

export default api
