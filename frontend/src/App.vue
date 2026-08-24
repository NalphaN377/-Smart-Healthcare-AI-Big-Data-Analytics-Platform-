<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import ChatPanel from './components/ChatPanel.vue'
import DashboardChart from './components/DashboardChart.vue'
import { createReport, dataQuality, health, overview, predictCost, publishReport, streamChat } from './api/client'
import { authState, can, logout } from './auth'

const route = useRoute()
const router = useRouter()
const activeView = computed(() => String(route.name || 'overview'))
const dateRange = ref('2021 年')
const regionFilter = ref('全部服务区域')
const mobileMenuOpen = ref(false)
const loading = ref(false)
const dataLoading = ref(false)
const apiConnected = ref(false)
const apiError = ref('')
const messages = ref([])
const conversationId = ref(null)
const aiSummary = ref('选择一个建议问题，或直接输入想分析的医疗数据问题。')
const aiChartOption = ref(null)
const dashboard = ref({ summary: {}, trend: [], diseases: [], ages: [], payments: [], genders: [], severity: [] })
const qualityReport = ref({})
const lastIngestion = ref(null)
const reportContent = ref('')
const reportId = ref(null)
const reportLoading = ref(false)
const lastResponseMs = ref(0)
const searchQuery = ref('')
const costLoading = ref(false)
const costError = ref('')
const costResult = ref(null)
const costForm = reactive({
  hospital_service_area: 'New York City', hospital_county: '', age_group: '50 to 69',
  gender: 'F', race: '', ethnicity: '', type_of_admission: 'Emergency',
  ccsr_diagnosis_code: '', ccsr_procedure_code: '', apr_drg_code: '', apr_mdc_code: '',
  apr_severity_of_illness_desc: 'Major', apr_risk_of_mortality: 'Major',
  apr_medical_surgical_desc: '', payment_typology_1: 'Medicare',
  emergency_department_indicator: 'Y', discharge_year: 2024, length_of_stay: 5,
  apr_severity_of_illness_code: 3,
})

const navItems = computed(() => [
  { id: 'overview', label: '运营总览', icon: 'dashboard', permission: 'overview:read' },
  { id: 'ai', label: 'AI 智能分析', icon: 'sparkle', badge: 'AI', anyPermission: ['ai:basic', 'ai:advanced'] },
  { id: 'cost-prediction', label: '费用预测', icon: 'wallet', badge: 'ML', permission: 'cost_prediction:use' },
  { id: 'data', label: '数据资产', icon: 'database', permission: 'data_asset:read' },
  { id: 'patients', label: '患者画像', icon: 'users', permission: 'patient_profile:read' },
  { id: 'reports', label: '分析报告', icon: 'report', permission: 'report:generate' },
  { id: 'public-reports', label: '公开报告', icon: 'report', permission: 'report:public:read', patientOnly: true },
  { id: 'account', label: '账户设置', icon: 'settings' },
].filter((item) => (!item.permission || can(item.permission)) && (!item.anyPermission || item.anyPermission.some(can)) && (!item.patientOnly || !can('report:generate'))))
const viewMeta = {
  overview: { title: '医疗运营总览', subtitle: '聚合住院、费用与资源利用指标，辅助管理决策' },
  ai: { title: 'AI 智能分析', subtitle: '用自然语言探索医疗大数据，快速生成洞察与图表' },
  'cost-prediction': { title: '住院费用预测', subtitle: '基于已编码住院信息估算最终总成本及误差范围' },
  data: { title: '数据资产中心', subtitle: '追踪数据接入、治理质量与服务状态' },
  patients: { title: '患者画像分析', subtitle: '从人口统计学与就诊特征理解患者群体' },
  reports: { title: '分析报告', subtitle: '沉淀专题洞察，形成可复用的决策依据' },
}
const currentMeta = computed(() => viewMeta[activeView.value] || viewMeta.overview)
const formatNumber = (value, digits = 0) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: digits })
const formatMoney = (value) => `US$${formatNumber(value, 0)}`
const formatCost = (value) => `US$${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const totalRecords = computed(() => Number(dashboard.value.summary?.discharges || 0))
const qualityScore = computed(() => Number(qualityReport.value.overall || 0) * 100)
const topAgeGroup = computed(() => [...(dashboard.value.ages || [])].sort((a, b) => b.count - a.count)[0]?.dimension_value || '暂无')
const topDiseaseName = computed(() => dashboard.value.diseases?.[0]?.dimension_value || '暂无')

const metrics = computed(() => [
  { label: '出院记录', value: formatNumber(totalRecords.value), unit: '条', trend: '全量', direction: 'up', note: '去重清洗后', icon: 'activity', tone: 'teal' },
  { label: '平均住院日', value: formatNumber(dashboard.value.summary?.avg_length_of_stay, 2), unit: '天', trend: '核心', direction: 'down', note: '全体患者均值', icon: 'clock', tone: 'blue' },
  { label: '次均住院费用', value: formatNumber(dashboard.value.summary?.avg_total_charges), unit: '元', trend: '费用', direction: 'up', note: 'Total Charges', icon: 'wallet', tone: 'amber' },
  { label: '覆盖医疗机构', value: formatNumber(dashboard.value.summary?.facilities), unit: '家', trend: '机构', direction: 'up', note: '去重机构数', icon: 'hospital', tone: 'violet' },
])

const insightItems = computed(() => {
  const topDisease = dashboard.value.diseases?.[0]
  const topAge = [...(dashboard.value.ages || [])].sort((a, b) => b.count - a.count)[0]
  return [
    { tag: '人群结构', color: 'teal', title: `${topAge?.dimension_value || '主要年龄组'}患者占比最高`, text: `该组共 ${formatNumber(topAge?.count)} 条记录，平均住院日 ${formatNumber(topAge?.avg_length_of_stay, 1)} 天。`, action: '查看患者画像' },
    { tag: '疾病负担', color: 'amber', title: '重点疾病住院量集中', text: `${topDisease?.dimension_value || '首位疾病'}记录数为 ${formatNumber(topDisease?.count)}，次均费用约 ${formatMoney(topDisease?.avg_total_charges)}。`, action: '查看费用分析' },
    { tag: '数据质量', color: 'blue', title: `综合质量评分 ${qualityScore.value.toFixed(2)}%`, text: `本次全量导入 ${formatNumber(lastIngestion.value?.rows_inserted || totalRecords.value)} 条，四维质量评估已完成。`, action: '生成专题报告' },
  ]
})

const diseaseRows = computed(() => (dashboard.value.diseases || []).slice(0, 8).map((row) => ({
  name: row.dimension_value || '未标注', count: formatNumber(row.count), days: formatNumber(row.avg_length_of_stay, 1), cost: formatMoney(row.avg_total_charges), change: '—',
})))
const qualityItems = computed(() => [
  ['完整性', 'completeness'], ['准确性', 'accuracy'], ['一致性', 'consistency'], ['时效性', 'timeliness'],
].map(([label, key]) => ({ label, value: Number(qualityReport.value[key] || 0) * 100, text: `${(Number(qualityReport.value[key] || 0) * 100).toFixed(2)}%` })))
const pipelineRows = computed(() => [
  { source: '住院出院记录', type: 'CSV · 33 字段', records: formatNumber(lastIngestion.value?.rows_inserted || totalRecords.value), updated: lastIngestion.value?.finished_at?.replace('T', ' ') || '已完成', status: '已完成' },
  { source: 'SQL Server 主库', type: 'SQL Server 2022', records: formatNumber(totalRecords.value), updated: '实时可查询', status: apiConnected.value ? '已完成' : '连接异常' },
  { source: '疾病 CCSR 维度', type: '聚合索引', records: formatNumber(dashboard.value.diseases?.length), updated: '按需计算', status: '已完成' },
  { source: 'DeepSeek V4 Flash', type: 'Anthropic SSE', records: '流式', updated: '按需调用', status: '已完成' },
])
const reportCards = [
  { type: '运营分析', title: '医疗运营综合分析报告', date: '实时生成', desc: '覆盖住院量、住院效率、费用结构与重点疾病变化。', icon: 'file-chart', color: 'teal' },
  { type: '患者画像', title: '重点患者群体结构分析', date: '实时生成', desc: '聚焦年龄、性别与病情严重程度的患者群体结构。', icon: 'users', color: 'blue' },
  { type: '费用分析', title: '重点疾病住院费用报告', date: '实时生成', desc: '识别住院量与次均费用较高的重点疾病组。', icon: 'wallet', color: 'amber' },
  { type: '数据质量', title: '住院数据质量评估报告', date: '最近导入', desc: '从完整性、准确性、一致性和时效性四维评估。', icon: 'shield', color: 'violet' },
]

const axisStyle = { axisLine: { lineStyle: { color: '#dfe5e8' } }, axisTick: { show: false }, axisLabel: { color: '#7b8792', fontSize: 11 } }
const tooltipStyle = { backgroundColor: '#213038', borderWidth: 0, textStyle: { color: '#fff', fontSize: 12 }, padding: [9, 12] }
const ratioRows = (rows) => { const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0); return rows.map((row) => ({ ...row, percent: total ? Number(row.count) / total * 100 : 0 })) }
const genderLegend = computed(() => { const labels = { F: '女性', M: '男性', U: '未知' }; const rows = ratioRows(dashboard.value.genders || []); return rows.map((row, i) => ({ label: labels[row.dimension_value] || '未知', percent: row.percent.toFixed(1), className: ['female', 'male', 'unknown'][i % 3] })) })
const patientSegments = computed(() => {
  const ages = ratioRows(dashboard.value.ages || [])
  const diseases = ratioRows(dashboard.value.diseases || [])
  const severity = ratioRows(dashboard.value.severity || [])
  const topAge = [...ages].sort((a, b) => b.count - a.count)[0] || {}
  const topDisease = [...diseases].sort((a, b) => b.count - a.count)[0] || {}
  const highRisk = severity.filter((row) => /major|extreme|重度|极重度/i.test(row.dimension_value || '')).reduce((sum, row) => sum + Number(row.count || 0), 0)
  return [
    { title: `${topAge.dimension_value || '主要年龄'}人群`, detail: '按年龄段住院记录自动识别', count: topAge.count, ratio: topAge.percent, icon: 'activity', tone: 'teal' },
    { title: '首位疾病人群', detail: topDisease.dimension_value || '暂无疾病分组', count: topDisease.count, ratio: topDisease.percent, icon: 'wallet', tone: 'amber' },
    { title: '较高严重程度人群', detail: 'APR Major / Extreme 分组', count: highRisk, ratio: totalRecords.value ? highRisk / totalRecords.value * 100 : 0, icon: 'shield', tone: 'red' },
  ]
})

const trendOption = computed(() => {
  const rows = dashboard.value.trend || []
  return { color: ['#17837a', '#86c9c1'], tooltip: { trigger: 'axis', ...tooltipStyle }, legend: { right: 0, top: 0, icon: 'circle', itemWidth: 8, data: ['出院记录', '平均住院日'] }, grid: { left: 12, right: 18, top: 42, bottom: 4, containLabel: true }, xAxis: { type: 'category', data: rows.map((r) => String(r.year)), ...axisStyle }, yAxis: [{ type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (v) => `${v / 10000}万` } }, { type: 'value', ...axisStyle, splitLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value} 天' } }], series: [{ name: '出院记录', type: 'bar', barMaxWidth: 52, data: rows.map((r) => r.count), itemStyle: { borderRadius: [6, 6, 0, 0] } }, { name: '平均住院日', type: 'line', yAxisIndex: 1, data: rows.map((r) => Number(r.avg_length_of_stay).toFixed(2)), symbolSize: 8, lineStyle: { width: 3 } }] }
})
const ageOption = computed(() => { const rows = ratioRows(dashboard.value.ages || []); return { tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 6, right: 16, top: 14, bottom: 3, containLabel: true }, xAxis: { type: 'value', max: Math.ceil(Math.max(10, ...rows.map((r) => r.percent)) / 5) * 5 + 5, ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}%' } }, yAxis: { type: 'category', data: rows.map((r) => r.dimension_value), ...axisStyle, axisLine: { show: false } }, series: [{ type: 'bar', barWidth: 10, data: rows.map((r) => Number(r.percent.toFixed(2))), label: { show: true, position: 'right', color: '#53616c', fontSize: 11, formatter: '{c}%' }, itemStyle: { color: (p) => ['#a4d9d3', '#76c5bc', '#43aa9e', '#17837a', '#0c625d'][p.dataIndex % 5], borderRadius: [0, 5, 5, 0] } }] } })
const paymentOption = computed(() => ({ tooltip: { trigger: 'item', ...tooltipStyle, formatter: '{b}<br/>{c}% · {d}%' }, legend: { orient: 'vertical', right: 0, top: 'middle', icon: 'circle', itemWidth: 8, itemGap: 12, textStyle: { color: '#66747e', fontSize: 10 } }, series: [{ type: 'pie', radius: ['50%', '74%'], center: ['35%', '50%'], padAngle: 2, label: { show: false }, data: (dashboard.value.payments || []).map((r, i) => ({ value: Number((Number(r.ratio || 0) * 100).toFixed(2)), name: r.payment || '未标注', itemStyle: { color: ['#17837a', '#5bb5aa', '#6f92c4', '#e1ad63', '#9d85bd', '#c5ced5'][i % 6] } })) }], graphic: [{ type: 'text', left: '27%', top: '43%', style: { text: '支付\n结构', textAlign: 'center', fill: '#50606a', fontSize: 13, lineHeight: 19, fontWeight: 600 } }] }))
const diseaseOption = computed(() => ({ tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 10, right: 38, top: 14, bottom: 2, containLabel: true }, xAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (v) => `${v / 1000}k` } }, yAxis: { type: 'category', inverse: true, data: (dashboard.value.diseases || []).map((r) => r.dimension_value), ...axisStyle, axisLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, width: 150, overflow: 'truncate', formatter: (value) => value.length > 22 ? `${value.slice(0, 22)}…` : value } }, series: [{ type: 'bar', barWidth: 12, data: (dashboard.value.diseases || []).map((r) => r.count), itemStyle: { color: '#2a8f86', borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: '#6c7983', fontSize: 10, formatter: (p) => `${(p.value / 1000).toFixed(1)}k` } }] }))
const genderOption = computed(() => { const labels = { F: '女性', M: '男性', U: '未知' }; return { tooltip: { trigger: 'item', ...tooltipStyle }, series: [{ type: 'pie', radius: ['56%', '78%'], center: ['50%', '50%'], label: { show: false }, data: (dashboard.value.genders || []).map((r, i) => ({ value: r.count, name: labels[r.dimension_value] || '未知', itemStyle: { color: ['#2a8f86', '#7398c8', '#d9dfe4'][i % 3] } })) }], graphic: [{ type: 'text', left: 'center', top: '42%', style: { text: `${formatNumber(totalRecords.value)}\n总记录`, textAlign: 'center', fill: '#33444e', fontSize: 12, lineHeight: 20, fontWeight: 600 } }] } })
const mortalityOption = computed(() => { const rows = ratioRows(dashboard.value.severity || []); return { tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 8, right: 15, top: 18, bottom: 2, containLabel: true }, xAxis: { type: 'category', data: rows.map((r) => r.dimension_value), ...axisStyle }, yAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}%' } }, series: [{ type: 'bar', barWidth: 30, data: rows.map((r) => Number(r.percent.toFixed(2))), itemStyle: { color: (p) => ['#9bd4ce', '#5eb8ae', '#e7b46d', '#d8796e'][p.dataIndex % 4], borderRadius: [5, 5, 0, 0] }, label: { show: true, position: 'top', color: '#6c7983', fontSize: 10, formatter: '{c}%' } }] } })

function filters() { return regionFilter.value === '全部服务区域' ? {} : { service_area: regionFilter.value } }
async function loadDashboard() {
  dataLoading.value = true; apiError.value = ''
  try {
    const [overviewResponse, healthResponse, qualityResponse] = await Promise.all([
      overview(filters()), health(), can('data_asset:read') ? dataQuality() : Promise.resolve(null),
    ])
    dashboard.value = overviewResponse.data
    lastResponseMs.value = Number(overviewResponse.meta?.elapsed_ms || 0)
    qualityReport.value = qualityResponse?.data?.quality || {}
    lastIngestion.value = qualityResponse?.data?.latest_ingestion || null
    apiConnected.value = Boolean(healthResponse.data.database?.connected)
  } catch (error) { apiConnected.value = false; apiError.value = error.message || '后端服务不可用' } finally { dataLoading.value = false }
}
function selectView(id) { router.push(`/${id}`); mobileMenuOpen.value = false; window.scrollTo({ top: 0, behavior: 'smooth' }) }
async function signOut() { await logout(); await router.replace('/login') }
async function send(query) {
  if (!query.trim() || loading.value) return
  messages.value.push({ role: 'user', content: query }); loading.value = true; aiSummary.value = ''
  aiChartOption.value = null
  let assistantMessage
  try {
    await streamChat(query, {
      context(payload) { aiChartOption.value = payload.chart || null; conversationId.value = payload.conversation_id || conversationId.value },
      delta(payload) { if (!assistantMessage) { assistantMessage = { role: 'assistant', content: '' }; messages.value.push(assistantMessage) }; assistantMessage.content += payload.text; aiSummary.value += payload.text },
      done(payload) { conversationId.value = payload.conversation_id || conversationId.value; if (!aiSummary.value) aiSummary.value = payload.summary || '分析已完成。' },
    }, conversationId.value)
  } catch (error) {
    aiChartOption.value = null
    aiSummary.value = error.message || '当前无法准确完成该问题的分析，请稍后重试或补充分析维度和指标。'
    if (!assistantMessage) messages.value.push({ role: 'assistant', content: aiSummary.value })
    else assistantMessage.content += '\n\n' + aiSummary.value
  } finally { loading.value = false }
}
async function submitCostPrediction() {
  if (costLoading.value) return
  costLoading.value = true; costError.value = ''; costResult.value = null
  try {
    const numericFields = new Set(['discharge_year', 'length_of_stay', 'apr_severity_of_illness_code'])
    const features = Object.fromEntries(Object.entries(costForm)
      .filter(([, value]) => value !== '' && value !== null && value !== undefined)
      .map(([key, value]) => [key, numericFields.has(key) ? Number(value) : String(value).trim()]))
    const response = await predictCost(features)
    costResult.value = response.data
  } catch (error) {
    costError.value = error.message || '费用预测失败，请检查输入后重试。'
  } finally { costLoading.value = false }
}
function resetCostPrediction() {
  Object.assign(costForm, {
    hospital_service_area: 'New York City', hospital_county: '', age_group: '50 to 69',
    gender: 'F', race: '', ethnicity: '', type_of_admission: 'Emergency',
    ccsr_diagnosis_code: '', ccsr_procedure_code: '', apr_drg_code: '', apr_mdc_code: '',
    apr_severity_of_illness_desc: 'Major', apr_risk_of_mortality: 'Major',
    apr_medical_surgical_desc: '', payment_typology_1: 'Medicare',
    emergency_department_indicator: 'Y', discharge_year: 2024, length_of_stay: 5,
    apr_severity_of_illness_code: 3,
  })
  costResult.value = null; costError.value = ''
}
async function generateReport() {
  reportLoading.value = true
  try { const response = await createReport({ title: '医疗大数据综合洞察报告' }); reportContent.value = response.data.content; reportId.value = response.data.id } catch (error) { reportContent.value = `报告生成失败：${error.message}`; reportId.value = null } finally { reportLoading.value = false }
}
async function publishGeneratedReport() { if (!reportId.value) return; await publishReport(reportId.value); window.alert('报告已发布，患者用户现在可以查看') }
function exportDashboard() {
  const blob = new Blob([JSON.stringify(dashboard.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '智慧医疗运营数据.json'; link.click(); URL.revokeObjectURL(url)
}
function downloadReport() {
  if (!reportContent.value) return
  const blob = new Blob([reportContent.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '医疗大数据洞察报告.md'; link.click(); URL.revokeObjectURL(url)
}
function runSearch() {
  const query = searchQuery.value.trim()
  if (!query) return
  selectView('ai'); send(query); searchQuery.value = ''
}
function analyzeDisease(name) { selectView('ai'); send(`分析疾病「${name}」的住院量、平均住院日和费用`) }

onMounted(loadDashboard)
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileMenuOpen" class="mobile-overlay" @click="mobileMenuOpen = false"></div>
    <aside class="sidebar" :class="{ open: mobileMenuOpen }">
      <div class="brand"><div class="brand-mark"><span></span><span></span></div><div><strong>智医数析</strong><small>MED DATA INTELLIGENCE</small></div></div>
      <div class="side-label">工作台</div>
      <nav class="nav-list"><button v-for="item in navItems" :key="item.id" :class="{ active: activeView === item.id }" @click="selectView(item.id)"><AppIcon :name="item.icon" :size="19" /><span>{{ item.label }}</span><em v-if="item.badge">{{ item.badge }}</em></button></nav>
      <div class="sidebar-spacer"></div><template v-if="can('system:manage')"><div class="side-label">系统</div><nav class="nav-list secondary"><button @click="router.push('/admin/users')"><AppIcon name="users" :size="18" /><span>用户管理</span></button><button @click="router.push('/admin/system')"><AppIcon name="settings" :size="18" /><span>平台状态</span></button></nav></template>
      <div class="data-status"><div class="status-row"><span class="status-dot" :class="{ offline: !apiConnected }"></span><strong>{{ apiConnected ? '数据服务正常' : '等待后端服务' }}</strong></div><p>{{ lastIngestion?.finished_at ? `最近同步：${lastIngestion.finished_at.replace('T', ' ')}` : '正在读取同步状态' }}</p><div class="status-progress"><i :style="{ width: apiConnected ? '100%' : '18%' }"></i></div><small>{{ formatNumber(totalRecords) }} 条记录已就绪</small></div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <button class="mobile-menu" aria-label="打开菜单" @click="mobileMenuOpen = true"><AppIcon name="menu" :size="22" /></button>
        <div class="global-search"><AppIcon name="search" :size="17" /><input v-model="searchQuery" placeholder="输入问题，回车交给 AI 分析" @keyup.enter="runSearch" /><kbd>↵</kbd></div>
        <div class="topbar-actions"><div class="demo-pill"><span :class="{ offline: !apiConnected }"></span> {{ apiConnected ? '数据服务正常' : '服务未连接' }}</div><button class="icon-button" aria-label="通知"><AppIcon name="bell" :size="19" /><i></i></button><div class="profile"><div class="avatar">{{ (authState.user?.display_name || authState.user?.username || '用').slice(0,1) }}</div><div><strong>{{ authState.user?.display_name || authState.user?.username }}</strong><small>{{ authState.user?.role === 'admin' ? '运维员' : authState.user?.role === 'doctor' ? '医生用户' : '患者用户' }}</small></div><button class="logout-button" @click="signOut">退出</button></div></div>
      </header>

      <main class="content">
        <div class="page-heading"><div><p class="eyebrow">SMART HEALTHCARE PLATFORM</p><h1>{{ currentMeta.title }}</h1><span>{{ currentMeta.subtitle }}</span></div><div v-if="activeView === 'overview'" class="filters"><label><AppIcon name="hospital" :size="15" /><select v-model="regionFilter" @change="loadDashboard"><option>全部服务区域</option><option>New York City</option><option>Long Island</option><option>Hudson Valley</option><option>Capital/Adirondack</option><option>Central NY</option><option>Western NY</option><option>Southern Tier</option><option>Finger Lakes</option></select><AppIcon name="chevron-down" :size="13" /></label><label><AppIcon name="calendar" :size="15" /><select v-model="dateRange"><option>2021 年</option></select><AppIcon name="chevron-down" :size="13" /></label><button v-if="can('data:export')" class="outline-button" @click="exportDashboard"><AppIcon name="download" :size="15" /> 导出</button></div></div>
        <div v-if="apiError" class="api-error"><AppIcon name="info" :size="16" /> {{ apiError }}，当前页面保留已加载数据。</div>

        <template v-if="activeView === 'overview'">
          <section class="metric-grid"><article v-for="metric in metrics" :key="metric.label" class="metric-card"><div class="metric-icon" :class="metric.tone"><AppIcon :name="metric.icon" :size="21" /></div><div class="metric-top"><span>{{ metric.label }}</span><button>•••</button></div><div class="metric-value">{{ metric.value }} <small>{{ metric.unit }}</small></div><div class="metric-foot" :class="metric.direction"><span><AppIcon :name="metric.direction === 'up' ? 'arrow-up' : 'arrow-down'" :size="11" />{{ metric.trend }}</span>{{ metric.note }}</div></article></section>
          <section class="dashboard-grid primary-row" :class="{ single: !can('patient_profile:read') }"><article class="panel trend-panel"><div class="panel-head"><div><h2>住院运营趋势</h2><p>出院人次与平均住院日变化</p></div><button v-if="can('report:generate')" class="text-button" @click="selectView('reports')">查看明细 <AppIcon name="arrow-right" :size="14" /></button></div><DashboardChart :option="trendOption" height="294px" /></article><article v-if="can('patient_profile:read')" class="panel insight-panel"><div class="panel-head"><div><h2>AI 智能洞察</h2><p>基于本期数据自动生成</p></div><span class="ai-badge"><AppIcon name="sparkle" :size="13" /> AI</span></div><div class="insight-list"><div v-for="item in insightItems" :key="item.title" class="insight-item"><span class="insight-mark" :class="item.color"></span><div><em :class="item.color">{{ item.tag }}</em><h3>{{ item.title }}</h3><p>{{ item.text }}</p><button @click="selectView(item.action.includes('画像') ? 'patients' : item.action.includes('报告') ? 'reports' : 'ai')">{{ item.action }} <AppIcon name="arrow-right" :size="12" /></button></div></div></div></article></section>
          <section v-if="can('patient_profile:read')" class="dashboard-grid secondary-row"><article class="panel"><div class="panel-head"><div><h2>重点疾病住院量</h2><p>按 CCSR 疾病大类统计</p></div><button class="panel-more">•••</button></div><DashboardChart :option="diseaseOption" height="235px" /></article><article class="panel"><div class="panel-head"><div><h2>患者年龄结构</h2><p>各年龄段住院人次占比</p></div><button class="panel-more">•••</button></div><DashboardChart :option="ageOption" height="235px" /></article><article class="panel"><div class="panel-head"><div><h2>支付方式构成</h2><p>主要支付类型分布</p></div><button class="panel-more">•••</button></div><DashboardChart :option="paymentOption" height="235px" /></article></section>
          <section v-if="can('patient_profile:read')" class="panel data-table-panel"><div class="panel-head"><div><h2>重点疾病运营明细</h2><p>住院量、平均住院日与次均费用对比</p></div><button class="text-button" @click="selectView('reports')">查看完整报告 <AppIcon name="arrow-right" :size="14" /></button></div><div class="table-wrap"><table><thead><tr><th>疾病类别</th><th>出院人次</th><th>平均住院日</th><th>次均费用</th><th>同比变化</th><th></th></tr></thead><tbody><tr v-for="row in diseaseRows" :key="row.name"><td><span class="disease-dot"></span><strong>{{ row.name }}</strong></td><td>{{ row.count }}</td><td>{{ row.days }} 天</td><td>{{ row.cost }}</td><td><em :class="row.change.startsWith('-') ? 'negative' : 'positive'">{{ row.change }}</em></td><td><button class="row-action" @click="analyzeDisease(row.name)"><AppIcon name="arrow-right" :size="14" /></button></td></tr></tbody></table></div></section>
        </template>

        <template v-else-if="activeView === 'ai'">
          <div class="ai-layout"><section class="ai-chat-wrap"><div class="section-title"><span class="title-icon"><AppIcon name="brain" :size="20" /></span><div><h2>对话式数据分析</h2><p>{{can('ai:basic')?'面向患者的公开趋势与健康科普，不提供个人诊断建议':'我会将你的问题转换为分析任务，并仅在意图明确时返回可视化图表'}}</p></div></div><ChatPanel :messages="messages" :loading="loading" :suggestions="can('ai:basic') ? ['2021年住院量趋势','哪些疾病住院量较高？','不同服务区域住院趋势'] : ['2021年住院量趋势', '不同年龄段患者占比', '哪些疾病费用最高？', '支付方式占比']" @send="send" /></section><section class="ai-result-wrap"><article class="panel ai-result-card"><div class="panel-head"><div><h2>分析结果</h2><p>{{ apiConnected ? '连接 SQL Server · 支持 DeepSeek 语义理解与流式生成' : '等待数据服务连接' }}</p></div><div class="result-actions"><button @click="aiChartOption = null"><AppIcon name="refresh" :size="15" /></button><button v-if="can('data:export') && aiChartOption" @click="exportDashboard"><AppIcon name="download" :size="15" /></button></div></div><div class="ai-summary"><span><AppIcon name="sparkle" :size="16" /></span><p>{{ aiSummary }}</p></div><DashboardChart v-if="aiChartOption" :option="aiChartOption" height="350px" /><div v-else class="ai-chart-empty"><AppIcon name="sparkle" :size="22" /><span>问题意图明确且查询到有效数据后，图表将在这里展示</span></div><div class="chart-note"><span>分析口径</span> 住院出院记录 · 已去重并排除异常费用数据</div></article><div class="quick-facts"><article><span>当前数据集</span><strong>{{ formatNumber(totalRecords) }} 条</strong><small>住院出院记录</small></article><article><span>可分析维度</span><strong>{{can('ai:basic')?'3':'13'}} 个</strong><small>疾病 / 年份 / 区域等</small></article><article><span>聚合响应</span><strong>{{ lastResponseMs ? `${(lastResponseMs / 1000).toFixed(2)} 秒` : '—' }}</strong><small>最近一次总览查询</small></article></div></section></div>
        </template>

        <template v-else-if="activeView === 'cost-prediction'">
          <div class="cost-layout">
            <section class="panel cost-form-panel">
              <div class="panel-head"><div><h2>住院编码信息</h2><p>未填写字段由模型按训练数据缺失值规则处理，填写越完整通常越可靠</p></div><span class="model-badge">ML · 2024 验证</span></div>
              <form class="cost-form" @submit.prevent="submitCostPrediction">
                <div class="cost-form-section"><h3>基本与入院信息</h3><div class="cost-field-grid">
                  <label><span>服务区域</span><select v-model="costForm.hospital_service_area"><option value="">未知</option><option>New York City</option><option>Long Island</option><option>Hudson Valley</option><option>Capital/Adirondack</option><option>Central NY</option><option>Western NY</option><option>Southern Tier</option><option>Finger Lakes</option></select></label>
                  <label><span>医院所在县</span><input v-model.trim="costForm.hospital_county" maxlength="100" placeholder="例如 Manhattan" /></label>
                  <label><span>年龄段</span><select v-model="costForm.age_group"><option value="">未知</option><option>0 to 17</option><option>18 to 29</option><option>30 to 49</option><option>50 to 69</option><option>70 or Older</option></select></label>
                  <label><span>性别</span><select v-model="costForm.gender"><option value="">未知</option><option value="F">F · 女性</option><option value="M">M · 男性</option><option value="U">U · 未知</option></select></label>
                  <label><span>种族</span><input v-model.trim="costForm.race" maxlength="50" placeholder="可选" /></label>
                  <label><span>族裔</span><input v-model.trim="costForm.ethnicity" maxlength="50" placeholder="可选" /></label>
                  <label><span>入院类型</span><select v-model="costForm.type_of_admission"><option value="">未知</option><option>Emergency</option><option>Urgent</option><option>Elective</option><option>Newborn</option><option>Trauma</option><option>Not Available</option></select></label>
                  <label><span>急诊标志</span><select v-model="costForm.emergency_department_indicator"><option value="">未知</option><option value="Y">Y · 是</option><option value="N">N · 否</option></select></label>
                  <label><span>出院年份</span><input v-model.number="costForm.discharge_year" type="number" min="2000" max="2100" required /></label>
                  <label><span>住院日</span><input v-model.number="costForm.length_of_stay" type="number" min="0" max="3650" step="1" required /></label>
                </div></div>

                <div class="cost-form-section"><h3>诊断、手术与分组编码</h3><div class="cost-field-grid">
                  <label><span>CCSR 诊断编码</span><input v-model.trim="costForm.ccsr_diagnosis_code" maxlength="20" placeholder="例如 CIR019" /></label>
                  <label><span>CCSR 手术编码</span><input v-model.trim="costForm.ccsr_procedure_code" maxlength="20" placeholder="例如 CAR024" /></label>
                  <label><span>APR DRG 编码</span><input v-model.trim="costForm.apr_drg_code" maxlength="20" placeholder="可选" /></label>
                  <label><span>APR MDC 编码</span><input v-model.trim="costForm.apr_mdc_code" maxlength="10" placeholder="可选" /></label>
                  <label><span>严重程度编码</span><select v-model.number="costForm.apr_severity_of_illness_code"><option :value="0">0 · 未知</option><option :value="1">1 · Minor</option><option :value="2">2 · Moderate</option><option :value="3">3 · Major</option><option :value="4">4 · Extreme</option></select></label>
                  <label><span>严重程度描述</span><select v-model="costForm.apr_severity_of_illness_desc"><option value="">未知</option><option>Minor</option><option>Moderate</option><option>Major</option><option>Extreme</option></select></label>
                  <label><span>死亡风险</span><select v-model="costForm.apr_risk_of_mortality"><option value="">未知</option><option>Minor</option><option>Moderate</option><option>Major</option><option>Extreme</option></select></label>
                  <label><span>内科/外科分类</span><select v-model="costForm.apr_medical_surgical_desc"><option value="">未知</option><option>Medical</option><option>Surgical</option><option>Not Applicable</option></select></label>
                  <label class="wide"><span>主要支付方式</span><select v-model="costForm.payment_typology_1"><option value="">未知</option><option>Medicare</option><option>Medicaid</option><option>Private Health Insurance</option><option>Self-Pay</option><option>Blue Cross/Blue Shield</option><option>Federal/State/Local/VA</option><option>Miscellaneous/Other</option></select></label>
                </div></div>

                <div v-if="costError" class="cost-error"><AppIcon name="info" :size="15" />{{ costError }}</div>
                <div class="cost-actions"><button type="button" class="outline-button" @click="resetCostPrediction">重置</button><button type="submit" class="primary-button" :disabled="costLoading"><AppIcon name="sparkle" :size="15" />{{ costLoading ? '预测中…' : '开始预测' }}</button></div>
              </form>
            </section>

            <section class="cost-result-column">
              <article v-if="costResult" class="cost-result-card">
                <span class="result-kicker">PREDICTED TOTAL COST</span><p>预测住院总成本</p>
                <strong>{{ formatCost(costResult.predicted_total_cost) }}</strong>
                <div class="cost-band"><span>近似误差范围</span><b>{{ formatCost(costResult.approximate_error_band?.lower) }} — {{ formatCost(costResult.approximate_error_band?.upper) }}</b><small>基于 2024 时间外测试集 MAE，不是统计置信区间</small></div>
              </article>
              <article v-else class="panel cost-empty"><span><AppIcon name="wallet" :size="30" /></span><h2>等待预测</h2><p>填写左侧住院编码信息并点击“开始预测”，结果将在这里显示。</p></article>

              <article v-if="costResult" class="panel model-metrics-card"><div class="panel-head"><div><h2>模型验证指标</h2><p>{{ costResult.model?.version }} · 数据版本 {{ costResult.model?.training_data_version }}</p></div><span class="status-tag">已激活</span></div><div class="model-metrics">
                <div><span>R²</span><strong>{{ Number(costResult.model?.metrics?.r2 || 0).toFixed(4) }}</strong></div>
                <div><span>MAE</span><strong>{{ formatCost(costResult.model?.metrics?.mae) }}</strong></div>
                <div><span>中位误差</span><strong>{{ formatCost(costResult.model?.metrics?.median_absolute_error) }}</strong></div>
                <div><span>RMSE</span><strong>{{ formatCost(costResult.model?.metrics?.rmse) }}</strong></div>
              </div></article>
              <article class="cost-safety-note"><AppIcon name="shield" :size="18" /><div><strong>使用范围</strong><p>这是基于已编码住院信息的运营成本估算，单位为美元。不能作为入院前承诺、患者结算金额、保险理赔结果或医疗决策依据。</p></div></article>
            </section>
          </div>
        </template>

        <template v-else-if="activeView === 'data'">
          <section class="data-overview-grid"><article class="quality-score-card"><div class="score-ring"><strong>{{ qualityScore.toFixed(2) }}</strong><small>综合评分</small></div><div><span class="tag success"><AppIcon name="check" :size="12" /> 数据质量优秀</span><h2>医疗数据质量评估</h2><p>依据完整性、准确性、一致性与时效性四个维度综合计算。</p></div></article><article class="panel quality-bars"><div class="panel-head"><div><h2>质量维度</h2><p>最近一次评估：{{ lastIngestion?.finished_at?.replace('T', ' ') || '暂无记录' }}</p></div></div><div v-for="item in qualityItems" :key="item.label" class="quality-row"><span>{{ item.label }}</span><div><i :style="{ width: `${item.value}%` }"></i></div><strong>{{ item.text }}</strong></div></article></section>
          <section class="metric-grid data-metrics"><article class="mini-stat"><span>数据总量</span><strong>{{ formatNumber(totalRecords) }}</strong><small>全量清洗后记录</small></article><article class="mini-stat"><span>标准字段</span><strong>33</strong><small>6 个业务主题域</small></article><article class="mini-stat"><span>清洗通过率</span><strong>{{ qualityReport.uniqueness ? `${(qualityReport.uniqueness * 100).toFixed(2)}%` : '—' }}</strong><small>过滤 {{ formatNumber(lastIngestion?.rows_dropped) }} 条</small></article><article class="mini-stat"><span>数据库状态</span><strong>{{ apiConnected ? '正常' : '异常' }}</strong><small>SQL Server 2022</small></article></section>
          <section class="panel data-table-panel"><div class="panel-head"><div><h2>数据接入任务</h2><p>监控各数据源的同步与处理状态</p></div><button class="primary-button" :disabled="dataLoading" @click="loadDashboard"><AppIcon name="refresh" :size="14" /> {{ dataLoading ? '同步中' : '刷新状态' }}</button></div><div class="table-wrap"><table><thead><tr><th>数据源</th><th>接入类型</th><th>记录数</th><th>更新时间</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="row in pipelineRows" :key="row.source"><td><span class="source-icon"><AppIcon name="database" :size="15" /></span><strong>{{ row.source }}</strong></td><td>{{ row.type }}</td><td>{{ row.records }}</td><td>{{ row.updated }}</td><td><em class="status-tag" :class="row.status.includes('异常') ? 'syncing' : ''">{{ row.status }}</em></td><td><button class="row-action"><AppIcon name="arrow-right" :size="14" /></button></td></tr></tbody></table></div></section>
          <section class="pipeline"><div class="pipeline-head"><h2>数据处理链路</h2><p>从原始数据接入到分析服务的完整流程</p></div><div class="pipeline-steps"><div v-for="(step, index) in ['数据接入', '清洗标准化', '质量校验', 'SQL Server 入库', '分析服务']" :key="step" class="pipeline-step"><span><AppIcon :name="index === 4 ? 'activity' : index === 3 ? 'database' : 'check'" :size="18" /></span><strong>{{ step }}</strong><small>{{ index === 0 ? 'CSV / JSON' : index === 1 ? 'Pandas / BULK' : index === 2 ? '四维评估' : index === 3 ? '结构化存储' : 'RESTful API' }}</small></div></div></section>
        </template>

        <template v-else-if="activeView === 'patients'">
          <section class="patient-banner"><div><span>患者群体概览</span><strong>{{ formatNumber(totalRecords) }} <small>出院记录</small></strong><p>当前分析周期：2021 年完整数据</p></div><div class="banner-stat"><span>主要年龄组</span><strong>{{ topAgeGroup }}</strong></div><div class="banner-stat"><span>首位疾病</span><strong>{{ topDiseaseName }}</strong></div><div class="banner-stat"><span>质量评分</span><strong>{{ qualityScore.toFixed(2) }}%</strong></div></section>
          <section class="dashboard-grid patient-charts"><article class="panel"><div class="panel-head"><div><h2>年龄段分布</h2><p>患者人口统计学结构</p></div></div><DashboardChart :option="ageOption" height="290px" /></article><article class="panel"><div class="panel-head"><div><h2>性别构成</h2><p>住院出院记录占比</p></div></div><div class="gender-chart-wrap"><DashboardChart :option="genderOption" height="260px" /><div class="gender-legend"><span v-for="item in genderLegend" :key="item.label"><i :class="item.className"></i>{{ item.label }} <strong>{{ item.percent }}%</strong></span></div></div></article><article class="panel"><div class="panel-head"><div><h2>病情严重程度</h2><p>APR 严重程度分级</p></div></div><DashboardChart :option="mortalityOption" height="290px" /></article></section>
          <section class="patient-segments"><div class="panel-head"><div><h2>重点患者分群</h2><p>基于年龄、疾病与严重程度的实时聚合结果</p></div><button class="text-button" @click="selectView('ai')">使用 AI 深入分析 <AppIcon name="arrow-right" :size="14" /></button></div><div class="segment-grid"><article v-for="segment in patientSegments" :key="segment.title"><span class="segment-icon" :class="segment.tone"><AppIcon :name="segment.icon" :size="19" /></span><div><strong>{{ segment.title }}</strong><p>{{ segment.detail }}</p><small>{{ formatNumber(segment.count) }} 条 · 占 {{ Number(segment.ratio || 0).toFixed(1) }}%</small></div></article></div></section>
        </template>

        <template v-else-if="activeView === 'reports'">
          <section class="report-toolbar"><div class="report-tabs"><button class="active">全部报告 <span>4</span></button><button>运营分析</button><button>费用分析</button><button>数据质量</button></div><button class="primary-button" :disabled="reportLoading" @click="generateReport"><AppIcon name="sparkle" :size="15" /> {{ reportLoading ? '生成中' : 'AI 生成报告' }}</button></section>
          <section class="report-grid"><article v-for="report in reportCards" :key="report.title" class="report-card"><div class="report-cover" :class="report.color"><span class="report-type">{{ report.type }}</span><AppIcon :name="report.icon" :size="42" :stroke-width="1.4" /><i></i><i></i><i></i></div><div class="report-body"><small>{{ report.date }}</small><h2>{{ report.title }}</h2><p>{{ report.desc }}</p><div><button @click="generateReport">生成报告 <AppIcon name="arrow-right" :size="13" /></button><button class="icon-button" :disabled="!reportContent" @click="downloadReport"><AppIcon name="download" :size="15" /></button></div></div></article></section>
          <section v-if="reportContent" class="panel generated-report"><div class="panel-head"><div><h2>最新生成报告</h2><p>Markdown 实时预览</p></div><div class="result-actions"><button v-if="can('system:manage') && reportId" title="发布为公开报告" @click="publishGeneratedReport"><AppIcon name="check" :size="15" /></button><button @click="downloadReport"><AppIcon name="download" :size="15" /></button><button @click="reportContent = ''; reportId = null"><AppIcon name="close" :size="15" /></button></div></div><pre>{{ reportContent }}</pre></section>
          <section class="panel recent-reports"><div class="panel-head"><div><h2>最近生成记录</h2><p>平台自动与手动生成的报告任务</p></div></div><div class="activity-list"><div><span class="activity-icon"><AppIcon name="file-chart" :size="17" /></span><div><strong>医疗运营综合分析报告</strong><p>支持基于当前 SQL Server 数据实时生成</p></div><em class="status-tag">可生成</em></div><div><span class="activity-icon"><AppIcon name="sparkle" :size="17" /></span><div><strong>重点疾病费用分析</strong><p>由 DeepSeek V4 Flash 生成摘要</p></div><em class="status-tag">可生成</em></div><div><span class="activity-icon"><AppIcon name="shield" :size="17" /></span><div><strong>住院数据质量报告</strong><p>系统在每次全量导入后自动评估</p></div><em class="status-tag">已完成</em></div></div></section>
        </template>
      </main>
    </section>
  </div>
</template>

<style>
:root { --ink:#23323b;--muted:#75828c;--teal:#176f6a;--teal-2:#278f86;--teal-soft:#eaf6f4;--surface:#fff;--bg:#f4f6f6;--line:#e4e9eb;--shadow:0 1px 2px rgba(31,45,52,.03),0 8px 26px rgba(31,45,52,.035) }
*{box-sizing:border-box;margin:0;padding:0}html{background:var(--bg)}body{min-width:320px;color:var(--ink);background:var(--bg);font-family:Inter,"SF Pro Display","Segoe UI","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}button,input,select,textarea{font:inherit}button{color:inherit}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid rgba(23,111,106,.35);outline-offset:2px}
.app-shell{min-height:100vh}.sidebar{position:fixed;inset:0 auto 0 0;z-index:20;width:224px;display:flex;flex-direction:column;padding:0 14px 18px;color:#dbe8e6;background:#163c3b;border-right:1px solid rgba(255,255,255,.05)}.brand{height:76px;display:flex;align-items:center;gap:11px;padding:0 9px;border-bottom:1px solid rgba(255,255,255,.08)}.brand-mark{position:relative;width:34px;height:34px;border-radius:11px;background:#fff;box-shadow:0 4px 13px rgba(0,0,0,.12)}.brand-mark span{position:absolute;left:9px;top:15px;width:16px;height:4px;border-radius:3px;background:#1d8179}.brand-mark span:last-child{transform:rotate(90deg)}.brand strong{display:block;color:#fff;font-size:17px;letter-spacing:.08em}.brand small{display:block;margin-top:3px;font-size:7px;letter-spacing:.11em;color:#87aaa6}.side-label{margin:22px 12px 8px;color:#759895;font-size:10px;letter-spacing:.16em}.nav-list{display:grid;gap:5px}.nav-list button{width:100%;display:flex;align-items:center;gap:12px;padding:11px 12px;border:0;border-radius:9px;color:#a9c1bf;background:transparent;font-size:13px;text-align:left;cursor:pointer;transition:.2s}.nav-list button span{flex:1}.nav-list button em{min-width:26px;padding:2px 5px;color:#bde4df;background:rgba(100,205,192,.14);border:1px solid rgba(132,223,212,.15);border-radius:5px;font-size:8px;font-style:normal;text-align:center}.nav-list button:hover{color:#fff;background:rgba(255,255,255,.06)}.nav-list button.active{color:#fff;background:#275957;box-shadow:inset 3px 0 #63c4b9}.sidebar-spacer{flex:1}.data-status{margin-top:15px;padding:13px;border:1px solid rgba(255,255,255,.08);border-radius:11px;background:rgba(255,255,255,.035)}.status-row{display:flex;align-items:center;gap:7px}.status-row strong{color:#dce9e7;font-size:11px;font-weight:600}.status-dot{width:7px;height:7px;border-radius:50%;background:#61d4ac;box-shadow:0 0 0 4px rgba(97,212,172,.1)}.data-status p,.data-status small{color:#799b98;font-size:9px}.data-status p{margin-top:5px}.status-progress{height:3px;margin:12px 0 7px;overflow:hidden;border-radius:4px;background:rgba(255,255,255,.08)}.status-progress i{display:block;width:82%;height:100%;background:#5ac0b5}
.workspace{min-height:100vh;margin-left:224px}.topbar{position:sticky;top:0;z-index:15;height:66px;display:flex;align-items:center;justify-content:space-between;padding:0 30px;background:rgba(255,255,255,.94);border-bottom:1px solid var(--line);backdrop-filter:blur(14px)}.global-search{width:min(360px,38vw);display:flex;align-items:center;gap:9px;color:#8a979f}.global-search input{flex:1;border:0;outline:0;color:var(--ink);background:transparent;font-size:12px}.global-search input::placeholder{color:#9ca6ad}.global-search kbd{padding:3px 7px;border:1px solid #dfe4e7;border-radius:5px;background:#f8f9fa;color:#9aa4aa;font-size:9px;box-shadow:0 1px 0 #e3e6e8}.topbar-actions{display:flex;align-items:center;gap:14px}.demo-pill{display:flex;align-items:center;gap:7px;padding:6px 10px;color:#5b6a72;background:#f7f9f9;border:1px solid #e4e9ea;border-radius:20px;font-size:10px}.demo-pill span{width:6px;height:6px;background:#48b894;border-radius:50%}.icon-button{position:relative;display:grid;place-items:center;width:34px;height:34px;color:#677680;background:transparent;border:0;border-radius:9px;cursor:pointer}.icon-button:hover{background:#f1f4f4}.icon-button>i{position:absolute;right:6px;top:5px;width:6px;height:6px;border:1.5px solid #fff;border-radius:50%;background:#e26960}.profile{display:flex;align-items:center;gap:9px;padding-left:14px;border-left:1px solid #e8ebed}.profile .avatar{width:34px;height:34px;display:grid;place-items:center;color:#fff;background:linear-gradient(145deg,#317c77,#1d5c59);border-radius:10px;font-size:12px}.profile strong,.profile small{display:block}.profile strong{font-size:11px}.profile small{margin-top:2px;color:#9aa4aa;font-size:9px}.profile>svg{color:#9ba5ab}.mobile-menu{display:none;border:0;background:transparent}
.logout-button{padding:4px 6px;color:#7b8987;background:transparent;border:0;font-size:9px;cursor:pointer}.primary-row.single{grid-template-columns:1fr}
.content{width:min(1540px,100%);margin:0 auto;padding:29px 30px 46px}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:23px}.page-heading .eyebrow{margin-bottom:7px;color:#409088;font-size:8px;letter-spacing:.18em;font-weight:700}.page-heading h1{font-size:25px;line-height:1.25;letter-spacing:-.02em}.page-heading>div>span{display:block;margin-top:6px;color:var(--muted);font-size:12px}.filters{display:flex;align-items:center;gap:8px}.filters label{height:34px;display:flex;align-items:center;gap:7px;padding:0 10px;color:#687780;background:#fff;border:1px solid #dde3e5;border-radius:8px}.filters select{appearance:none;padding:0 4px 0 0;color:#53616a;background:transparent;border:0;outline:0;font-size:11px;cursor:pointer}.outline-button,.primary-button{height:34px;display:inline-flex;align-items:center;gap:7px;padding:0 12px;border-radius:8px;font-size:11px;cursor:pointer}.outline-button{color:#596871;background:#fff;border:1px solid #dde3e5}.outline-button:hover{border-color:#8bbdb8;color:var(--teal)}.primary-button{color:#fff;background:var(--teal);border:1px solid var(--teal)}.primary-button:hover{background:#125e5a}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.metric-card{position:relative;min-width:0;padding:17px 18px 15px 70px;background:#fff;border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow)}.metric-icon{position:absolute;left:18px;top:19px;width:38px;height:38px;display:grid;place-items:center;border-radius:10px}.metric-icon.teal{color:#16776f;background:#e5f4f1}.metric-icon.blue{color:#4f78aa;background:#edf3fa}.metric-icon.amber{color:#b37a2e;background:#fbf2e4}.metric-icon.violet{color:#7668a7;background:#f1eef9}.metric-top{display:flex;justify-content:space-between;align-items:center;color:#74818a;font-size:11px}.metric-top button,.panel-more{border:0;color:#a7b0b5;background:transparent;cursor:pointer;letter-spacing:2px}.metric-value{margin:8px 0 9px;color:#263740;font-size:25px;font-weight:700;letter-spacing:-.02em}.metric-value small{color:#75828b;font-size:10px;font-weight:500;letter-spacing:0}.metric-foot{display:flex;align-items:center;gap:6px;color:#96a0a6;font-size:9px}.metric-foot span{display:inline-flex;align-items:center;gap:2px;padding:3px 5px;border-radius:4px;font-weight:600}.metric-foot.up span,.metric-foot.down span{color:#158273;background:#e9f7f3}
.dashboard-grid{display:grid;gap:13px;margin-top:13px}.primary-row{grid-template-columns:minmax(0,1.75fr) minmax(330px,.95fr)}.secondary-row{grid-template-columns:repeat(3,minmax(0,1fr))}.panel{min-width:0;padding:18px 19px;background:#fff;border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow)}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:9px}.panel-head h2{color:#2c3c45;font-size:13px;font-weight:650}.panel-head p{margin-top:4px;color:#929ba1;font-size:9px}.text-button{display:inline-flex;align-items:center;gap:4px;padding:3px 0;color:#37817b;border:0;background:transparent;font-size:10px;cursor:pointer}.text-button:hover{color:#115d58}.ai-badge{display:flex;align-items:center;gap:4px;padding:5px 7px;color:#1b7c74;background:#e9f6f4;border-radius:6px;font-size:9px;font-weight:700}.insight-panel{padding-bottom:13px}.insight-list{display:grid}.insight-item{position:relative;display:flex;gap:11px;padding:12px 2px;border-top:1px solid #edf0f2}.insight-item:first-child{border-top:0}.insight-mark{width:4px;flex:0 0 4px;margin:2px 0;border-radius:4px}.insight-mark.teal{background:#42a59b}.insight-mark.amber{background:#e4ad5f}.insight-mark.blue{background:#7099ca}.insight-item em{display:inline-block;margin-bottom:4px;padding:2px 5px;border-radius:4px;font-size:8px;font-style:normal}.insight-item em.teal{color:#16766e;background:#e8f5f3}.insight-item em.amber{color:#a66d24;background:#fbf0df}.insight-item em.blue{color:#4d72a0;background:#edf3fa}.insight-item h3{font-size:11px}.insight-item p{margin-top:4px;color:#7f8a91;font-size:9px;line-height:1.55}.insight-item button{display:flex;align-items:center;gap:3px;margin-top:5px;color:#43827d;background:transparent;border:0;font-size:9px;cursor:pointer}
.data-table-panel{margin-top:13px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{padding:10px 12px;color:#929ba1;background:#f7f9f9;border-bottom:1px solid #e8ecee;font-size:9px;font-weight:500;text-align:left}td{padding:12px;color:#65727b;border-bottom:1px solid #edf0f1;font-size:10px}tbody tr:last-child td{border-bottom:0}td strong{color:#3b4a52;font-weight:600}.disease-dot{display:inline-block;width:6px;height:6px;margin-right:9px;border-radius:2px;background:#55aa9f}.positive,.negative{display:inline-block;padding:3px 6px;border-radius:5px;font-style:normal}.positive{color:#188174;background:#eaf6f3}.negative{color:#b35e58;background:#faeeee}.row-action{width:25px;height:25px;display:grid;place-items:center;color:#8d989f;background:transparent;border:1px solid #e2e6e8;border-radius:7px;cursor:pointer}
.ai-layout{display:grid;grid-template-columns:minmax(370px,.82fr) minmax(500px,1.18fr);gap:16px;align-items:stretch}.ai-chat-wrap,.ai-result-wrap{min-width:0}.section-title{display:flex;align-items:center;gap:11px;margin-bottom:12px}.title-icon{width:38px;height:38px;display:grid;place-items:center;color:#176f6a;background:#e5f3f1;border-radius:11px}.section-title h2{font-size:13px}.section-title p{margin-top:4px;color:#879199;font-size:9px}.ai-chat-wrap .chat-panel{height:550px}.ai-result-card{min-height:550px}.result-actions{display:flex;gap:5px}.result-actions button{width:28px;height:28px;display:grid;place-items:center;color:#7b878e;background:#f8f9f9;border:1px solid #e5e9eb;border-radius:7px;cursor:pointer}.ai-summary{display:flex;gap:10px;margin:15px 0 8px;padding:12px 13px;color:#47565f;background:#f0f8f6;border:1px solid #dbeeea;border-radius:10px;font-size:10px;line-height:1.7}.ai-summary span{color:#198077;margin-top:1px}.chart-note{padding-top:11px;border-top:1px solid #edf0f1;color:#929ba1;font-size:9px}.chart-note span{display:inline-block;margin-right:6px;color:#667780;font-weight:600}.quick-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.quick-facts article{padding:13px 14px;background:#fff;border:1px solid var(--line);border-radius:10px}.quick-facts span,.quick-facts small,.quick-facts strong{display:block}.quick-facts span{color:#929da3;font-size:9px}.quick-facts strong{margin:5px 0 3px;color:#31434c;font-size:15px}.quick-facts small{color:#9ca5aa;font-size:8px}
.ai-chart-empty{height:350px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#98a5aa;background:#f8faf9;border:1px dashed #d8e3e1;border-radius:10px;font-size:10px}.ai-chart-empty svg{color:#65a39d}
.data-overview-grid{display:grid;grid-template-columns:1fr 1.15fr;gap:13px}.quality-score-card{display:flex;align-items:center;gap:25px;padding:22px 26px;color:#fff;background:linear-gradient(130deg,#194f4c,#176f69);border-radius:14px;box-shadow:0 10px 30px rgba(18,86,81,.13)}.score-ring{width:112px;height:112px;display:flex;flex-direction:column;align-items:center;justify-content:center;flex:0 0 auto;border:8px solid rgba(255,255,255,.18);outline:3px solid rgba(87,211,193,.85);outline-offset:-6px;border-radius:50%}.score-ring strong{font-size:27px}.score-ring small{color:#afd4cf;font-size:8px}.quality-score-card .tag{display:inline-flex;align-items:center;gap:4px;padding:4px 7px;color:#bce8dc;background:rgba(255,255,255,.1);border-radius:5px;font-size:8px}.quality-score-card h2{margin:12px 0 7px;font-size:17px}.quality-score-card p{max-width:330px;color:#b6cfcc;font-size:10px;line-height:1.6}.quality-bars{padding-top:20px}.quality-row{display:grid;grid-template-columns:50px 1fr 42px;align-items:center;gap:10px;margin:13px 0;color:#66747d;font-size:9px}.quality-row>div{height:6px;overflow:hidden;background:#edf1f2;border-radius:5px}.quality-row i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#2b8d85,#61b9ae)}.quality-row strong{color:#4c5d65;font-size:9px;text-align:right}.data-metrics{margin-top:13px}.mini-stat{padding:16px 18px;background:#fff;border:1px solid var(--line);border-radius:11px}.mini-stat span,.mini-stat small,.mini-stat strong{display:block}.mini-stat span{color:#88949b;font-size:9px}.mini-stat strong{margin:7px 0 4px;font-size:20px}.mini-stat small{color:#8b989e;font-size:8px}.source-icon{display:inline-grid;place-items:center;width:27px;height:27px;margin-right:8px;color:#2b837c;background:#e9f5f3;border-radius:7px;vertical-align:middle}.status-tag{display:inline-block;padding:4px 7px;color:#208176;background:#e7f5f2;border-radius:5px;font-size:8px;font-style:normal}.status-tag.syncing{color:#a36c24;background:#fbf0df}.pipeline{margin-top:13px;padding:20px 22px;background:#fff;border:1px solid var(--line);border-radius:13px}.pipeline-head h2{font-size:13px}.pipeline-head p{margin-top:4px;color:#919ba1;font-size:9px}.pipeline-steps{display:grid;grid-template-columns:repeat(5,1fr);margin-top:20px}.pipeline-step{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center}.pipeline-step:not(:last-child)::after{content:"";position:absolute;left:calc(50% + 25px);top:19px;width:calc(100% - 50px);border-top:1px dashed #bad3d0}.pipeline-step>span{z-index:1;width:40px;height:40px;display:grid;place-items:center;color:#247f77;background:#edf7f5;border:1px solid #d9eeeb;border-radius:11px}.pipeline-step strong{margin-top:8px;font-size:10px}.pipeline-step small{margin-top:3px;color:#97a1a7;font-size:8px}
.patient-banner{display:grid;grid-template-columns:1.5fr repeat(3,.55fr);align-items:center;padding:22px 28px;color:#fff;background:linear-gradient(120deg,#1a504d,#1b716b);border-radius:14px;box-shadow:0 10px 30px rgba(18,86,81,.11)}.patient-banner>div:first-child>span{display:block;color:#9ccac5;font-size:9px}.patient-banner>div:first-child>strong{display:block;margin:7px 0 5px;font-size:27px}.patient-banner strong small{color:#bad5d2;font-size:10px;font-weight:400}.patient-banner p{color:#9fc0bd;font-size:9px}.banner-stat{padding-left:22px;border-left:1px solid rgba(255,255,255,.13)}.banner-stat span,.banner-stat strong{display:block}.banner-stat span{color:#a9c7c4;font-size:9px}.banner-stat strong{margin-top:7px;font-size:17px}.patient-charts{grid-template-columns:1.25fr .9fr 1.15fr}.gender-chart-wrap{display:grid;grid-template-columns:1fr auto;align-items:center}.gender-legend{display:grid;gap:12px}.gender-legend span{display:grid;grid-template-columns:7px 65px auto;align-items:center;gap:6px;color:#7f8b92;font-size:9px}.gender-legend i{width:7px;height:7px;border-radius:2px}.gender-legend i.female{background:#2a8f86}.gender-legend i.male{background:#7398c8}.gender-legend i.unknown{background:#d9dfe4}.gender-legend strong{color:#52616a;font-size:9px}.patient-segments{margin-top:13px;padding:20px;background:#fff;border:1px solid var(--line);border-radius:13px}.segment-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}.segment-grid article{display:flex;align-items:center;gap:13px;padding:15px;border:1px solid #e7ebed;border-radius:10px}.segment-icon{width:38px;height:38px;display:grid;place-items:center;flex:0 0 auto;border-radius:10px}.segment-icon.teal{color:#18786f;background:#e7f5f2}.segment-icon.amber{color:#ad762c;background:#fbf0df}.segment-icon.red{color:#b65d57;background:#faeceb}.segment-grid strong,.segment-grid p,.segment-grid small{display:block}.segment-grid strong{font-size:10px}.segment-grid p{margin:5px 0;color:#879199;font-size:8px}.segment-grid small{color:#527b76;font-size:8px}
.report-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.report-tabs{display:flex;gap:5px;padding:4px;background:#e9edee;border-radius:9px}.report-tabs button{padding:7px 12px;border:0;border-radius:6px;color:#758189;background:transparent;font-size:9px;cursor:pointer}.report-tabs button.active{color:#2f4a48;background:#fff;box-shadow:0 1px 4px rgba(31,45,52,.08)}.report-tabs span{margin-left:3px;color:#4f8b86}.report-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.report-card{overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);transition:.25s}.report-card:hover{transform:translateY(-3px);box-shadow:0 12px 28px rgba(31,45,52,.08)}.report-cover{position:relative;height:138px;display:flex;align-items:center;justify-content:center;overflow:hidden}.report-cover.teal{color:#4fa49b;background:#e8f4f2}.report-cover.blue{color:#6b91c2;background:#edf2f8}.report-cover.amber{color:#d09a50;background:#fbf1e3}.report-cover.violet{color:#8879b7;background:#f0edf7}.report-cover .report-type{position:absolute;left:13px;top:12px;padding:4px 7px;color:currentColor;background:rgba(255,255,255,.7);border-radius:5px;font-size:8px;font-weight:600}.report-cover i{position:absolute;height:1px;background:currentColor;opacity:.18}.report-cover i:nth-of-type(1){width:70%;left:15%;bottom:27px}.report-cover i:nth-of-type(2){width:48%;left:15%;bottom:20px}.report-cover i:nth-of-type(3){width:60%;left:15%;bottom:13px}.report-body{padding:16px}.report-body>small{color:#98a1a7;font-size:8px}.report-body h2{margin:7px 0;font-size:12px}.report-body p{min-height:39px;color:#7d8990;font-size:9px;line-height:1.55}.report-body>div{display:flex;align-items:center;justify-content:space-between;margin-top:13px;padding-top:11px;border-top:1px solid #edf0f1}.report-body>div>button:first-child{display:flex;align-items:center;gap:4px;color:#327c76;border:0;background:transparent;font-size:9px;cursor:pointer}.report-body .icon-button{width:27px;height:27px;border:1px solid #e4e8ea}.recent-reports{margin-top:13px}.activity-list>div{display:flex;align-items:center;gap:11px;padding:11px 0;border-top:1px solid #edf0f1}.activity-list>div:first-child{border-top:0}.activity-icon{width:31px;height:31px;display:grid;place-items:center;color:#287f78;background:#eaf5f3;border-radius:8px}.activity-list>div>div{flex:1}.activity-list strong{font-size:10px}.activity-list p{margin-top:4px;color:#959fa5;font-size:8px}
.api-error{display:flex;align-items:center;gap:8px;margin:-10px 0 16px;padding:10px 12px;color:#9b5a43;background:#fff5ee;border:1px solid #f0d8ca;border-radius:9px;font-size:10px}.status-dot.offline,.demo-pill span.offline{background:#d47669;box-shadow:0 0 0 4px rgba(212,118,105,.1)}.primary-button:disabled{cursor:wait;opacity:.62}.generated-report{margin-top:13px}.generated-report pre{max-height:520px;overflow:auto;margin:12px 0 0;padding:18px;color:#42545d;background:#f7f9f9;border:1px solid #e7ebed;border-radius:10px;font:11px/1.8 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}.mobile-overlay{display:none}@media(max-width:1180px){.metric-grid{grid-template-columns:repeat(2,1fr)}.primary-row{grid-template-columns:1fr}.secondary-row{grid-template-columns:repeat(2,1fr)}.secondary-row>:last-child{grid-column:span 2}.report-grid{grid-template-columns:repeat(2,1fr)}.patient-charts{grid-template-columns:1fr 1fr}.patient-charts>:last-child{grid-column:span 2}.ai-layout{grid-template-columns:1fr}.ai-chat-wrap .chat-panel{height:500px}}@media(max-width:800px){.sidebar{transform:translateX(-100%);transition:transform .25s}.sidebar.open{transform:translateX(0)}.workspace{margin-left:0}.mobile-overlay{position:fixed;inset:0;z-index:19;display:block;background:rgba(17,32,34,.42);backdrop-filter:blur(2px)}.mobile-menu{display:block}.topbar{height:60px;padding:0 18px}.global-search{display:none}.demo-pill,.profile>div:not(.avatar),.profile>svg{display:none}.profile{padding-left:8px}.content{padding:23px 17px 38px}.page-heading{align-items:flex-start;flex-direction:column}.filters{width:100%;overflow-x:auto}.metric-grid,.secondary-row,.data-overview-grid,.patient-charts,.segment-grid{grid-template-columns:1fr}.secondary-row>:last-child,.patient-charts>:last-child{grid-column:auto}.patient-banner{grid-template-columns:1fr 1fr;gap:20px}.patient-banner>div:first-child{grid-column:span 2}.banner-stat{padding-left:0;border-left:0}.report-grid{grid-template-columns:1fr}.pipeline-steps{grid-template-columns:1fr;gap:10px}.pipeline-step{align-items:flex-start;padding-left:50px;text-align:left}.pipeline-step>span{position:absolute;left:0}.pipeline-step:not(:last-child)::after{left:19px;top:40px;width:1px;height:calc(100% - 30px);border-top:0;border-left:1px dashed #bad3d0}.gender-chart-wrap{grid-template-columns:1fr}.gender-legend{grid-template-columns:repeat(3,1fr)}.gender-legend span{grid-template-columns:7px 1fr}.gender-legend strong{grid-column:2}.report-toolbar{align-items:flex-start;gap:10px;flex-direction:column}.report-tabs{max-width:100%;overflow-x:auto}.ai-layout{display:block}.ai-result-wrap{margin-top:15px}.quick-facts{grid-template-columns:1fr}.page-heading h1{font-size:22px}}@media(max-width:480px){.metric-grid{grid-template-columns:1fr}.metric-card{padding-left:68px}.filters label:first-child{display:none}.patient-banner{grid-template-columns:1fr}.patient-banner>div:first-child{grid-column:auto}.quality-score-card{align-items:flex-start;flex-direction:column}.report-tabs button{white-space:nowrap}.gender-legend{grid-template-columns:1fr}.topbar-actions{gap:5px}.content{padding-inline:12px}}
</style>

<style>
.cost-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.75fr);gap:15px;align-items:start}
.cost-form-panel{padding:21px 23px}.model-badge{padding:5px 8px;color:#277d75;background:#e7f5f2;border-radius:6px;font-size:9px;font-weight:700}
.cost-form-section{margin-top:18px;padding-top:16px;border-top:1px solid #edf0f1}.cost-form-section:first-child{margin-top:8px;padding-top:0;border-top:0}.cost-form-section h3{margin-bottom:12px;color:#41535c;font-size:11px}
.cost-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px 13px}.cost-field-grid label{display:grid;gap:6px;color:#68767f;font-size:9px}.cost-field-grid label.wide{grid-column:span 2}
.cost-field-grid input,.cost-field-grid select{width:100%;height:37px;padding:0 10px;color:#33464f;background:#fafcfc;border:1px solid #dfe6e8;border-radius:7px;outline:0;font-size:10px;transition:.2s}.cost-field-grid input:focus,.cost-field-grid select:focus{border-color:#5aa79f;box-shadow:0 0 0 3px rgba(42,143,134,.09)}
.cost-error{display:flex;align-items:center;gap:7px;margin-top:14px;padding:10px;color:#a65c4f;background:#fff2f0;border:1px solid #f0d1cc;border-radius:8px;font-size:9px}.cost-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}
.cost-result-column{display:grid;gap:13px;position:sticky;top:80px}.cost-result-card{padding:27px;color:#fff;background:linear-gradient(135deg,#164f4b,#19776f);border-radius:14px;box-shadow:0 14px 34px rgba(22,86,80,.16)}
.result-kicker{color:#9fd2cc;font-size:8px;font-weight:700;letter-spacing:1.2px}.cost-result-card>p{margin-top:12px;color:#c4dedb;font-size:10px}.cost-result-card>strong{display:block;margin:8px 0 22px;font-size:32px;letter-spacing:-1px}
.cost-band{display:grid;gap:6px;padding-top:17px;border-top:1px solid rgba(255,255,255,.15)}.cost-band span{color:#a9ceca;font-size:9px}.cost-band b{font-size:12px}.cost-band small{color:#9abbb8;font-size:8px;line-height:1.5}
.cost-empty{display:grid;justify-items:center;padding:45px 25px;text-align:center}.cost-empty>span{width:58px;height:58px;display:grid;place-items:center;color:#2c8b82;background:#e9f6f4;border-radius:16px}.cost-empty h2{margin:15px 0 7px;font-size:13px}.cost-empty p{max-width:240px;color:#87939a;font-size:9px;line-height:1.7}
.model-metrics-card{padding:19px}.model-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-top:14px}.model-metrics>div{padding:12px;background:#f7f9f9;border:1px solid #e8edee;border-radius:8px}.model-metrics span,.model-metrics strong{display:block}.model-metrics span{color:#879299;font-size:8px}.model-metrics strong{margin-top:5px;color:#344950;font-size:12px}
.cost-safety-note{display:flex;align-items:flex-start;gap:10px;padding:14px;color:#77653f;background:#fffaf0;border:1px solid #eee1c5;border-radius:10px}.cost-safety-note>svg{flex:0 0 auto;color:#a77b35}.cost-safety-note strong{font-size:9px}.cost-safety-note p{margin-top:5px;font-size:8px;line-height:1.65}
@media(max-width:1180px){.cost-layout{grid-template-columns:1fr}.cost-result-column{position:static;grid-template-columns:1fr 1fr}.cost-safety-note{grid-column:span 2}}
@media(max-width:800px){.cost-result-column{grid-template-columns:1fr}.cost-safety-note{grid-column:auto}}
@media(max-width:480px){.cost-form-panel{padding:17px 14px}.cost-field-grid{grid-template-columns:1fr}.cost-field-grid label.wide{grid-column:auto}.cost-result-card>strong{font-size:27px}}
</style>
