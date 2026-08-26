<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import ChatPanel from './components/ChatPanel.vue'
import DashboardChart from './components/DashboardChart.vue'
import AccountSettings from './views/AccountSettings.vue'
import PublicReports from './views/PublicReports.vue'
import suggestionCatalog from '../../config/ai_suggestions.json'
import diseaseDictionary from '../../config/disease_dictionary.json'
import diseaseDisplayNames from '../../config/disease_display_names.json'
import { analyticsQuery, analyticsTopic, compareHospitals, costPredictionOptions, createReport, dataQuality, dimensionValues, fieldQuality, forecastAnnualBudget, getReport, health, listHospitals, listNotifications, listReports, overview, predictCost, predictFutureCost, publishReport, streamChat, withdrawReport } from './api/client'
import { authState, can, logout } from './auth'

const route = useRoute()
const router = useRouter()
const activeView = computed(() => String(route.name || 'overview'))
const dateRange = ref('all')
const availableYears = ref([2024, 2023, 2022, 2021])
const regionFilter = ref('全部服务区域')
const mobileMenuOpen = ref(false)
const loading = ref(false)
const dataLoading = ref(false)
const apiConnected = ref(false)
const apiError = ref('')
const messages = ref([])
const conversationId = ref(null)
const dashboard = ref({ summary: {}, trend: [], diseases: [], ages: [], payments: [], genders: [], severity: [] })
const comparisonTrend = ref([])
const diseaseBurden = ref([])
const regionalOperations = ref([])
const diseaseGrowth = ref([])
const diseaseRankingViews = ref({ growth: [], decline: [], absolute: [] })
const rankingCompatibilityMode = ref(false)
const growthMode = ref('growth')
const drilldownDisease = ref('')
const regionalComparison = ref([])
const compareOpen = ref(false)
const comparisonType = ref('year')
const comparisonA = ref('')
const comparisonB = ref('')
const hospitalOptions = ref([])
const hospitalComparison = ref(null)
const hospitalComparisonLoading = ref(false)
const hospitalComparisonError = ref('')
const expandedChartKey = ref('')
const insightsLoading = ref(false)
const insightsError = ref('')
const qualityReport = ref({})
const lastIngestion = ref(null)
const qualityMatrix = ref({ years: [], fields: [], field_count: 0 })
const qualityMatrixLoading = ref(false)
const qualityMatrixError = ref('')
const qualityDomain = ref('all')
const qualitySort = ref('score')
const patientDashboard = ref({ summary: {}, trend: [], diseases: [], ages: [], payments: [], genders: [], severity: [] })
const patientLoading = ref(false)
const patientError = ref('')
const patientDiseaseOptions = ref([])
const patientHospitalOptions = ref([])
const patientFilters = reactive({ year: 'all', service_area: '', disease: '', hospital: '', age_group: '', gender: '' })
const reportContent = ref('')
const reportId = ref(null)
const reportTitle = ref('')
const reportLoading = ref(false)
const reportLibrary = ref([])
const reportLibraryLoading = ref(false)
const reportLibraryError = ref('')
const reportFilter = ref('all')
const lastResponseMs = ref(0)
const searchQuery = ref('')
const costLoading = ref(false)
const costError = ref('')
const costResult = ref(null)
const budgetResult = ref(null)
const costMode = ref('encoded')
const costOptions = ref({ diagnosis: [], procedure: [], apr_drg: [], apr_mdc: [] })
const budgetHospitalOptions = ref([])
const futureForecastYear = ref(2025)
const futureGrowthRate = ref('')
const budgetForm = reactive({
  scope_type: 'service_area', scope_value: 'New York City', target_year: 2025,
  annual_volume_growth_rate: '', annual_cost_growth_rate: '',
})
const unreadNotifications = ref(0)
let notificationTimer = null
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
  { id: 'public-reports', label: '公开报告', icon: 'report', permission: 'report:public:read' },
  { id: 'account', label: '账户设置', icon: 'settings' },
].filter((item) => (!item.permission || can(item.permission)) && (!item.anyPermission || item.anyPermission.some(can))))
const viewMeta = {
  overview: { title: '医疗运营总览', subtitle: '聚合住院、费用与资源利用指标，辅助管理决策' },
  ai: { title: 'AI 智能分析', subtitle: '用自然语言探索医疗大数据，快速生成洞察与图表' },
  'cost-prediction': { title: '住院费用预测', subtitle: '基于已编码住院信息估算最终总成本及误差范围' },
  data: { title: '数据资产中心', subtitle: '追踪数据接入、治理质量与服务状态' },
  patients: { title: '患者画像分析', subtitle: '从人口统计学与就诊特征理解患者群体' },
  reports: { title: '分析报告', subtitle: '沉淀专题洞察，形成可复用的决策依据' },
  'public-reports': { title: '公开健康分析报告', subtitle: '浏览基于脱敏聚合数据发布的健康分析内容' },
  account: { title: '账户设置', subtitle: '查看账户资料与管理账号安全选项' },
}
const currentMeta = computed(() => viewMeta[activeView.value] || viewMeta.overview)
const formatNumber = (value, digits = 0) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: digits })
const formatOptionalNumber = (value, digits = 0) => value == null || value === '' || !Number.isFinite(Number(value)) ? '—' : formatNumber(value, digits)
const formatMoney = (value) => `US$${formatNumber(value, 0)}`
const formatCost = (value) => `US$${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const diseaseNameMap = new Map([
  ...Object.entries(diseaseDisplayNames).map(([name, chinese]) => [name.trim().toUpperCase(), chinese]),
  ...diseaseDictionary.flatMap((item) => [item.code, item.canonical, item.english, ...(item.aliases || [])]
    .filter(Boolean).map((name) => [String(name).trim().toUpperCase(), item.chinese])),
])
const formatDiseaseName = (value) => {
  const raw = String(value || '').trim()
  return diseaseNameMap.get(raw.toUpperCase()) || raw || '未标注'
}
const rawDiseaseFromChartEvent = (event) => event?.data?.rawDisease || event?.name || ''
const totalRecords = computed(() => Number(dashboard.value.summary?.discharges || 0))
const patientTotalRecords = computed(() => Number(patientDashboard.value.summary?.discharges || 0))
const profileSource = computed(() => activeView.value === 'patients' ? patientDashboard.value : dashboard.value)
const activeFilterChips = computed(() => [
  ...(regionFilter.value !== '全部服务区域' ? [{ key: 'region', label: `区域：${regionFilter.value}` }] : []),
  ...(dateRange.value !== 'all' ? [{ key: 'year', label: `年份：${dateRange.value}` }] : []),
  ...(drilldownDisease.value ? [{ key: 'disease', label: `疾病：${formatDiseaseName(drilldownDisease.value)}` }] : []),
])
const qualityScore = computed(() => Number(qualityReport.value.overall || 0) * 100)
const topAgeGroup = computed(() => [...(patientDashboard.value.ages || [])].sort((a, b) => b.count - a.count)[0]?.dimension_value || '暂无')
const topDiseaseName = computed(() => formatDiseaseName(patientDashboard.value.diseases?.[0]?.dimension_value || '暂无'))
const patientPeriodLabel = computed(() => patientFilters.year === 'all' ? `${Math.min(...availableYears.value)}—${Math.max(...availableYears.value)} 年` : `${patientFilters.year} 年`)
const aiSuggestions = computed(() => {
  if (can('analytics:financial')) return suggestionCatalog.admin
  if (can('ai:advanced')) return suggestionCatalog.doctor
  return suggestionCatalog.patient
})

const selectedComparison = computed(() => {
  const rows = comparisonTrend.value
    .map((row) => ({ ...row, year: row.year ?? row.dimension_value }))
    .filter((row) => Number.isInteger(Number(row.year)))
    .sort((a, b) => Number(a.year) - Number(b.year))
  const requestedYear = dateRange.value === 'all' ? Number(rows.at(-1)?.year) : Number(dateRange.value)
  const currentIndex = rows.findIndex((row) => Number(row.year) === requestedYear)
  return { current: rows[currentIndex] || null, previous: currentIndex > 0 ? rows[currentIndex - 1] : null }
})
function yoy(metric) {
  const current = Number(selectedComparison.value.current?.[metric])
  const previous = Number(selectedComparison.value.previous?.[metric])
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return null
  return (current / previous - 1) * 100
}
function trendMeta(metric) {
  const change = yoy(metric)
  const currentYear = selectedComparison.value.current?.year
  const previousYear = selectedComparison.value.previous?.year
  return {
    trend: change == null ? '暂无同比' : `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`,
    direction: change == null || change >= 0 ? 'up' : 'down',
    note: currentYear && previousYear ? `${currentYear} 对 ${previousYear}` : '当前筛选范围',
  }
}
const metrics = computed(() => {
  const current = selectedComparison.value.current || dashboard.value.summary || {}
  const cards = [
    { label: '最新年度出院记录', value: formatNumber(current.count ?? totalRecords.value), unit: '条', ...trendMeta('count'), icon: 'activity', tone: 'teal' },
    { label: '平均住院日', value: formatNumber(current.avg_length_of_stay ?? dashboard.value.summary?.avg_length_of_stay, 2), unit: '天', ...trendMeta('avg_length_of_stay'), icon: 'clock', tone: 'blue' },
    { label: '次均账单费用', value: formatNumber(current.avg_total_charges ?? dashboard.value.summary?.avg_total_charges), unit: '美元', ...trendMeta('avg_total_charges'), icon: 'wallet', tone: 'amber' },
  ]
  if (authState.user?.role !== 'patient') cards.push({ label: '次均实际成本', value: formatOptionalNumber(current.avg_total_costs, 0), unit: '美元', ...trendMeta('avg_total_costs'), icon: 'wallet', tone: 'violet' })
  else cards.push({ label: '覆盖医疗机构', value: formatNumber(dashboard.value.summary?.facilities), unit: '家', trend: '全量覆盖', direction: 'up', note: '当前筛选去重机构数', icon: 'hospital', tone: 'violet' })
  return cards
})

const insightItems = computed(() => {
  const topDisease = dashboard.value.diseases?.[0]
  const topAge = [...(dashboard.value.ages || [])].sort((a, b) => b.count - a.count)[0]
  return [
    { tag: '人群结构', color: 'teal', title: `${topAge?.dimension_value || '主要年龄组'}患者占比最高`, text: `该组共 ${formatNumber(topAge?.count)} 条记录，平均住院日 ${formatNumber(topAge?.avg_length_of_stay, 1)} 天。`, action: '查看患者画像' },
    { tag: '疾病负担', color: 'amber', title: '重点疾病住院量集中', text: `${formatDiseaseName(topDisease?.dimension_value || '首位疾病')}记录数为 ${formatNumber(topDisease?.count)}，次均费用约 ${formatMoney(topDisease?.avg_total_charges)}。`, action: '查看费用分析' },
    { tag: '数据质量', color: 'blue', title: `综合质量评分 ${qualityScore.value.toFixed(2)}%`, text: `本次全量导入 ${formatNumber(lastIngestion.value?.rows_inserted || totalRecords.value)} 条，四维质量评估已完成。`, action: '生成专题报告' },
  ]
})

const diseaseRows = computed(() => {
  const growthByDisease = new Map(diseaseRankingViews.value.growth.map((row) => [row.dimension_value, row.growth_pct]))
  return (dashboard.value.diseases || []).slice(0, 8).map((row) => {
    const change = Number(growthByDisease.get(row.dimension_value))
    return {
      rawName: row.dimension_value || '', name: formatDiseaseName(row.dimension_value), count: formatNumber(row.count), days: formatNumber(row.avg_length_of_stay, 1), cost: formatMoney(row.avg_total_charges),
      change: Number.isFinite(change) ? `${change >= 0 ? '+' : ''}${change.toFixed(1)}%` : '—',
    }
  })
})
const qualityItems = computed(() => [
  ['完整性', 'completeness'], ['准确性', 'accuracy'], ['一致性', 'consistency'], ['时效性', 'timeliness'],
].map(([label, key]) => ({ label, value: Number(qualityReport.value[key] || 0) * 100, text: `${(Number(qualityReport.value[key] || 0) * 100).toFixed(2)}%` })))
const qualityDomains = computed(() => [...new Set((qualityMatrix.value.fields || []).map((item) => item.domain))])
const visibleQualityFields = computed(() => {
  const rows = (qualityMatrix.value.fields || []).filter((item) => qualityDomain.value === 'all' || item.domain === qualityDomain.value)
  const value = (item) => item.conditional ? item.coverage_pct : item.score_pct
  return [...rows].sort((a, b) => qualitySort.value === 'change'
    ? Number(a.change_pct ?? 0) - Number(b.change_pct ?? 0)
    : Number(value(a) ?? -1) - Number(value(b) ?? -1))
})
const pipelineRows = computed(() => [
  { source: '住院出院记录', type: 'CSV · 33 字段', records: formatNumber(lastIngestion.value?.rows_inserted || totalRecords.value), updated: lastIngestion.value?.finished_at?.replace('T', ' ') || '已完成', status: '已完成' },
  { source: 'SQL Server 主库', type: 'SQL Server 2022', records: formatNumber(totalRecords.value), updated: '实时可查询', status: apiConnected.value ? '已完成' : '连接异常' },
  { source: '疾病 CCSR 维度', type: '聚合索引', records: formatNumber(dashboard.value.diseases?.length), updated: '按需计算', status: '已完成' },
  { source: 'DeepSeek V4 Flash', type: 'Anthropic SSE', records: '流式', updated: '按需调用', status: '已完成' },
])
const reportCards = [
  { category: 'operations', type: '运营分析', title: '医疗运营综合分析报告', date: '实时生成', desc: '覆盖住院量、住院效率、费用结构与重点疾病变化。', icon: 'file-chart', color: 'teal' },
  { category: 'operations', type: '患者画像', title: '重点患者群体结构分析', date: '实时生成', desc: '聚焦年龄、性别与病情严重程度的患者群体结构。', icon: 'users', color: 'blue' },
  { category: 'cost', type: '费用分析', title: '重点疾病住院费用报告', date: '实时生成', desc: '识别住院量与次均费用较高的重点疾病组。', icon: 'wallet', color: 'amber' },
  { category: 'quality', type: '数据质量', title: '住院数据质量评估报告', date: '最近导入', desc: '从完整性、准确性、一致性和时效性四维评估。', icon: 'shield', color: 'violet' },
]
const reportTabs = [
  { id: 'all', label: '全部报告' },
  { id: 'operations', label: '运营分析' },
  { id: 'cost', label: '费用分析' },
  { id: 'quality', label: '数据质量' },
]
const filteredReportCards = computed(() => reportFilter.value === 'all'
  ? reportCards
  : reportCards.filter((report) => report.category === reportFilter.value))
const selectedReportTab = computed(() => reportTabs.find((tab) => tab.id === reportFilter.value) || reportTabs[0])
const reportTabCount = (tabId) => tabId === 'all'
  ? reportCards.length
  : reportCards.filter((report) => report.category === tabId).length

const axisStyle = { axisLine: { lineStyle: { color: '#dfe5e8' } }, axisTick: { show: false }, axisLabel: { color: '#7b8792', fontSize: 11 } }
const tooltipStyle = { backgroundColor: '#213038', borderWidth: 0, textStyle: { color: '#fff', fontSize: 12 }, padding: [9, 12] }
const ratioRows = (rows) => { const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0); return rows.map((row) => ({ ...row, percent: total ? Number(row.count) / total * 100 : 0 })) }
const genderLegend = computed(() => { const labels = { F: '女性', M: '男性', U: '未知' }; const rows = ratioRows(profileSource.value.genders || []); return rows.map((row, i) => ({ label: labels[row.dimension_value] || '未知', percent: row.percent.toFixed(1), className: ['female', 'male', 'unknown'][i % 3] })) })
const patientSegments = computed(() => {
  const ages = ratioRows(patientDashboard.value.ages || [])
  const diseases = ratioRows(patientDashboard.value.diseases || [])
  const severity = ratioRows(patientDashboard.value.severity || [])
  const topAge = [...ages].sort((a, b) => b.count - a.count)[0] || {}
  const topDisease = [...diseases].sort((a, b) => b.count - a.count)[0] || {}
  const highRisk = severity.filter((row) => /major|extreme|重度|极重度/i.test(row.dimension_value || '')).reduce((sum, row) => sum + Number(row.count || 0), 0)
  return [
    { title: `${topAge.dimension_value || '主要年龄'}人群`, detail: '按年龄段住院记录自动识别', count: topAge.count, ratio: topAge.percent, icon: 'activity', tone: 'teal' },
    { title: '首位疾病人群', detail: formatDiseaseName(topDisease.dimension_value || '暂无疾病分组'), count: topDisease.count, ratio: topDisease.percent, icon: 'wallet', tone: 'amber' },
    { title: '较高严重程度人群', detail: 'APR Major / Extreme 分组', count: highRisk, ratio: patientTotalRecords.value ? highRisk / patientTotalRecords.value * 100 : 0, icon: 'shield', tone: 'red' },
  ]
})

const trendOption = computed(() => {
  const rows = dashboard.value.trend || []
  return { color: ['#17837a', '#86c9c1'], tooltip: { trigger: 'axis', ...tooltipStyle }, legend: { right: 0, top: 0, icon: 'circle', itemWidth: 8, data: ['出院记录', '平均住院日'] }, grid: { left: 12, right: 18, top: 42, bottom: 4, containLabel: true }, xAxis: { type: 'category', data: rows.map((r) => String(r.year)), ...axisStyle }, yAxis: [{ type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (v) => `${v / 10000}万` } }, { type: 'value', ...axisStyle, splitLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value} 天' } }], series: [{ name: '出院记录', type: 'bar', barMaxWidth: 52, data: rows.map((r) => r.count), itemStyle: { borderRadius: [6, 6, 0, 0] } }, { name: '平均住院日', type: 'line', yAxisIndex: 1, data: rows.map((r) => Number(r.avg_length_of_stay).toFixed(2)), symbolSize: 8, lineStyle: { width: 3 } }] }
})
const ageOption = computed(() => { const rows = ratioRows(profileSource.value.ages || []); return { tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 6, right: 16, top: 14, bottom: 3, containLabel: true }, xAxis: { type: 'value', max: Math.ceil(Math.max(10, ...rows.map((r) => r.percent)) / 5) * 5 + 5, ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}%' } }, yAxis: { type: 'category', data: rows.map((r) => r.dimension_value), ...axisStyle, axisLine: { show: false } }, series: [{ type: 'bar', barWidth: 10, data: rows.map((r) => Number(r.percent.toFixed(2))), label: { show: true, position: 'right', color: '#53616c', fontSize: 11, formatter: '{c}%' }, itemStyle: { color: (p) => ['#a4d9d3', '#76c5bc', '#43aa9e', '#17837a', '#0c625d'][p.dataIndex % 5], borderRadius: [0, 5, 5, 0] } }] } })
const paymentOption = computed(() => ({ tooltip: { trigger: 'item', ...tooltipStyle, formatter: '{b}<br/>{c}% · {d}%' }, legend: { orient: 'vertical', right: 0, top: 'middle', icon: 'circle', itemWidth: 8, itemGap: 12, textStyle: { color: '#66747e', fontSize: 10 } }, series: [{ type: 'pie', radius: ['50%', '74%'], center: ['35%', '50%'], padAngle: 2, label: { show: false }, data: (dashboard.value.payments || []).map((r, i) => ({ value: Number((Number(r.ratio || 0) * 100).toFixed(2)), name: r.payment || '未标注', itemStyle: { color: ['#17837a', '#5bb5aa', '#6f92c4', '#e1ad63', '#9d85bd', '#c5ced5'][i % 6] } })) }], graphic: [{ type: 'text', left: '31.5%', top: '43%', style: { text: '支付\n结构', textAlign: 'center', fill: '#50606a', fontSize: 13, lineHeight: 19, fontWeight: 600 } }] }))
const diseaseOption = computed(() => ({ tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 10, right: 38, top: 14, bottom: 2, containLabel: true }, xAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (v) => `${v / 1000}k` } }, yAxis: { type: 'category', inverse: true, data: (dashboard.value.diseases || []).map((r) => formatDiseaseName(r.dimension_value)), ...axisStyle, axisLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, width: 150, overflow: 'truncate' } }, series: [{ type: 'bar', barWidth: 12, data: (dashboard.value.diseases || []).map((r) => ({ value: r.count, rawDisease: r.dimension_value })), itemStyle: { color: '#2a8f86', borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: '#6c7983', fontSize: 10, formatter: (p) => `${(p.value / 1000).toFixed(1)}k` } }] }))
const genderOption = computed(() => { const labels = { F: '女性', M: '男性', U: '未知' }; return { tooltip: { trigger: 'item', ...tooltipStyle }, series: [{ type: 'pie', radius: ['56%', '78%'], center: ['50%', '50%'], label: { show: false }, data: (profileSource.value.genders || []).map((r, i) => ({ value: r.count, name: labels[r.dimension_value] || '未知', itemStyle: { color: ['#2a8f86', '#7398c8', '#d9dfe4'][i % 3] } })) }], graphic: [{ type: 'text', left: 'center', top: '42%', style: { text: `${formatNumber(activeView.value === 'patients' ? patientTotalRecords.value : totalRecords.value)}\n总记录`, textAlign: 'center', fill: '#33444e', fontSize: 12, lineHeight: 20, fontWeight: 600 } }] } })
const mortalityOption = computed(() => { const rows = ratioRows(profileSource.value.severity || []); return { tooltip: { trigger: 'axis', ...tooltipStyle }, grid: { left: 8, right: 15, top: 18, bottom: 2, containLabel: true }, xAxis: { type: 'category', data: rows.map((r) => r.dimension_value), ...axisStyle }, yAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}%' } }, series: [{ type: 'bar', barWidth: 30, data: rows.map((r) => Number(r.percent.toFixed(2))), itemStyle: { color: (p) => ['#9bd4ce', '#5eb8ae', '#e7b46d', '#d8796e'][p.dataIndex % 4], borderRadius: [5, 5, 0, 0] }, label: { show: true, position: 'top', color: '#6c7983', fontSize: 10, formatter: '{c}%' } }] } })

const burdenCostMetric = computed(() => authState.user?.role === 'patient' ? 'avg_total_charges' : 'avg_total_costs')
const burdenCostLabel = computed(() => burdenCostMetric.value === 'avg_total_costs' ? '次均实际成本' : '次均账单费用')
const activeDiseaseGrowth = computed(() => diseaseRankingViews.value[growthMode.value] || diseaseGrowth.value)
const growthModeMeta = computed(() => ({
  growth: { title: '疾病住院量增长榜', subtitle: '增长率最高', valueKey: 'growth_pct', unit: '%' },
  decline: { title: '疾病住院量下降榜', subtitle: '下降幅度最大', valueKey: 'growth_pct', unit: '%' },
  absolute: { title: '疾病住院量绝对变化榜', subtitle: '按绝对增减量排序', valueKey: 'absolute_growth', unit: '条' },
}[growthMode.value]))
const diseaseBurdenOption = computed(() => {
  const rows = diseaseBurden.value.filter((row) => Number(row.count) > 0)
  const counts = rows.map((row) => Number(row.count || 0))
  const median = (values) => { const sorted = values.filter(Number.isFinite).sort((a, b) => a - b); const middle = Math.floor(sorted.length / 2); return sorted.length ? (sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2) : 0 }
  const medianStay = median(rows.map((row) => Number(row.avg_length_of_stay)))
  const medianCost = median(rows.map((row) => Number(row[burdenCostMetric.value])))
  const minCount = Math.min(...counts, 0); const maxCount = Math.max(...counts, 1)
  const bubbleSize = (count) => 12 + Math.sqrt((Number(count) - minCount) / Math.max(maxCount - minCount, 1)) * 34
  return {
    tooltip: { ...tooltipStyle, formatter: ({ data }) => `${data.name}<br/>住院记录：${formatNumber(data.value[2])}<br/>平均住院日：${formatNumber(data.value[0], 2)} 天<br/>${burdenCostLabel.value}：${formatCost(data.value[1])}` },
    grid: { left: 16, right: 24, top: 20, bottom: 12, containLabel: true },
    xAxis: { type: 'value', name: '平均住院日（天）', nameLocation: 'middle', nameGap: 28, ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } } },
    yAxis: { type: 'value', name: `${burdenCostLabel.value}（USD）`, ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (value) => `$${formatNumber(value / 1000, 0)}k` } },
    series: [{ type: 'scatter', data: rows.map((row) => ({ name: formatDiseaseName(row.dimension_value), rawDisease: row.dimension_value, value: [Number(row.avg_length_of_stay || 0), Number(row[burdenCostMetric.value] || 0), Number(row.count || 0)], symbolSize: bubbleSize(row.count), itemStyle: { color: '#238d84', opacity: .72, borderColor: '#fff', borderWidth: 1 } })), emphasis: { focus: 'series', itemStyle: { opacity: 1 } }, markLine: { silent: true, symbol: 'none', lineStyle: { color: '#9ba7ac', type: 'dashed', width: 1 }, label: { color: '#7d898f', fontSize: 8, formatter: '中位基准' }, data: [{ xAxis: medianStay }, { yAxis: medianCost }] } }],
  }
})
const regionalHeatmapOption = computed(() => {
  const rows = regionalOperations.value.filter((row) => row.service_area && row.year)
  const years = [...new Set(rows.map((row) => String(row.year)))].sort()
  const regions = [...new Set(rows.map((row) => String(row.service_area)))].sort()
  const values = rows.map((row) => Number(row.count || 0))
  return {
    tooltip: { ...tooltipStyle, formatter: ({ data }) => `${data.meta.service_area} · ${data.meta.year}<br/>住院记录：${formatNumber(data.meta.count)}<br/>平均住院日：${formatNumber(data.meta.avg_length_of_stay, 2)} 天` },
    grid: { left: 18, right: 28, top: 12, bottom: 42, containLabel: true },
    xAxis: { type: 'category', data: years, ...axisStyle, splitArea: { show: true } },
    yAxis: { type: 'category', data: regions, ...axisStyle, axisLabel: { ...axisStyle.axisLabel, width: 112, overflow: 'truncate' }, splitArea: { show: true } },
    visualMap: { min: Math.min(...values, 0), max: Math.max(...values, 1), calculable: true, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 10, itemHeight: 86, textStyle: { color: '#74818a', fontSize: 9 }, inRange: { color: ['#edf7f5', '#94d2ca', '#17837a', '#0c5652'] } },
    series: [{ type: 'heatmap', data: rows.map((row) => ({ value: [years.indexOf(String(row.year)), regions.indexOf(String(row.service_area)), Number(row.count || 0)], meta: row })), label: { show: false }, emphasis: { itemStyle: { borderColor: '#263740', borderWidth: 1 } } }],
  }
})
const diseaseGrowthOption = computed(() => {
  const meta = growthModeMeta.value
  const rows = activeDiseaseGrowth.value.slice(0, 8).reverse()
  return {
    tooltip: { trigger: 'axis', ...tooltipStyle, formatter: (items) => { const row = rows[items[0]?.dataIndex]; return `${formatDiseaseName(row?.dimension_value)}<br/>${row?.baseline_year}：${formatNumber(row?.baseline_value)}<br/>${row?.latest_year}：${formatNumber(row?.latest_value)}<br/>增长率：${Number(row?.growth_pct || 0).toFixed(1)}%<br/>绝对变化：${Number(row?.absolute_growth || 0) >= 0 ? '+' : ''}${formatNumber(row?.absolute_growth)}` } },
    grid: { left: 12, right: 35, top: 10, bottom: 5, containLabel: true },
    xAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (value) => meta.unit === '%' ? `${value}%` : formatNumber(value) } },
    yAxis: { type: 'category', data: rows.map((row) => formatDiseaseName(row.dimension_value)), ...axisStyle, axisLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, width: 135, overflow: 'truncate' } },
    series: [{ type: 'bar', barWidth: 13, data: rows.map((row) => ({ value: Number(row[meta.valueKey] || 0), rawDisease: row.dimension_value })), itemStyle: { color: ({ value }) => value >= 0 ? '#3aa198' : '#d8796e', borderRadius: [0, 5, 5, 0] }, label: { show: true, position: 'right', color: '#65727b', fontSize: 9, formatter: ({ value }) => meta.unit === '%' ? `${value > 0 ? '+' : ''}${value.toFixed(1)}%` : `${value > 0 ? '+' : ''}${formatNumber(value)}` } }],
  }
})

const expandedChart = computed(() => ({
  burden: { title: '疾病负担四象限', subtitle: `平均住院日、${burdenCostLabel.value}与住院规模的综合观察`, option: diseaseBurdenOption.value, onSelect: (event) => drillIntoDisease(rawDiseaseFromChartEvent(event)) },
  regional: { title: '服务区域年度热力图', subtitle: '服务区域与年度住院记录对比', option: regionalHeatmapOption.value, onSelect: drillIntoHeatmap },
  growth: { title: growthModeMeta.value.title, subtitle: `${growthModeMeta.value.subtitle}，可悬停查看首末年度明细`, option: diseaseGrowthOption.value, onSelect: (event) => drillIntoDisease(rawDiseaseFromChartEvent(event)) },
  disease: { title: '重点疾病住院量', subtitle: '重点疾病住院记录规模对比', option: diseaseOption.value, onSelect: (event) => drillIntoDisease(rawDiseaseFromChartEvent(event)) },
  age: { title: '患者年龄结构', subtitle: '各年龄段住院记录占比', option: ageOption.value },
  payment: { title: '支付方式构成', subtitle: '主要支付类型分布', option: paymentOption.value },
})[expandedChartKey.value] || null)

function openExpandedChart(key) {
  expandedChartKey.value = key
  document.body.classList.add('chart-modal-open')
}
function closeExpandedChart() {
  expandedChartKey.value = ''
  document.body.classList.remove('chart-modal-open')
}
function selectExpandedChart(event) {
  const handler = expandedChart.value?.onSelect
  closeExpandedChart()
  handler?.(event)
}
function handleChartModalKeydown(event) {
  if (event.key === 'Escape' && expandedChartKey.value) closeExpandedChart()
}

const comparisonOptions = computed(() => {
  if (comparisonType.value === 'year') return comparisonTrend.value
    .map((row) => String(row.year ?? row.dimension_value)).filter((value) => value && value !== 'undefined')
    .sort((a, b) => Number(b) - Number(a)).map((value) => ({ value, label: `${value} 年` }))
  if (comparisonType.value === 'hospital') return hospitalOptions.value.map((row) => ({
    value: String(row.hospital), label: `${row.hospital} · ${row.service_area || '未标注区域'}${row.count == null ? '' : ` · ${formatNumber(row.count)}条`}`,
  }))
  return [...regionalComparison.value].sort((a, b) => Number(b.count || 0) - Number(a.count || 0))
    .map((row) => ({ value: String(row.service_area ?? row.dimension_value), label: String(row.service_area ?? row.dimension_value) }))
})
function comparisonSourceRows() {
  if (comparisonType.value === 'hospital') return (hospitalComparison.value?.hospitals || []).map((row) => ({ ...row, comparison_key: String(row.hospital) }))
  return comparisonType.value === 'year'
    ? comparisonTrend.value.map((row) => ({ ...row, comparison_key: String(row.year ?? row.dimension_value) }))
    : regionalComparison.value.map((row) => ({ ...row, comparison_key: String(row.service_area ?? row.dimension_value) }))
}
const comparisonRows = computed(() => {
  const rows = comparisonSourceRows()
  return { a: rows.find((row) => row.comparison_key === comparisonA.value), b: rows.find((row) => row.comparison_key === comparisonB.value) }
})
const comparisonMetricRows = computed(() => {
  const definitions = [
    { key: 'count', label: '住院记录', unit: '条', digits: 0 },
    { key: 'avg_length_of_stay', label: '平均住院日', unit: '天', digits: 2 },
    { key: 'avg_total_charges', label: '次均账单费用', unit: '美元', digits: 0 },
    ...(authState.user?.role === 'patient' ? [] : [{ key: 'avg_total_costs', label: '次均实际成本', unit: '美元', digits: 0 }]),
    ...(comparisonType.value === 'hospital' && authState.user?.role !== 'patient' ? [
      { key: 'costs_per_day', label: '每住院日成本', unit: '美元/天', digits: 0 },
      { key: 'ed_rate', label: '急诊来源占比', unit: '%', digits: 1 },
      { key: 'surgical_rate', label: '手术类病例占比', unit: '%', digits: 1 },
      { key: 'long_stay_rate', label: '30天以上住院占比', unit: '%', digits: 1 },
    ] : []),
  ]
  return definitions.map((metric) => {
  const a = Number(comparisonRows.value.a?.[metric.key]); const b = Number(comparisonRows.value.b?.[metric.key])
  const valid = Number.isFinite(a) && Number.isFinite(b)
  return { ...metric, a: valid ? a : null, b: valid ? b : null, delta: valid ? a - b : null, deltaPct: valid && b !== 0 ? (a / b - 1) * 100 : null }
  })
})
function pairedHospitalMix(key) {
  const mix = hospitalComparison.value?.mixes?.[key] || { a: [], b: [] }
  const a = new Map((mix.a || []).map((row) => [row.dimension_value, row]))
  const b = new Map((mix.b || []).map((row) => [row.dimension_value, row]))
  return [...new Set([...a.keys(), ...b.keys()])].map((name) => ({
    name, a: a.get(name)?.share_pct ?? 0, b: b.get(name)?.share_pct ?? 0,
    countA: a.get(name)?.count ?? 0, countB: b.get(name)?.count ?? 0,
  })).sort((left, right) => (right.countA + right.countB) - (left.countA + left.countB)).slice(0, 10)
}
const hospitalDiseaseMix = computed(() => pairedHospitalMix('disease').map((row) => ({ ...row, rawName: row.name, name: formatDiseaseName(row.name) })))
const hospitalSeverityMix = computed(() => pairedHospitalMix('severity'))
const hospitalAdmissionMix = computed(() => pairedHospitalMix('admission'))
const hospitalCaseMix = computed(() => ({
  a: hospitalComparison.value?.case_mix?.a?.[0] || null,
  b: hospitalComparison.value?.case_mix?.b?.[0] || null,
}))
const hospitalTrendOption = computed(() => {
  const trend = hospitalComparison.value?.yearly_trend || { a: [], b: [] }
  const years = [...new Set([...(trend.a || []), ...(trend.b || [])].map((row) => String(row.year)))].sort()
  const byYear = (rows, year, key) => rows.find((row) => String(row.year) === year)?.[key] ?? null
  return {
    color: ['#17837a', '#6f92c4', '#76c5bc', '#a9b9d0'],
    tooltip: { trigger: 'axis', ...tooltipStyle },
    legend: { top: 0, right: 0, textStyle: { color: '#6f7d85', fontSize: 9 } },
    grid: { left: 10, right: 12, top: 42, bottom: 6, containLabel: true },
    xAxis: { type: 'category', data: years, ...axisStyle },
    yAxis: [{ type: 'value', ...axisStyle, splitLine: { lineStyle: { color: '#edf1f3', type: 'dashed' } }, axisLabel: { ...axisStyle.axisLabel, formatter: (value) => `${formatNumber(value / 10000, 0)}万` } }, { type: 'value', ...axisStyle, splitLine: { show: false }, axisLabel: { ...axisStyle.axisLabel, formatter: '{value}天' } }],
    series: [
      { name: '医院A住院量', type: 'bar', data: years.map((year) => byYear(trend.a || [], year, 'count')), barMaxWidth: 30 },
      { name: '医院B住院量', type: 'bar', data: years.map((year) => byYear(trend.b || [], year, 'count')), barMaxWidth: 30 },
      { name: '医院A住院日', type: 'line', yAxisIndex: 1, data: years.map((year) => byYear(trend.a || [], year, 'avg_length_of_stay')), symbolSize: 6 },
      { name: '医院B住院日', type: 'line', yAxisIndex: 1, data: years.map((year) => byYear(trend.b || [], year, 'avg_length_of_stay')), symbolSize: 6 },
    ],
  }
})

function filters() {
  const selected = {}
  if (regionFilter.value !== '全部服务区域') selected.service_area = regionFilter.value
  if (dateRange.value !== 'all') selected.year = Number(dateRange.value)
  if (drilldownDisease.value) selected.disease = drilldownDisease.value
  return selected
}
function patientFilterPayload() {
  return Object.fromEntries(Object.entries(patientFilters)
    .filter(([, value]) => value !== '' && value !== 'all')
    .map(([key, value]) => [key, key === 'year' ? Number(value) : value]))
}
async function loadPatientOptions() {
  if (patientDiseaseOptions.value.length && patientHospitalOptions.value.length) return
  const [diseases, hospitals] = await Promise.allSettled([dimensionValues('disease', 100), listHospitals()])
  if (diseases.status === 'fulfilled') patientDiseaseOptions.value = diseases.value.data?.values || []
  if (hospitals.status === 'fulfilled') patientHospitalOptions.value = hospitals.value.data || []
}
async function loadPatientProfile() {
  patientLoading.value = true; patientError.value = ''
  try {
    const response = await overview(patientFilterPayload())
    patientDashboard.value = response.data
    await loadPatientOptions()
  } catch (error) { patientError.value = error.message || '患者群体画像加载失败' } finally { patientLoading.value = false }
}
function resetPatientFilters() {
  Object.assign(patientFilters, { year: 'all', service_area: '', disease: '', hospital: '', age_group: '', gender: '' })
  loadPatientProfile()
}
async function loadFieldQuality() {
  if (qualityMatrixLoading.value) return
  qualityMatrixLoading.value = true; qualityMatrixError.value = ''
  try { qualityMatrix.value = (await fieldQuality()).data || { years: [], fields: [] } }
  catch (error) { qualityMatrixError.value = error.message || '字段质量矩阵加载失败' }
  finally { qualityMatrixLoading.value = false }
}
const reportStatusLabel = (status) => ({ draft: '草稿', published: '已发布', archived: '已归档' }[status] || status)
const formatDateTime = (value) => value ? String(value).replace('T', ' ').slice(0, 16) : '—'
async function loadReportLibrary() {
  if (reportLibraryLoading.value) return
  reportLibraryLoading.value = true; reportLibraryError.value = ''
  try { reportLibrary.value = (await listReports(50)).data || [] }
  catch (error) { reportLibraryError.value = error.message || '报告库加载失败' }
  finally { reportLibraryLoading.value = false }
}
async function openStoredReport(id) {
  reportLoading.value = true
  try {
    const item = (await getReport(id)).data
    reportId.value = item.id; reportTitle.value = item.title; reportContent.value = item.content
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (error) { reportLibraryError.value = error.message || '报告读取失败' }
  finally { reportLoading.value = false }
}
async function changeReportStatus(item) {
  if (!can('system:manage')) return
  try {
    if (item.status === 'published') await withdrawReport(item.id)
    else await publishReport(item.id)
    await loadReportLibrary()
  } catch (error) { reportLibraryError.value = error.message || '报告状态更新失败' }
}
function syncComparisonDefaults(force = false) {
  const options = comparisonOptions.value
  if (!options.length) { comparisonA.value = ''; comparisonB.value = ''; return }
  if (force || !options.some((item) => item.value === comparisonA.value)) comparisonA.value = options[0]?.value || ''
  if (force || !options.some((item) => item.value === comparisonB.value) || comparisonB.value === comparisonA.value) comparisonB.value = options[1]?.value || options[0]?.value || ''
}
async function loadHospitalOptions() {
  hospitalComparisonError.value = ''
  try {
    const response = await listHospitals('', regionFilter.value === '全部服务区域' ? '' : regionFilter.value)
    hospitalOptions.value = response.data || []
    syncComparisonDefaults(true)
  } catch (error) {
    hospitalOptions.value = []
    hospitalComparisonError.value = error.message || '医疗机构目录加载失败'
  }
}
async function setComparisonType(type) {
  comparisonType.value = type
  hospitalComparison.value = null
  hospitalComparisonError.value = ''
  if (type === 'hospital') await loadHospitalOptions()
  else syncComparisonDefaults(true)
}
async function runHospitalComparison() {
  hospitalComparison.value = null
  hospitalComparisonError.value = ''
  if (!comparisonA.value || !comparisonB.value) {
    hospitalComparisonError.value = '请选择两家医疗机构'
    return
  }
  if (comparisonA.value === comparisonB.value) {
    hospitalComparisonError.value = '请选择两家不同的医疗机构'
    return
  }
  hospitalComparisonLoading.value = true
  try {
    const response = await compareHospitals(comparisonA.value, comparisonB.value, filters())
    hospitalComparison.value = response.data
  } catch (error) {
    hospitalComparisonError.value = error.message || '医院比较暂时不可用'
  } finally {
    hospitalComparisonLoading.value = false
  }
}
function clearFilter(key) {
  if (key === 'region') regionFilter.value = '全部服务区域'
  if (key === 'year') dateRange.value = 'all'
  if (key === 'disease') drilldownDisease.value = ''
  loadDashboard()
}
function clearAllFilters() { regionFilter.value = '全部服务区域'; dateRange.value = 'all'; drilldownDisease.value = ''; loadDashboard() }
function drillIntoDisease(name) { if (!name) return; drilldownDisease.value = name; loadDashboard() }
function drillIntoYear(event) { const year = Number(event?.name); if (!Number.isInteger(year)) return; dateRange.value = String(year); loadDashboard() }
function drillIntoHeatmap(event) {
  const value = Array.isArray(event?.value) ? event.value : []
  const rows = regionalOperations.value.filter((row) => row.service_area && row.year)
  const years = [...new Set(rows.map((row) => String(row.year)))].sort()
  const regions = [...new Set(rows.map((row) => String(row.service_area)))].sort()
  const year = years[Number(value[0])]; const region = regions[Number(value[1])]
  if (!year || !region) return
  dateRange.value = year; regionFilter.value = region; loadDashboard()
}
function currentAnalysisContext() {
  return [
    regionFilter.value === '全部服务区域' ? '全部服务区域' : regionFilter.value,
    dateRange.value === 'all' ? '2021至2024年' : `${dateRange.value}年`,
    drilldownDisease.value || null,
  ].filter(Boolean).join('、')
}
function analyzeOverview(kind) {
  const context = currentAnalysisContext()
  const prompts = {
    burden: `基于${context}，解读疾病负担四象限，指出高住院量、长住院日和高费用疾病，并说明统计口径。`,
    regional: `基于${context}，比较各服务区域住院量和平均住院日差异，识别值得关注的变化。`,
    growth: `基于${context}，分析疾病住院量${growthModeMeta.value.subtitle}的项目，同时比较增长率、绝对变化和样本量。`,
    comparison: `基于页面已选对象，比较${comparisonA.value}与${comparisonB.value}在住院量、平均住院日和费用方面的差异，指出主要差值、可能的运营含义与数据口径限制；不要将运营差异表述为医疗质量排名。`,
  }
  if (kind === 'comparison') {
    const comparisonFilters = filters()
    if (comparisonType.value === 'year') delete comparisonFilters.year
    if (comparisonType.value === 'region') delete comparisonFilters.service_area
    selectView('ai')
    send(prompts[kind], {
      kind: 'comparison', comparison_type: comparisonType.value,
      a: comparisonA.value, b: comparisonB.value, filters: comparisonFilters,
    })
    return
  }
  selectView('ai'); send(prompts[kind])
}
function buildCompatibleRankingViews(yearDiseaseRows, growthRows) {
  const series = new Map()
  for (const row of yearDiseaseRows || []) {
    const name = String(row.disease || '').trim(); const year = Number(row.year)
    if (!name || !Number.isInteger(year)) continue
    if (!series.has(name)) series.set(name, [])
    series.get(name).push({ year, value: Number(row.count || 0), count: Number(row.count || 0) })
  }
  const ranked = [...series.entries()].flatMap(([name, points]) => {
    points.sort((a, b) => a.year - b.year)
    if (points.length < 2 || !points[0].value) return []
    const first = points[0]; const last = points.at(-1); const absolute = last.value - first.value
    return [{ dimension_value: name, baseline_year: first.year, latest_year: last.year, baseline_value: first.value, latest_value: last.value, absolute_growth: absolute, growth_pct: absolute / first.value * 100, latest_count: last.count, yearly_values: points }]
  })
  return {
    growth: growthRows || [],
    decline: [...ranked].sort((a, b) => a.growth_pct - b.growth_pct).slice(0, 16),
    absolute: [...ranked].sort((a, b) => Math.abs(b.absolute_growth) - Math.abs(a.absolute_growth)).slice(0, 16),
  }
}
async function loadDashboardInsights() {
  insightsLoading.value = true; insightsError.value = ''
  const role = authState.user?.role || 'patient'
  const comparisonFilters = {
    ...(regionFilter.value === '全部服务区域' ? {} : { service_area: regionFilter.value }),
    ...(drilldownDisease.value ? { disease: drilldownDisease.value } : {}),
  }
  const regionalFilters = {
    ...(dateRange.value === 'all' ? {} : { year: Number(dateRange.value) }),
    ...(drilldownDisease.value ? { disease: drilldownDisease.value } : {}),
  }
  const currentFilters = filters()
  const comparisonMetrics = ['count', 'avg_length_of_stay', 'avg_total_charges', ...(role === 'patient' ? [] : ['avg_total_costs'])]
  const burdenMetrics = ['count', 'avg_length_of_stay', role === 'patient' ? 'avg_total_charges' : 'avg_total_costs']
  const requests = await Promise.allSettled([
    analyticsQuery({ dimensions: ['year'], metrics: comparisonMetrics, filters: comparisonFilters, limit: 10 }),
    analyticsQuery({ dimensions: ['disease'], metrics: burdenMetrics, filters: currentFilters, sort_by: 'count', sort_order: 'desc', limit: 24 }),
    analyticsTopic('operations', { filters: regionalFilters, limit: 100 }),
    analyticsTopic('growth_ranking', { dimension: 'disease', metrics: ['count'], filters: comparisonFilters, limit: 16 }),
    analyticsQuery({ dimensions: ['service_area'], metrics: comparisonMetrics, filters: regionalFilters, sort_by: 'count', sort_order: 'desc', limit: 30 }),
  ])
  if (requests[0].status === 'fulfilled') comparisonTrend.value = requests[0].value.data?.rows || []
  if (requests[1].status === 'fulfilled') diseaseBurden.value = requests[1].value.data?.rows || []
  if (requests[2].status === 'fulfilled') regionalOperations.value = requests[2].value.data?.rows || []
  if (requests[3].status === 'fulfilled') {
    const rankingPayload = requests[3].value.data || {}
    diseaseGrowth.value = rankingPayload.rows || []
    if (rankingPayload.ranking_views) {
      diseaseRankingViews.value = rankingPayload.ranking_views
      rankingCompatibilityMode.value = false
    } else {
      try {
        const fallback = await analyticsQuery({ dimensions: ['year', 'disease'], metrics: ['count'], filters: comparisonFilters, limit: 100 })
        diseaseRankingViews.value = buildCompatibleRankingViews(fallback.data?.rows || [], diseaseGrowth.value)
        rankingCompatibilityMode.value = true
      } catch (_error) {
        diseaseRankingViews.value = { growth: diseaseGrowth.value, decline: [], absolute: [] }
        rankingCompatibilityMode.value = true
      }
    }
  }
  if (requests[4].status === 'fulfilled') regionalComparison.value = requests[4].value.data?.rows || []
  const failed = requests.filter((result) => result.status === 'rejected')
  if (failed.length) insightsError.value = `${failed.length} 项增强分析暂时不可用，基础总览不受影响`
  syncComparisonDefaults()
  insightsLoading.value = false
}
async function loadDashboard() {
  dataLoading.value = true; apiError.value = ''
  try {
    const [overviewResponse, healthResponse, qualityResponse] = await Promise.all([
      overview(filters()), health(), can('data_asset:read') ? dataQuality() : Promise.resolve(null),
    ])
    dashboard.value = overviewResponse.data
    if (dateRange.value === 'all') {
      const years = (overviewResponse.data.trend || [])
        .map((row) => Number(row.year))
        .filter((year) => Number.isInteger(year))
      if (years.length) availableYears.value = [...new Set(years)].sort((a, b) => b - a)
    }
    lastResponseMs.value = Number(overviewResponse.meta?.elapsed_ms || 0)
    qualityReport.value = qualityResponse?.data?.quality || {}
    lastIngestion.value = qualityResponse?.data?.latest_ingestion || null
    apiConnected.value = Boolean(healthResponse.data.database?.connected)
    await loadDashboardInsights()
  } catch (error) { apiConnected.value = false; apiError.value = error.message || '后端服务不可用' } finally { dataLoading.value = false }
}
function selectView(id) { router.push(`/${id}`); mobileMenuOpen.value = false; window.scrollTo({ top: 0, behavior: 'smooth' }) }
async function signOut() { await logout(); await router.replace('/login') }
async function refreshUnreadNotifications() {
  if (!['patient', 'doctor'].includes(authState.user?.role)) return
  try { unreadNotifications.value = Number((await listNotifications(1)).data?.unread_count || 0) } catch (_error) { /* 不让通知检查影响主页 */ }
}
function openNotifications() { router.push('/notifications') }
async function send(query, analysisContext = null) {
  if (!query.trim() || loading.value) return
  messages.value.push({ role: 'user', content: query }); loading.value = true
  let assistantMessage
  let pendingChartOption = null
  try {
    await streamChat(query, {
      context(payload) { pendingChartOption = payload.chart || null; conversationId.value = payload.conversation_id || conversationId.value },
      delta(payload) { if (!assistantMessage) { assistantMessage = { role: 'assistant', content: '', chart: null }; messages.value.push(assistantMessage) }; assistantMessage.content += payload.text },
      done(payload) {
        conversationId.value = payload.conversation_id || conversationId.value
        if (!assistantMessage) { assistantMessage = { role: 'assistant', content: payload.summary || '分析已完成。', chart: null }; messages.value.push(assistantMessage) }
      },
    }, conversationId.value, analysisContext)
    // 文字完成后把图表附在同一条回复下方，保持对话阅读顺序。
    if (assistantMessage && pendingChartOption) assistantMessage.chart = pendingChartOption
  } catch (error) {
    const errorText = error.message || '当前无法准确完成该问题的分析，请稍后重试或补充分析维度和指标。'
    if (!assistantMessage) messages.value.push({ role: 'assistant', content: errorText, chart: null })
    else assistantMessage.content += '\n\n' + errorText
  } finally { loading.value = false }
}
async function submitCostPrediction() {
  if (costLoading.value) return
  costLoading.value = true; costError.value = ''; costResult.value = null; budgetResult.value = null
  try {
    const numericFields = new Set(['discharge_year', 'length_of_stay', 'apr_severity_of_illness_code'])
    const features = Object.fromEntries(Object.entries(costForm)
      .filter(([, value]) => value !== '' && value !== null && value !== undefined)
      .map(([key, value]) => [key, numericFields.has(key) ? Number(value) : String(value).trim()]))
    let response
    if (costMode.value === 'future') {
      const allowed = new Set(['hospital_service_area', 'hospital_county', 'age_group', 'gender', 'race', 'ethnicity', 'type_of_admission', 'ccsr_diagnosis_code', 'payment_typology_1', 'emergency_department_indicator'])
      const futureFeatures = Object.fromEntries(Object.entries(features).filter(([key]) => allowed.has(key)))
      response = await predictFutureCost(futureFeatures, Number(futureForecastYear.value), futureGrowthRate.value === '' ? null : Number(futureGrowthRate.value))
    } else response = await predictCost(features)
    costResult.value = response.data
  } catch (error) {
    costError.value = error.message || '费用预测失败，请检查输入后重试。'
  } finally { costLoading.value = false }
}
async function submitBudgetForecast() {
  if (costLoading.value) return
  costLoading.value = true; costError.value = ''; costResult.value = null; budgetResult.value = null
  try {
    const payload = {
      ...budgetForm, target_year: Number(budgetForm.target_year),
      annual_volume_growth_rate: budgetForm.annual_volume_growth_rate === '' ? null : Number(budgetForm.annual_volume_growth_rate),
      annual_cost_growth_rate: budgetForm.annual_cost_growth_rate === '' ? null : Number(budgetForm.annual_cost_growth_rate),
    }
    budgetResult.value = (await forecastAnnualBudget(payload)).data
  } catch (error) { costError.value = error.message || '年度预算预测失败，请检查输入后重试。' } finally { costLoading.value = false }
}
function selectCostMode(mode) {
  costMode.value = mode; costResult.value = null; budgetResult.value = null; costError.value = ''
  if (mode !== 'budget') void loadCostOptions()
  if (mode === 'budget') void loadBudgetHospitalOptions()
}
async function loadCostOptions() {
  if (costOptions.value.diagnosis.length) return
  try { costOptions.value = (await costPredictionOptions()).data || costOptions.value } catch (_error) { /* 留空时仍允许手工输入 */ }
}
async function loadBudgetHospitalOptions() {
  if (budgetHospitalOptions.value.length) return
  try { budgetHospitalOptions.value = (await listHospitals('', '', 300)).data || [] } catch (_error) { /* 允许手工输入作为降级 */ }
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
  budgetResult.value = null
}
function sectionsForReport(report) {
  if (!report) return undefined
  const base = { filters: filters(), sort_order: null }
  if (report.title === '医疗运营综合分析报告') return [
    { title: '年度住院运营趋势', data: { ...base, dimension: 'year', dimension_label: '年份', metrics: ['count', 'avg_length_of_stay'], rows: (dashboard.value.trend || []).map((row) => ({ ...row, dimension_value: row.year })) } },
    { title: '重点疾病负担', data: { ...base, dimension: 'disease', dimension_label: '疾病', metrics: ['count', 'avg_length_of_stay', 'avg_total_charges'], sort_by: 'count', rows: dashboard.value.diseases || [] } },
  ]
  if (report.title === '重点患者群体结构分析') return [
    { title: '年龄结构', data: { ...base, dimension: 'age_group', dimension_label: '年龄段', metrics: ['count', 'avg_length_of_stay'], sort_by: 'count', rows: dashboard.value.ages || [] } },
    { title: '病情严重程度', data: { ...base, dimension: 'severity', dimension_label: '严重程度', metrics: ['count', 'avg_length_of_stay'], sort_by: 'count', rows: dashboard.value.severity || [] } },
  ]
  if (report.title === '重点疾病住院费用报告') return [
    { title: '重点疾病住院费用', data: { ...base, dimension: 'disease', dimension_label: '疾病', metrics: ['count', 'avg_total_charges'], sort_by: 'avg_total_charges', rows: dashboard.value.diseases || [] } },
  ]
  return [
    { title: '数据质量评估', data: { ...base, dimension: 'quality', dimension_label: '质量指标', metrics: ['quality_score'], sort_by: 'quality_score', rows: qualityItems.value.map((item) => ({ dimension_value: item.label, quality_score: Number(item.value.toFixed(2)) })) } },
  ]
}
async function generateReport(report = null) {
  reportLoading.value = true
  const title = report?.title || '医疗大数据综合洞察报告'
  try { const response = await createReport({ title, sections: sectionsForReport(report) }); reportContent.value = response.data.content; reportId.value = response.data.id; reportTitle.value = response.data.title; await loadReportLibrary() } catch (error) { reportContent.value = `报告生成失败：${error.message}`; reportId.value = null; reportTitle.value = '' } finally { reportLoading.value = false }
}
async function publishGeneratedReport() { if (!reportId.value) return; await publishReport(reportId.value); await loadReportLibrary(); window.alert('报告已发布，患者用户现在可以查看') }
function exportDashboard() {
  const blob = new Blob([JSON.stringify(dashboard.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '智慧医疗运营数据.json'; link.click(); URL.revokeObjectURL(url)
}
function downloadReport() {
  if (!reportContent.value) return
  const blob = new Blob([reportContent.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `${reportTitle.value || '医疗大数据洞察报告'}.md`; link.click(); URL.revokeObjectURL(url)
}
function runSearch() {
  const query = searchQuery.value.trim()
  if (!query) return
  selectView('ai'); send(query); searchQuery.value = ''
}
function analyzeDisease(name) { selectView('ai'); send(`分析疾病「${name}」的住院量、平均住院日和费用`) }

onMounted(() => {
  loadDashboard()
  refreshUnreadNotifications()
  window.addEventListener('keydown', handleChartModalKeydown)
  if (['patient', 'doctor'].includes(authState.user?.role)) {
    notificationTimer = window.setInterval(refreshUnreadNotifications, 30000)
  }
})
watch(activeView, (view) => {
  if (view === 'data' && can('data_asset:read') && !(qualityMatrix.value.fields || []).length) loadFieldQuality()
  if (view === 'patients' && can('patient_profile:read')) loadPatientProfile()
  if (view === 'reports' && can('report:generate')) loadReportLibrary()
  if (view === 'cost-prediction') {
    if (costMode.value === 'budget') void loadBudgetHospitalOptions()
    else void loadCostOptions()
  }
}, { immediate: true })
watch(() => budgetForm.scope_type, (scopeType) => {
  budgetForm.scope_value = scopeType === 'service_area' ? 'New York City' : ''
  if (scopeType === 'hospital') void loadBudgetHospitalOptions()
})
onBeforeUnmount(() => {
  if (notificationTimer) window.clearInterval(notificationTimer)
  window.removeEventListener('keydown', handleChartModalKeydown)
  document.body.classList.remove('chart-modal-open')
})
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
        <div class="topbar-actions"><div class="demo-pill"><span :class="{ offline: !apiConnected }"></span> {{ apiConnected ? '数据服务正常' : '服务未连接' }}</div><button class="icon-button" :aria-label="unreadNotifications ? `通知，${unreadNotifications}条未读` : '通知'" @click="openNotifications"><AppIcon name="bell" :size="19" /><i v-if="unreadNotifications > 0"></i></button><div class="profile"><div class="avatar">{{ (authState.user?.display_name || authState.user?.username || '用').slice(0,1) }}</div><div><strong>{{ authState.user?.display_name || authState.user?.username }}</strong><small>{{ authState.user?.role === 'admin' ? '运维员' : authState.user?.role === 'doctor' ? '医生用户' : '患者用户' }}</small></div><button class="logout-button" @click="signOut">退出</button></div></div>
      </header>

      <main class="content">
        <div class="page-heading"><div><p class="eyebrow">SMART HEALTHCARE PLATFORM</p><h1>{{ currentMeta.title }}</h1><span>{{ currentMeta.subtitle }}</span></div><div v-if="activeView === 'overview'" class="filters" :aria-busy="dataLoading"><label><AppIcon name="hospital" :size="15" /><select v-model="regionFilter" :disabled="dataLoading" aria-label="选择服务区域" @change="loadDashboard"><option>全部服务区域</option><option>New York City</option><option>Long Island</option><option>Hudson Valley</option><option>Capital/Adirondacks</option><option>Central NY</option><option>Western NY</option><option>Southern Tier</option><option>Finger Lakes</option></select><AppIcon name="chevron-down" :size="13" /></label><label><AppIcon name="calendar" :size="15" /><select v-model="dateRange" :disabled="dataLoading" aria-label="选择出院年份" @change="loadDashboard"><option value="all">全部年份</option><option v-for="year in availableYears" :key="year" :value="String(year)">{{ year }} 年</option></select><AppIcon name="chevron-down" :size="13" /></label><button class="outline-button compare-trigger" :class="{ active: compareOpen }" @click="compareOpen = !compareOpen"><AppIcon name="chart" :size="14" /> 对比分析</button><span v-if="dataLoading" class="filter-loading"><AppIcon name="refresh" :size="12" /> 更新中</span><button v-if="can('data:export')" class="outline-button" @click="exportDashboard"><AppIcon name="download" :size="15" /> 导出</button></div></div>
        <div v-if="activeView === 'overview' && activeFilterChips.length" class="filter-context"><span>当前分析</span><button v-for="chip in activeFilterChips" :key="chip.key" @click="clearFilter(chip.key)">{{ chip.label }} ×</button><button class="clear-all" @click="clearAllFilters">清除全部</button></div>
        <div v-if="apiError" class="api-error"><AppIcon name="info" :size="16" /> {{ apiError }}，当前页面保留已加载数据。</div>

        <template v-if="activeView === 'overview'">
          <section class="metric-grid"><article v-for="metric in metrics" :key="metric.label" class="metric-card"><div class="metric-icon" :class="metric.tone"><AppIcon :name="metric.icon" :size="21" /></div><div class="metric-top"><span>{{ metric.label }}</span><button>•••</button></div><div class="metric-value">{{ metric.value }} <small>{{ metric.unit }}</small></div><div class="metric-foot" :class="metric.direction"><span><AppIcon :name="metric.direction === 'up' ? 'arrow-up' : 'arrow-down'" :size="11" />{{ metric.trend }}</span>{{ metric.note }}</div></article></section>
          <section v-if="compareOpen" class="panel comparison-panel">
            <div class="comparison-head"><div><span class="eyebrow">COMPARE</span><h2>双对象运营比较</h2><p>{{ drilldownDisease ? `当前疾病：${formatDiseaseName(drilldownDisease)}` : '当前疾病范围：全部' }}</p></div><div class="comparison-tabs"><button :class="{ active: comparisonType === 'year' }" @click="setComparisonType('year')">年份对比</button><button :class="{ active: comparisonType === 'region' }" @click="setComparisonType('region')">区域对比</button><button :class="{ active: comparisonType === 'hospital' }" @click="setComparisonType('hospital')">医院对比</button></div></div>
            <div class="comparison-controls"><label>对象 A<select v-model="comparisonA" @change="hospitalComparison = null"><option v-for="item in comparisonOptions" :key="`a-${item.value}`" :value="item.value">{{ item.label }}</option></select></label><span>VS</span><label>对象 B<select v-model="comparisonB" @change="hospitalComparison = null"><option v-for="item in comparisonOptions" :key="`b-${item.value}`" :value="item.value">{{ item.label }}</option></select></label><button v-if="comparisonType === 'hospital'" class="compare-run" :disabled="hospitalComparisonLoading || !comparisonOptions.length" @click="runHospitalComparison">{{ hospitalComparisonLoading ? '正在比较…' : '开始比较' }}</button><button class="ai-action" :disabled="comparisonType === 'hospital' && !hospitalComparison" @click="analyzeOverview('comparison')"><AppIcon name="sparkle" :size="13" /> AI 解读差异</button></div>
            <p v-if="comparisonType === 'hospital' && !hospitalOptions.length && !hospitalComparisonError" class="hospital-compare-status">正在加载可比较的医疗机构…</p>
            <p v-if="hospitalComparisonError" class="hospital-compare-status error"><AppIcon name="info" :size="13" /> {{ hospitalComparisonError }}</p>
            <template v-if="comparisonType !== 'hospital' || hospitalComparison">
              <div class="comparison-metrics"><article v-for="metric in comparisonMetricRows" :key="metric.key"><span>{{ metric.label }}</span><div><strong>{{ formatOptionalNumber(metric.a, metric.digits) }} <small>{{ metric.unit }}</small></strong><b>对比</b><strong>{{ formatOptionalNumber(metric.b, metric.digits) }} <small>{{ metric.unit }}</small></strong></div><p :class="metric.delta != null && metric.delta < 0 ? 'negative-text' : 'positive-text'">差值 {{ metric.delta == null ? '—' : `${metric.delta >= 0 ? '+' : ''}${formatNumber(metric.delta, metric.digits)} ${metric.unit}` }} · {{ metric.deltaPct == null ? '暂无比例' : `${metric.deltaPct >= 0 ? '+' : ''}${metric.deltaPct.toFixed(1)}%` }}</p></article></div>
            </template>
            <div v-if="comparisonType === 'hospital' && hospitalComparison" class="hospital-compare-grid">
              <article class="hospital-trend"><div class="hospital-section-head"><div><h3>年度规模与住院日趋势</h3><p>柱形为住院记录，折线为平均住院日</p></div><span>A / B</span></div><DashboardChart :option="hospitalTrendOption" height="300px" /></article>
              <div class="hospital-detail-mosaic" :class="{ single: authState.user?.role === 'patient' }">
                <article class="hospital-mix-card disease-mix-card"><div class="hospital-section-head"><div><h3>重点疾病构成</h3><p>展示两院病例构成占比与记录数</p></div><span>前 10 项</span></div><div class="hospital-mix-table"><div v-for="row in hospitalDiseaseMix" :key="row.rawName" class="hospital-mix-row"><strong :title="row.name">{{ row.name }}</strong><div><span>A {{ row.a.toFixed(1) }}% · {{ formatNumber(row.countA) }}</span><i><em class="mix-a" :style="{ width: `${Math.min(row.a, 100)}%` }"></em></i></div><div><span>B {{ row.b.toFixed(1) }}% · {{ formatNumber(row.countB) }}</span><i><em class="mix-b" :style="{ width: `${Math.min(row.b, 100)}%` }"></em></i></div></div></div></article>
                <div v-if="authState.user?.role !== 'patient'" class="hospital-side-stack">
                  <article class="hospital-mix-card severity-mix-card"><div class="hospital-section-head"><div><h3>病例严重程度</h3><p>辅助判断病例结构差异</p></div><span>临床运营</span></div><div class="hospital-mix-table compact"><div v-for="row in hospitalSeverityMix" :key="row.name" class="hospital-mix-row"><strong>{{ row.name }}</strong><div><span>A {{ row.a.toFixed(1) }}%</span><i><em class="mix-a" :style="{ width: `${Math.min(row.a, 100)}%` }"></em></i></div><div><span>B {{ row.b.toFixed(1) }}%</span><i><em class="mix-b" :style="{ width: `${Math.min(row.b, 100)}%` }"></em></i></div></div></div></article>
                  <article class="hospital-mix-card admission-mix-card"><div class="hospital-section-head"><div><h3>入院类型构成</h3><p>比较急诊、择期等来源结构</p></div><span>临床运营</span></div><div class="hospital-mix-table compact"><div v-for="row in hospitalAdmissionMix" :key="row.name" class="hospital-mix-row"><strong>{{ row.name }}</strong><div><span>A {{ row.a.toFixed(1) }}%</span><i><em class="mix-a" :style="{ width: `${Math.min(row.a, 100)}%` }"></em></i></div><div><span>B {{ row.b.toFixed(1) }}%</span><i><em class="mix-b" :style="{ width: `${Math.min(row.b, 100)}%` }"></em></i></div></div></div></article>
                </div>
              </div>
              <article v-if="authState.user?.role === 'admin' && (hospitalCaseMix.a || hospitalCaseMix.b)" class="hospital-case-mix"><div class="hospital-section-head"><div><h3>病例组合校正基准</h3><p>按年度、APR DRG 与严重程度计算观察/预期指数，1.00 为基准</p></div><span>管理员</span></div><div class="case-mix-grid"><div v-for="(row, key) in hospitalCaseMix" :key="key"><b>医院 {{ key.toUpperCase() }}</b><strong>{{ formatOptionalNumber(row?.case_mix_cost_index, 2) }}</strong><small>成本指数</small><strong>{{ formatOptionalNumber(row?.case_mix_los_index, 2) }}</strong><small>住院日指数</small><p>次均实际 / 预期成本：{{ formatOptionalNumber(row?.avg_actual_cost, 0) }} / {{ formatOptionalNumber(row?.avg_expected_cost, 0) }} 美元</p></div></div></article>
            </div>
            <p v-if="comparisonType === 'hospital' && hospitalComparison" class="hospital-caveat">住院记录不是去重患者人数；账单收费不是实际收入。医院差异仅用于运营分析，不代表医疗质量评级。</p>
          </section>
          <section class="dashboard-grid primary-row" :class="{ single: !can('patient_profile:read') }"><article class="panel trend-panel"><div class="panel-head"><div><h2>住院运营趋势</h2><p>点击年份柱形可下钻筛选</p></div><button v-if="can('report:generate')" class="text-button" @click="selectView('reports')">查看明细 <AppIcon name="arrow-right" :size="14" /></button></div><DashboardChart :option="trendOption" height="294px" @select="drillIntoYear" /></article><article v-if="can('patient_profile:read')" class="panel insight-panel"><div class="panel-head"><div><h2>AI 智能洞察</h2><p>基于本期数据自动生成</p></div><span class="ai-badge"><AppIcon name="sparkle" :size="13" /> AI</span></div><div class="insight-list"><div v-for="item in insightItems" :key="item.title" class="insight-item"><span class="insight-mark" :class="item.color"></span><div><em :class="item.color">{{ item.tag }}</em><h3>{{ item.title }}</h3><p>{{ item.text }}</p><button @click="selectView(item.action.includes('画像') ? 'patients' : item.action.includes('报告') ? 'reports' : 'ai')">{{ item.action }} <AppIcon name="arrow-right" :size="12" /></button></div></div></div></article></section>
          <p v-if="insightsError" class="insights-warning"><AppIcon name="info" :size="14" />{{ insightsError }}</p>
          <section class="dashboard-grid decision-row" :aria-busy="insightsLoading">
            <article class="panel chart-click-card" tabindex="0" aria-label="点击放大疾病负担四象限" @click="openExpandedChart('burden')" @keydown.enter.self="openExpandedChart('burden')"><div class="panel-head"><div><h2>疾病负担四象限</h2><p>点击模块放大；大图中点击气泡下钻疾病</p></div><button class="ai-action compact" @click.stop="analyzeOverview('burden')"><AppIcon name="sparkle" :size="12" /> AI 解读</button></div><div v-if="insightsLoading && !diseaseBurden.length" class="analytics-empty">正在计算疾病负担…</div><DashboardChart v-else :option="diseaseBurdenOption" height="285px" /></article>
            <article class="panel chart-click-card" tabindex="0" aria-label="点击放大服务区域年度热力图" @click="openExpandedChart('regional')" @keydown.enter.self="openExpandedChart('regional')"><div class="panel-head"><div><h2>服务区域年度热力图</h2><p>点击模块放大；大图中点击单元格下钻</p></div><button class="ai-action compact" @click.stop="analyzeOverview('regional')"><AppIcon name="sparkle" :size="12" /> AI 解读</button></div><div v-if="insightsLoading && !regionalOperations.length" class="analytics-empty">正在汇总区域数据…</div><DashboardChart v-else :option="regionalHeatmapOption" height="285px" /></article>
            <article class="panel chart-click-card" tabindex="0" :aria-label="`点击放大${growthModeMeta.title}`" @click="openExpandedChart('growth')" @keydown.enter.self="openExpandedChart('growth')"><div class="panel-head ranking-head"><div><h2>{{ growthModeMeta.title }}</h2><p>点击模块放大；最早与最新可用年度对比<span v-if="rankingCompatibilityMode"> · 兼容模式基于主要疾病</span></p></div><button class="ai-action compact" @click.stop="analyzeOverview('growth')"><AppIcon name="sparkle" :size="12" /> AI 解读</button></div><div class="ranking-tabs" @click.stop><button :class="{ active: growthMode === 'growth' }" @click="growthMode = 'growth'">增长最快</button><button :class="{ active: growthMode === 'decline' }" @click="growthMode = 'decline'">下降最多</button><button :class="{ active: growthMode === 'absolute' }" @click="growthMode = 'absolute'">绝对变化</button></div><div v-if="insightsLoading && !diseaseGrowth.length" class="analytics-empty ranking-empty">正在计算变化排名…</div><div v-else-if="!activeDiseaseGrowth.length" class="analytics-empty ranking-empty">当前筛选范围没有足够的跨年样本</div><DashboardChart v-else :option="diseaseGrowthOption" height="250px" /></article>
          </section>
          <p class="analytics-caveat">费用为名义美元，未进行通胀调整；增长和区域差异仅用于运营分析，不代表因果关系或医疗质量排名。</p>
          <section v-if="can('patient_profile:read')" class="dashboard-grid secondary-row"><article class="panel chart-click-card" tabindex="0" aria-label="点击放大重点疾病住院量" @click="openExpandedChart('disease')" @keydown.enter.self="openExpandedChart('disease')"><div class="panel-head"><div><h2>重点疾病住院量</h2><p>点击模块放大；大图中点击疾病下钻</p></div></div><DashboardChart :option="diseaseOption" height="235px" /></article><article class="panel chart-click-card" tabindex="0" aria-label="点击放大患者年龄结构" @click="openExpandedChart('age')" @keydown.enter.self="openExpandedChart('age')"><div class="panel-head"><div><h2>患者年龄结构</h2><p>点击模块放大查看年龄段占比</p></div></div><DashboardChart :option="ageOption" height="235px" /></article><article class="panel chart-click-card" tabindex="0" aria-label="点击放大支付方式构成" @click="openExpandedChart('payment')" @keydown.enter.self="openExpandedChart('payment')"><div class="panel-head"><div><h2>支付方式构成</h2><p>点击模块放大查看支付类型分布</p></div></div><DashboardChart :option="paymentOption" height="235px" /></article></section>
          <section v-if="can('patient_profile:read')" class="panel data-table-panel"><div class="panel-head"><div><h2>重点疾病运营明细</h2><p>住院量、平均住院日与次均费用对比</p></div><button class="text-button" @click="selectView('reports')">查看完整报告 <AppIcon name="arrow-right" :size="14" /></button></div><div class="table-wrap"><table><thead><tr><th>疾病类别</th><th>出院人次</th><th>平均住院日</th><th>次均费用</th><th>首末年变化</th><th></th></tr></thead><tbody><tr v-for="row in diseaseRows" :key="row.rawName"><td><span class="disease-dot"></span><strong>{{ row.name }}</strong></td><td>{{ row.count }}</td><td>{{ row.days }} 天</td><td>{{ row.cost }}</td><td><em :class="row.change.startsWith('-') ? 'negative' : 'positive'">{{ row.change }}</em></td><td><button class="row-action" @click="analyzeDisease(row.rawName)"><AppIcon name="arrow-right" :size="14" /></button></td></tr></tbody></table></div></section>
        </template>

        <template v-else-if="activeView === 'ai'">
          <div class="ai-conversation-layout"><section class="ai-chat-wrap"><div class="section-title"><span class="title-icon"><AppIcon name="brain" :size="20" /></span><div><h2>对话式数据分析</h2><p>{{can('ai:basic')?'面向患者的公开趋势与健康科普，不提供个人诊断建议':'分析文字与可视化图表将在同一条回复中连续展示'}}</p></div><span class="ai-connection-state" :class="{ offline: !apiConnected }">{{ apiConnected ? 'SQL Server · DeepSeek 已连接' : '等待数据服务连接' }}</span></div><ChatPanel :messages="messages" :loading="loading" :suggestions="aiSuggestions" @send="send" /></section></div>
        </template>

        <template v-else-if="activeView === 'cost-prediction'">
          <div class="cost-layout">
            <section class="panel cost-form-panel">
              <div class="panel-head"><div><h2>{{ costMode === 'encoded' ? '已编码住院信息' : costMode === 'future' ? '待入院病例信息' : '年度预算范围' }}</h2><p>{{ costMode === 'encoded' ? '使用完整编码估算最终成本；未填写字段按训练数据缺失规则处理' : costMode === 'future' ? '仅使用入院前可知信息，并按未来年度成本增长情景估算' : '按医院或服务区域的历史病例量与次均成本趋势生成预算情景' }}</p></div><span class="model-badge">{{ costMode === 'budget' ? '趋势情景预测' : '机器学习模型 · 2024测试集验证' }}</span></div>
              <div class="ranking-tabs cost-mode-tabs"><button type="button" :class="{ active: costMode === 'encoded' }" @click="selectCostMode('encoded')">已编码病例估算</button><button type="button" :class="{ active: costMode === 'future' }" @click="selectCostMode('future')">未来病例预测</button><button v-if="can('budget_forecast:use')" type="button" :class="{ active: costMode === 'budget' }" @click="selectCostMode('budget')">年度预算预测</button></div>
              <form v-if="costMode !== 'budget'" class="cost-form" @submit.prevent="submitCostPrediction">
                <div class="cost-form-section"><h3>基本与入院信息</h3><div class="cost-field-grid">
                  <label><span>服务区域</span><select v-model="costForm.hospital_service_area"><option value="">未知</option><option>New York City</option><option>Long Island</option><option>Hudson Valley</option><option>Capital/Adirondacks</option><option>Central NY</option><option>Western NY</option><option>Southern Tier</option><option>Finger Lakes</option></select></label>
                  <label><span>医院所在县</span><input v-model.trim="costForm.hospital_county" maxlength="100" placeholder="例如 Manhattan" /></label>
                  <label><span>年龄段</span><select v-model="costForm.age_group"><option value="">未知</option><option>0 to 17</option><option>18 to 29</option><option>30 to 49</option><option>50 to 69</option><option>70 or Older</option></select></label>
                  <label><span>性别</span><select v-model="costForm.gender"><option value="">未知</option><option value="F">F · 女性</option><option value="M">M · 男性</option><option value="U">U · 未知</option></select></label>
                  <label><span>种族</span><input v-model.trim="costForm.race" maxlength="50" placeholder="可选" /></label>
                  <label><span>族裔</span><input v-model.trim="costForm.ethnicity" maxlength="50" placeholder="可选" /></label>
                  <label><span>入院类型</span><select v-model="costForm.type_of_admission"><option value="">未知</option><option>Emergency</option><option>Urgent</option><option>Elective</option><option>Newborn</option><option>Trauma</option><option>Not Available</option></select></label>
                  <label><span>急诊标志</span><select v-model="costForm.emergency_department_indicator"><option value="">未知</option><option value="Y">Y · 是</option><option value="N">N · 否</option></select></label>
                  <label v-if="costMode === 'encoded'"><span>出院年份</span><input v-model.number="costForm.discharge_year" type="number" min="2000" max="2100" required /></label>
                  <label v-if="costMode === 'encoded'"><span>住院日</span><input v-model.number="costForm.length_of_stay" type="number" min="0" max="3650" step="1" required /></label>
                </div></div>

                <div v-if="costMode === 'encoded'" class="cost-form-section"><h3>诊断、手术与分组编码</h3><div class="cost-field-grid">
                  <label><span>CCSR 诊断编码</span><select v-model="costForm.ccsr_diagnosis_code"><option value="">未知 / 未选择</option><option v-for="item in costOptions.diagnosis" :key="`dx-${item.code}`" :value="item.code">{{ item.code }}{{ item.description ? ` · ${item.description}` : '' }}</option></select></label>
                  <label><span>CCSR 手术编码</span><select v-model="costForm.ccsr_procedure_code"><option value="">未知 / 未选择</option><option v-for="item in costOptions.procedure" :key="`px-${item.code}`" :value="item.code">{{ item.code }}{{ item.description ? ` · ${item.description}` : '' }}</option></select></label>
                  <label><span>APR DRG 编码</span><select v-model="costForm.apr_drg_code"><option value="">未知 / 未选择</option><option v-for="item in costOptions.apr_drg" :key="`drg-${item.code}`" :value="item.code">{{ item.code }}{{ item.description ? ` · ${item.description}` : '' }}</option></select></label>
                  <label><span>APR MDC 编码</span><select v-model="costForm.apr_mdc_code"><option value="">未知 / 未选择</option><option v-for="item in costOptions.apr_mdc" :key="`mdc-${item.code}`" :value="item.code">{{ item.code }}{{ item.description ? ` · ${item.description}` : '' }}</option></select></label>
                  <label><span>严重程度编码</span><select v-model.number="costForm.apr_severity_of_illness_code"><option :value="0">0 · 未知</option><option :value="1">1 · Minor</option><option :value="2">2 · Moderate</option><option :value="3">3 · Major</option><option :value="4">4 · Extreme</option></select></label>
                  <label><span>严重程度描述</span><select v-model="costForm.apr_severity_of_illness_desc"><option value="">未知</option><option>Minor</option><option>Moderate</option><option>Major</option><option>Extreme</option></select></label>
                  <label><span>死亡风险</span><select v-model="costForm.apr_risk_of_mortality"><option value="">未知</option><option>Minor</option><option>Moderate</option><option>Major</option><option>Extreme</option></select></label>
                  <label><span>内科/外科分类</span><select v-model="costForm.apr_medical_surgical_desc"><option value="">未知</option><option>Medical</option><option>Surgical</option><option>Not Applicable</option></select></label>
                  <label class="wide"><span>主要支付方式</span><select v-model="costForm.payment_typology_1"><option value="">未知</option><option>Medicare</option><option>Medicaid</option><option>Private Health Insurance</option><option>Self-Pay</option><option>Blue Cross/Blue Shield</option><option>Federal/State/Local/VA</option><option>Miscellaneous/Other</option></select></label>
                </div></div>

                <div v-else class="cost-form-section"><h3>入院前诊断与未来情景</h3><div class="cost-field-grid">
                  <label><span>初步 CCSR 诊断编码</span><select v-model="costForm.ccsr_diagnosis_code"><option value="">未知 / 未选择</option><option v-for="item in costOptions.diagnosis" :key="`future-dx-${item.code}`" :value="item.code">{{ item.code }}{{ item.description ? ` · ${item.description}` : '' }}</option></select></label>
                  <label><span>预计支付方式</span><select v-model="costForm.payment_typology_1"><option value="">未知</option><option>Medicare</option><option>Medicaid</option><option>Private Health Insurance</option><option>Self-Pay</option><option>Blue Cross/Blue Shield</option><option>Federal/State/Local/VA</option><option>Miscellaneous/Other</option></select></label>
                  <label><span>预测年度</span><input v-model.number="futureForecastYear" type="number" min="2025" max="2034" required /></label>
                  <label class="with-hint"><span>年度成本增长率</span><input v-model.number="futureGrowthRate" type="number" min="-0.2" max="0.2" step="0.005" placeholder="留空则采用历史趋势" /><small>如 0.03 表示 3%</small></label>
                </div></div>

                <div v-if="costError" class="cost-error"><AppIcon name="info" :size="15" />{{ costError }}</div>
                <div class="cost-actions"><button type="button" class="outline-button" @click="resetCostPrediction">重置</button><button type="submit" class="primary-button" :disabled="costLoading"><AppIcon name="sparkle" :size="15" />{{ costLoading ? '预测中…' : '开始预测' }}</button></div>
              </form>
              <form v-else class="cost-form" @submit.prevent="submitBudgetForecast">
                <div class="cost-form-section"><h3>预算范围与情景</h3><div class="cost-field-grid">
                  <label><span>预算范围</span><select v-model="budgetForm.scope_type"><option value="service_area">服务区域</option><option value="hospital">医院</option></select></label>
                  <label v-if="budgetForm.scope_type === 'service_area'"><span>服务区域</span><select v-model="budgetForm.scope_value"><option>New York City</option><option>Long Island</option><option>Hudson Valley</option><option>Capital/Adirondacks</option><option>Central NY</option><option>Western NY</option><option>Southern Tier</option><option>Finger Lakes</option></select></label>
                  <label v-else><span>医院名称</span><select v-model="budgetForm.scope_value" required><option value="">请选择医院</option><option v-for="item in budgetHospitalOptions" :key="`budget-hospital-${item.hospital}`" :value="item.hospital">{{ item.hospital }}{{ item.service_area ? ` · ${item.service_area}` : '' }}</option></select></label>
                  <label><span>目标年度</span><input v-model.number="budgetForm.target_year" type="number" min="2025" max="2034" required /></label>
                  <label><span>年度病例量增长率</span><input v-model.number="budgetForm.annual_volume_growth_rate" type="number" min="-0.2" max="0.2" step="0.005" placeholder="留空则采用历史趋势" /></label>
                  <label><span>年度次均成本增长率</span><input v-model.number="budgetForm.annual_cost_growth_rate" type="number" min="-0.2" max="0.2" step="0.005" placeholder="留空则采用历史趋势" /></label>
                </div></div>
                <div v-if="costError" class="cost-error"><AppIcon name="info" :size="15" />{{ costError }}</div>
                <div class="cost-actions"><button type="submit" class="primary-button" :disabled="costLoading"><AppIcon name="sparkle" :size="15" />{{ costLoading ? '预测中…' : '生成年度预算' }}</button></div>
              </form>
            </section>

            <section class="cost-result-column">
              <article v-if="costResult" class="cost-result-card">
                <span class="result-kicker">PREDICTED TOTAL COST</span><p>预测住院总成本</p>
                <strong>{{ formatCost(costResult.predicted_total_cost) }}</strong>
                <div class="cost-band"><span>近似误差范围</span><b>{{ formatCost(costResult.approximate_error_band?.lower) }} — {{ formatCost(costResult.approximate_error_band?.upper) }}</b><small>基于 2024 时间外测试集 MAE，不是统计置信区间</small></div>
              </article>
              <article v-else-if="budgetResult" class="cost-result-card"><span class="result-kicker">FORECAST ANNUAL BUDGET</span><p>{{ budgetResult.target_year }} 年预测总预算</p><strong>{{ formatCost(budgetResult.forecast_total_cost) }}</strong><div class="cost-band"><span>预计病例量 / 次均成本</span><b>{{ formatNumber(budgetResult.forecast_case_count) }} 例 · {{ formatCost(budgetResult.forecast_average_cost) }}</b><small>基准：{{ budgetResult.baseline?.year }} 年；病例量与成本增长率均可调整</small></div></article>
              <article v-else class="panel cost-empty"><span><AppIcon name="wallet" :size="30" /></span><h2>等待预测</h2><p>选择模式、填写必要信息后开始预测，结果将在这里显示。</p></article>

              <article v-if="costResult" class="panel model-metrics-card"><div class="panel-head"><div><h2>模型验证指标</h2><p>{{ costResult.model?.version }} · 数据版本 {{ costResult.model?.training_data_version }}</p></div><span class="status-tag">已激活</span></div><div class="model-metrics">
                <div><span>R²</span><strong>{{ Number(costResult.model?.metrics?.r2 || 0).toFixed(4) }}</strong></div>
                <div><span>MAE</span><strong>{{ formatCost(costResult.model?.metrics?.mae) }}</strong></div>
                <div><span>中位误差</span><strong>{{ formatCost(costResult.model?.metrics?.median_absolute_error) }}</strong></div>
                <div><span>RMSE</span><strong>{{ formatCost(costResult.model?.metrics?.rmse) }}</strong></div>
              </div></article>
              <article class="cost-safety-note"><AppIcon name="shield" :size="18" /><div><strong>使用范围</strong><p>{{ costMode === 'encoded' ? '这是基于已编码住院信息的运营成本估算。' : costMode === 'future' ? '这是基于入院前可知信息和年度成本增长情景的未来病例估算。' : '这是基于历史病例量和次均成本趋势的年度预算情景。' }}单位为美元，不能作为患者结算金额、保险理赔结果、财务承诺或医疗决策依据。</p></div></article>
            </section>
          </div>
        </template>

        <template v-else-if="activeView === 'data'">
          <section class="data-overview-grid"><article class="quality-score-card"><div class="score-ring"><strong>{{ qualityScore.toFixed(2) }}</strong><small>综合评分</small></div><div><span class="tag success"><AppIcon name="check" :size="12" /> 数据质量优秀</span><h2>医疗数据质量评估</h2><p>依据完整性、准确性、一致性与时效性四个维度综合计算。</p></div></article><article class="panel quality-bars"><div class="panel-head"><div><h2>质量维度</h2><p>最近一次评估：{{ lastIngestion?.finished_at?.replace('T', ' ') || '暂无记录' }}</p></div></div><div v-for="item in qualityItems" :key="item.label" class="quality-row"><span>{{ item.label }}</span><div><i :style="{ width: `${item.value}%` }"></i></div><strong>{{ item.text }}</strong></div></article></section>
          <section class="metric-grid data-metrics"><article class="mini-stat"><span>数据总量</span><strong>{{ formatNumber(totalRecords) }}</strong><small>全量清洗后记录</small></article><article class="mini-stat"><span>标准字段</span><strong>33</strong><small>6 个业务主题域</small></article><article class="mini-stat"><span>清洗通过率</span><strong>{{ qualityReport.uniqueness ? `${(qualityReport.uniqueness * 100).toFixed(2)}%` : '—' }}</strong><small>过滤 {{ formatNumber(lastIngestion?.rows_dropped) }} 条</small></article><article class="mini-stat"><span>数据库状态</span><strong>{{ apiConnected ? '正常' : '异常' }}</strong><small>SQL Server 2022</small></article></section>
          <section class="panel field-quality-panel" :aria-busy="qualityMatrixLoading"><div class="panel-head"><div><h2>字段级质量矩阵</h2><p>逐字段比较完整性与有效性；数值越低越需要优先治理</p></div><div class="matrix-controls"><select v-model="qualityDomain" aria-label="筛选主题域"><option value="all">全部主题域</option><option v-for="domain in qualityDomains" :key="domain" :value="domain">{{ domain }}</option></select><select v-model="qualitySort" aria-label="字段质量排序"><option value="score">质量最低优先</option><option value="change">下降最多优先</option></select><button class="outline-button" :disabled="qualityMatrixLoading" @click="loadFieldQuality"><AppIcon name="refresh" :size="13" />刷新</button></div></div><div v-if="qualityMatrixLoading && !qualityMatrix.fields.length" class="matrix-empty">正在汇总 33 个字段的年度质量…</div><div v-else-if="qualityMatrixError" class="matrix-empty error">{{ qualityMatrixError }}</div><div v-else class="table-wrap quality-matrix-wrap"><table class="quality-matrix"><thead><tr><th>字段</th><th>主题域</th><th v-for="year in qualityMatrix.years" :key="year">{{ year }}</th><th>总体</th><th>首末年变化</th></tr></thead><tbody><tr v-for="field in visibleQualityFields" :key="field.field"><td><strong>{{ field.label }}</strong><small>{{ field.field }}</small></td><td><span class="domain-tag">{{ field.domain }}</span></td><td v-for="point in field.yearly" :key="`${field.field}-${point.year}`"><span class="matrix-score" :class="{ conditional: field.conditional, warning: Number(field.conditional ? point.coverage_pct : point.score_pct) < 95 }">{{ formatOptionalNumber(field.conditional ? point.coverage_pct : point.score_pct, 1) }}%</span></td><td><strong>{{ formatOptionalNumber(field.conditional ? field.coverage_pct : field.score_pct, 1) }}%</strong><small>{{ field.metric_label }}</small></td><td><em :class="Number(field.change_pct) < 0 ? 'negative-text' : 'positive-text'">{{ field.change_pct == null ? '—' : `${field.change_pct >= 0 ? '+' : ''}${field.change_pct.toFixed(1)} 个百分点` }}</em></td></tr></tbody></table></div><p v-if="qualityMatrix.caveat" class="matrix-caveat"><AppIcon name="info" :size="12" />{{ qualityMatrix.caveat }}</p></section>
          <section class="panel data-table-panel"><div class="panel-head"><div><h2>数据接入任务</h2><p>监控各数据源的同步与处理状态</p></div><button class="primary-button" :disabled="dataLoading" @click="loadDashboard"><AppIcon name="refresh" :size="14" /> {{ dataLoading ? '同步中' : '刷新状态' }}</button></div><div class="table-wrap"><table><thead><tr><th>数据源</th><th>接入类型</th><th>记录数</th><th>更新时间</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="row in pipelineRows" :key="row.source"><td><span class="source-icon"><AppIcon name="database" :size="15" /></span><strong>{{ row.source }}</strong></td><td>{{ row.type }}</td><td>{{ row.records }}</td><td>{{ row.updated }}</td><td><em class="status-tag" :class="row.status.includes('异常') ? 'syncing' : ''">{{ row.status }}</em></td><td><button class="row-action"><AppIcon name="arrow-right" :size="14" /></button></td></tr></tbody></table></div></section>
          <section class="pipeline"><div class="pipeline-head"><h2>数据处理链路</h2><p>从原始数据接入到分析服务的完整流程</p></div><div class="pipeline-steps"><div v-for="(step, index) in ['数据接入', '清洗标准化', '质量校验', 'SQL Server 入库', '分析服务']" :key="step" class="pipeline-step"><span><AppIcon :name="index === 4 ? 'activity' : index === 3 ? 'database' : 'check'" :size="18" /></span><strong>{{ step }}</strong><small>{{ index === 0 ? 'CSV / JSON' : index === 1 ? 'Pandas / BULK' : index === 2 ? '四维评估' : index === 3 ? '结构化存储' : 'RESTful API' }}</small></div></div></section>
        </template>

        <template v-else-if="activeView === 'patients'">
          <section class="panel patient-filter-panel"><div class="panel-head"><div><h2>患者群体筛选</h2><p>以下筛选同步作用于指标、图表和重点分群</p></div><button class="text-button" @click="resetPatientFilters">重置全部</button></div><div class="patient-filter-grid"><label><span>年份</span><select v-model="patientFilters.year" @change="loadPatientProfile"><option value="all">全部年份</option><option v-for="year in availableYears" :key="year" :value="String(year)">{{ year }} 年</option></select></label><label><span>服务区域</span><select v-model="patientFilters.service_area" @change="loadPatientProfile"><option value="">全部区域</option><option v-for="region in ['New York City','Long Island','Hudson Valley','Capital/Adirondacks','Central NY','Western NY','Southern Tier','Finger Lakes']" :key="region">{{ region }}</option></select></label><label><span>疾病</span><select v-model="patientFilters.disease" @change="loadPatientProfile"><option value="">全部疾病</option><option v-for="item in patientDiseaseOptions" :key="item" :value="item">{{ formatDiseaseName(item) }}</option></select></label><label><span>医院</span><select v-model="patientFilters.hospital" @change="loadPatientProfile"><option value="">全部医院</option><option v-for="item in patientHospitalOptions" :key="item.hospital" :value="item.hospital">{{ item.hospital }}</option></select></label><label><span>年龄段</span><select v-model="patientFilters.age_group" @change="loadPatientProfile"><option value="">全部年龄</option><option value="0-17">0—17</option><option value="18-29">18—29</option><option value="30-49">30—49</option><option value="50-69">50—69</option><option value="70+">70+</option></select></label><label><span>性别</span><select v-model="patientFilters.gender" @change="loadPatientProfile"><option value="">全部性别</option><option value="F">女性</option><option value="M">男性</option><option value="U">未知</option></select></label></div><p v-if="patientError" class="patient-filter-error">{{ patientError }}</p></section>
          <section class="patient-banner" :class="{ loading: patientLoading }"><div><span>住院患者群体概览</span><strong>{{ formatNumber(patientTotalRecords) }} <small>出院记录</small></strong><p>当前分析周期：{{ patientPeriodLabel }} · 记录口径并非去重患者人数</p></div><div class="banner-stat"><span>主要年龄组</span><strong>{{ topAgeGroup }}</strong></div><div class="banner-stat"><span>首位疾病</span><strong>{{ topDiseaseName }}</strong></div><div class="banner-stat"><span>筛选维度</span><strong>{{ Object.values(patientFilters).filter(value => value && value !== 'all').length }} 项</strong></div></section>
          <section class="dashboard-grid patient-charts"><article class="panel"><div class="panel-head"><div><h2>年龄段分布</h2><p>患者人口统计学结构</p></div></div><DashboardChart :option="ageOption" height="290px" /></article><article class="panel"><div class="panel-head"><div><h2>性别构成</h2><p>住院出院记录占比</p></div></div><div class="gender-chart-wrap"><DashboardChart :option="genderOption" height="260px" /><div class="gender-legend"><span v-for="item in genderLegend" :key="item.label"><i :class="item.className"></i>{{ item.label }} <strong>{{ item.percent }}%</strong></span></div></div></article><article class="panel"><div class="panel-head"><div><h2>病情严重程度</h2><p>APR 严重程度分级</p></div></div><DashboardChart :option="mortalityOption" height="290px" /></article></section>
          <section class="patient-segments"><div class="panel-head"><div><h2>重点患者分群</h2><p>基于年龄、疾病与严重程度的实时聚合结果</p></div><button class="text-button" @click="selectView('ai')">使用 AI 深入分析 <AppIcon name="arrow-right" :size="14" /></button></div><div class="segment-grid"><article v-for="segment in patientSegments" :key="segment.title"><span class="segment-icon" :class="segment.tone"><AppIcon :name="segment.icon" :size="19" /></span><div><strong>{{ segment.title }}</strong><p>{{ segment.detail }}</p><small>{{ formatNumber(segment.count) }} 条 · 占 {{ Number(segment.ratio || 0).toFixed(1) }}%</small></div></article></div></section>
        </template>

        <template v-else-if="activeView === 'reports'">
          <section class="report-toolbar"><div class="report-tabs" role="tablist" aria-label="报告类型筛选"><button v-for="tab in reportTabs" :key="tab.id" role="tab" :class="{ active: reportFilter === tab.id }" :aria-selected="reportFilter === tab.id" @click="reportFilter = tab.id">{{ tab.label }} <span>{{ reportTabCount(tab.id) }}</span></button></div><button class="primary-button" :disabled="reportLoading" @click="generateReport()"><AppIcon name="sparkle" :size="15" /> {{ reportLoading ? '生成中' : 'AI 生成报告' }}</button></section>
          <div class="report-filter-summary" aria-live="polite"><span><AppIcon name="check" :size="13" /> 当前分类</span><strong>{{ selectedReportTab.label }}</strong><small>显示 {{ filteredReportCards.length }} 个报告模块</small></div>
          <section class="report-grid"><article v-for="report in filteredReportCards" :key="`${reportFilter}-${report.title}`" class="report-card report-card-enter"><div class="report-cover" :class="report.color"><span class="report-type">{{ report.type }}</span><AppIcon :name="report.icon" :size="42" :stroke-width="1.4" /><i></i><i></i><i></i></div><div class="report-body"><small>{{ report.date }}</small><h2>{{ report.title }}</h2><p>{{ report.desc }}</p><div><button @click="generateReport(report)">生成报告 <AppIcon name="arrow-right" :size="13" /></button><button class="icon-button" :disabled="!reportContent" @click="downloadReport"><AppIcon name="download" :size="15" /></button></div></div></article></section>
          <section v-if="reportContent" class="panel generated-report"><div class="panel-head"><div><h2>{{ reportTitle || '最新生成报告' }}</h2><p>Markdown 实时预览</p></div><div class="result-actions"><button v-if="can('system:manage') && reportId" title="发布为公开报告" @click="publishGeneratedReport"><AppIcon name="check" :size="15" /></button><button @click="downloadReport"><AppIcon name="download" :size="15" /></button><button @click="reportContent = ''; reportId = null; reportTitle = ''"><AppIcon name="close" :size="15" /></button></div></div><pre>{{ reportContent }}</pre></section>
          <section class="panel recent-reports report-library"><div class="panel-head"><div><h2>报告库</h2><p>{{ can('system:manage') ? '全部用户生成的持久化报告' : '由当前账户生成的持久化报告' }}</p></div><button class="outline-button" :disabled="reportLibraryLoading" @click="loadReportLibrary"><AppIcon name="refresh" :size="13" />刷新</button></div><p v-if="reportLibraryError" class="library-error">{{ reportLibraryError }}</p><div v-if="reportLibraryLoading && !reportLibrary.length" class="matrix-empty">正在读取报告库…</div><div v-else-if="!reportLibrary.length" class="matrix-empty">尚未生成报告，选择上方模板即可创建第一份报告。</div><div v-else class="table-wrap"><table><thead><tr><th>报告标题</th><th>创建人</th><th>状态</th><th>创建时间</th><th>更新时间</th><th>操作</th></tr></thead><tbody><tr v-for="item in reportLibrary" :key="item.id"><td><strong>{{ item.title }}</strong><small class="report-id">#{{ item.id }}</small></td><td>{{ item.author }}</td><td><em class="status-tag" :class="item.status === 'published' ? '' : 'draft'">{{ reportStatusLabel(item.status) }}</em></td><td>{{ formatDateTime(item.created_at) }}</td><td>{{ formatDateTime(item.updated_at) }}</td><td><div class="library-actions"><button class="text-button" @click="openStoredReport(item.id)">查看</button><button v-if="can('system:manage')" class="text-button" @click="changeReportStatus(item)">{{ item.status === 'published' ? '撤回' : '发布' }}</button></div></td></tr></tbody></table></div></section>
        </template>

        <template v-else-if="activeView === 'public-reports'">
          <PublicReports embedded />
        </template>

        <template v-else-if="activeView === 'account'">
          <AccountSettings embedded />
        </template>
      </main>
    </section>
    <Teleport to="body">
      <Transition name="chart-focus">
        <div v-if="expandedChart" class="chart-modal-backdrop" role="presentation" @click.self="closeExpandedChart">
          <section class="chart-modal-card" role="dialog" aria-modal="true" :aria-label="`${expandedChart.title}放大图表`">
            <header><div><span>CHART FOCUS</span><h2>{{ expandedChart.title }}</h2><p>{{ expandedChart.subtitle }}</p></div><button type="button" aria-label="关闭放大图表" title="关闭" @click="closeExpandedChart"><AppIcon name="close" :size="19" /></button></header>
            <div class="chart-modal-body"><DashboardChart :key="expandedChartKey" :option="expandedChart.option" height="min(68vh, 640px)" @select="selectExpandedChart" /></div>
            <footer><span><AppIcon name="info" :size="12" /> 图表保留悬停提示和原有下钻交互</span><kbd>Esc 关闭</kbd></footer>
          </section>
        </div>
      </Transition>
    </Teleport>
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
.ai-conversation-layout{width:min(1120px,100%);margin:0 auto}.ai-chat-wrap{min-width:0}.section-title{display:flex;align-items:center;gap:11px;margin-bottom:12px}.title-icon{width:38px;height:38px;display:grid;place-items:center;color:#176f6a;background:#e5f3f1;border-radius:11px}.section-title h2{font-size:13px}.section-title p{margin-top:4px;color:#879199;font-size:9px}.ai-connection-state{margin-left:auto;padding:5px 8px;color:#277d75;background:#e7f5f2;border-radius:6px;font-size:8px;font-weight:650}.ai-connection-state.offline{color:#a5675e;background:#faeeee}.ai-chat-wrap .chat-panel{height:clamp(600px,calc(100vh - 205px),800px)}.result-actions{display:flex;gap:5px}.result-actions button{width:28px;height:28px;display:grid;place-items:center;color:#7b878e;background:#f8f9f9;border:1px solid #e5e9eb;border-radius:7px;cursor:pointer}
.data-overview-grid{display:grid;grid-template-columns:1fr 1.15fr;gap:13px}.quality-score-card{display:flex;align-items:center;gap:25px;padding:22px 26px;color:#fff;background:linear-gradient(130deg,#194f4c,#176f69);border-radius:14px;box-shadow:0 10px 30px rgba(18,86,81,.13)}.score-ring{width:112px;height:112px;display:flex;flex-direction:column;align-items:center;justify-content:center;flex:0 0 auto;border:8px solid rgba(255,255,255,.18);outline:3px solid rgba(87,211,193,.85);outline-offset:-6px;border-radius:50%}.score-ring strong{font-size:27px}.score-ring small{color:#afd4cf;font-size:8px}.quality-score-card .tag{display:inline-flex;align-items:center;gap:4px;padding:4px 7px;color:#bce8dc;background:rgba(255,255,255,.1);border-radius:5px;font-size:8px}.quality-score-card h2{margin:12px 0 7px;font-size:17px}.quality-score-card p{max-width:330px;color:#b6cfcc;font-size:10px;line-height:1.6}.quality-bars{padding-top:20px}.quality-row{display:grid;grid-template-columns:50px 1fr 42px;align-items:center;gap:10px;margin:13px 0;color:#66747d;font-size:9px}.quality-row>div{height:6px;overflow:hidden;background:#edf1f2;border-radius:5px}.quality-row i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#2b8d85,#61b9ae)}.quality-row strong{color:#4c5d65;font-size:9px;text-align:right}.data-metrics{margin-top:13px}.mini-stat{padding:16px 18px;background:#fff;border:1px solid var(--line);border-radius:11px}.mini-stat span,.mini-stat small,.mini-stat strong{display:block}.mini-stat span{color:#88949b;font-size:9px}.mini-stat strong{margin:7px 0 4px;font-size:20px}.mini-stat small{color:#8b989e;font-size:8px}.source-icon{display:inline-grid;place-items:center;width:27px;height:27px;margin-right:8px;color:#2b837c;background:#e9f5f3;border-radius:7px;vertical-align:middle}.status-tag{display:inline-block;padding:4px 7px;color:#208176;background:#e7f5f2;border-radius:5px;font-size:8px;font-style:normal}.status-tag.syncing{color:#a36c24;background:#fbf0df}.pipeline{margin-top:13px;padding:20px 22px;background:#fff;border:1px solid var(--line);border-radius:13px}.pipeline-head h2{font-size:13px}.pipeline-head p{margin-top:4px;color:#919ba1;font-size:9px}.pipeline-steps{display:grid;grid-template-columns:repeat(5,1fr);margin-top:20px}.pipeline-step{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center}.pipeline-step:not(:last-child)::after{content:"";position:absolute;left:calc(50% + 25px);top:19px;width:calc(100% - 50px);border-top:1px dashed #bad3d0}.pipeline-step>span{z-index:1;width:40px;height:40px;display:grid;place-items:center;color:#247f77;background:#edf7f5;border:1px solid #d9eeeb;border-radius:11px}.pipeline-step strong{margin-top:8px;font-size:10px}.pipeline-step small{margin-top:3px;color:#97a1a7;font-size:8px}
.patient-banner{display:grid;grid-template-columns:1.5fr repeat(3,.55fr);align-items:center;padding:22px 28px;color:#fff;background:linear-gradient(120deg,#1a504d,#1b716b);border-radius:14px;box-shadow:0 10px 30px rgba(18,86,81,.11)}.patient-banner>div:first-child>span{display:block;color:#9ccac5;font-size:9px}.patient-banner>div:first-child>strong{display:block;margin:7px 0 5px;font-size:27px}.patient-banner strong small{color:#bad5d2;font-size:10px;font-weight:400}.patient-banner p{color:#9fc0bd;font-size:9px}.banner-stat{padding-left:22px;border-left:1px solid rgba(255,255,255,.13)}.banner-stat span,.banner-stat strong{display:block}.banner-stat span{color:#a9c7c4;font-size:9px}.banner-stat strong{margin-top:7px;font-size:17px}.patient-charts{grid-template-columns:1.25fr .9fr 1.15fr}.gender-chart-wrap{display:grid;grid-template-columns:1fr auto;align-items:center}.gender-legend{display:grid;gap:12px}.gender-legend span{display:grid;grid-template-columns:7px 65px auto;align-items:center;gap:6px;color:#7f8b92;font-size:9px}.gender-legend i{width:7px;height:7px;border-radius:2px}.gender-legend i.female{background:#2a8f86}.gender-legend i.male{background:#7398c8}.gender-legend i.unknown{background:#d9dfe4}.gender-legend strong{color:#52616a;font-size:9px}.patient-segments{margin-top:13px;padding:20px;background:#fff;border:1px solid var(--line);border-radius:13px}.segment-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}.segment-grid article{display:flex;align-items:center;gap:13px;padding:15px;border:1px solid #e7ebed;border-radius:10px}.segment-icon{width:38px;height:38px;display:grid;place-items:center;flex:0 0 auto;border-radius:10px}.segment-icon.teal{color:#18786f;background:#e7f5f2}.segment-icon.amber{color:#ad762c;background:#fbf0df}.segment-icon.red{color:#b65d57;background:#faeceb}.segment-grid strong,.segment-grid p,.segment-grid small{display:block}.segment-grid strong{font-size:10px}.segment-grid p{margin:5px 0;color:#879199;font-size:8px}.segment-grid small{color:#527b76;font-size:8px}
.report-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.report-tabs{display:flex;gap:5px;padding:4px;background:#e9edee;border-radius:9px}.report-tabs button{padding:8px 13px;border:1px solid transparent;border-radius:7px;color:#758189;background:transparent;font-size:9px;cursor:pointer;transition:color .18s,background .18s,box-shadow .18s,transform .18s}.report-tabs button:hover{color:#2f615d;background:rgba(255,255,255,.6)}.report-tabs button.active{color:#fff;background:var(--teal);border-color:var(--teal);box-shadow:0 5px 13px rgba(23,111,106,.24);transform:translateY(-1px);font-weight:700}.report-tabs span{display:inline-grid;min-width:16px;height:16px;margin-left:4px;place-items:center;color:#4f8b86;background:rgba(255,255,255,.72);border-radius:8px;font-size:8px}.report-tabs button.active span{color:var(--teal);background:#fff}.report-filter-summary{display:flex;align-items:center;gap:8px;margin-bottom:12px;padding:9px 12px;color:#678079;background:#edf7f5;border:1px solid #d8ece8;border-radius:9px;font-size:9px}.report-filter-summary span{display:inline-flex;align-items:center;gap:5px}.report-filter-summary strong{color:#176f6a;font-size:10px}.report-filter-summary small{margin-left:auto;color:#83938f}.report-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.report-card{overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);transition:transform .25s,box-shadow .25s}.report-card-enter{animation:report-card-in .16s ease-out both}.report-card:hover{transform:translateY(-3px);box-shadow:0 12px 28px rgba(31,45,52,.08)}@keyframes report-card-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){.report-card-enter{animation:none}}.report-cover{position:relative;height:138px;display:flex;align-items:center;justify-content:center;overflow:hidden}.report-cover.teal{color:#4fa49b;background:#e8f4f2}.report-cover.blue{color:#6b91c2;background:#edf2f8}.report-cover.amber{color:#d09a50;background:#fbf1e3}.report-cover.violet{color:#8879b7;background:#f0edf7}.report-cover .report-type{position:absolute;left:13px;top:12px;padding:4px 7px;color:currentColor;background:rgba(255,255,255,.7);border-radius:5px;font-size:8px;font-weight:600}.report-cover i{position:absolute;height:1px;background:currentColor;opacity:.18}.report-cover i:nth-of-type(1){width:70%;left:15%;bottom:27px}.report-cover i:nth-of-type(2){width:48%;left:15%;bottom:20px}.report-cover i:nth-of-type(3){width:60%;left:15%;bottom:13px}.report-body{padding:16px}.report-body>small{color:#98a1a7;font-size:8px}.report-body h2{margin:7px 0;font-size:12px}.report-body p{min-height:39px;color:#7d8990;font-size:9px;line-height:1.55}.report-body>div{display:flex;align-items:center;justify-content:space-between;margin-top:13px;padding-top:11px;border-top:1px solid #edf0f1}.report-body>div>button:first-child{display:flex;align-items:center;gap:4px;color:#327c76;border:0;background:transparent;font-size:9px;cursor:pointer}.report-body .icon-button{width:27px;height:27px;border:1px solid #e4e8ea}.recent-reports{margin-top:13px}.activity-list>div{display:flex;align-items:center;gap:11px;padding:11px 0;border-top:1px solid #edf0f1}.activity-list>div:first-child{border-top:0}.activity-icon{width:31px;height:31px;display:grid;place-items:center;color:#287f78;background:#eaf5f3;border-radius:8px}.activity-list>div>div{flex:1}.activity-list strong{font-size:10px}.activity-list p{margin-top:4px;color:#959fa5;font-size:8px}
.api-error{display:flex;align-items:center;gap:8px;margin:-10px 0 16px;padding:10px 12px;color:#9b5a43;background:#fff5ee;border:1px solid #f0d8ca;border-radius:9px;font-size:10px}.status-dot.offline,.demo-pill span.offline{background:#d47669;box-shadow:0 0 0 4px rgba(212,118,105,.1)}.primary-button:disabled{cursor:wait;opacity:.62}.generated-report{margin-top:13px}.generated-report pre{max-height:520px;overflow:auto;margin:12px 0 0;padding:18px;color:#42545d;background:#f7f9f9;border:1px solid #e7ebed;border-radius:10px;font:11px/1.8 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}.mobile-overlay{display:none}@media(max-width:1180px){.metric-grid{grid-template-columns:repeat(2,1fr)}.primary-row{grid-template-columns:1fr}.secondary-row{grid-template-columns:repeat(2,1fr)}.secondary-row>:last-child{grid-column:span 2}.report-grid{grid-template-columns:repeat(2,1fr)}.patient-charts{grid-template-columns:1fr 1fr}.patient-charts>:last-child{grid-column:span 2}}@media(max-width:800px){.sidebar{transform:translateX(-100%);transition:transform .25s}.sidebar.open{transform:translateX(0)}.workspace{margin-left:0}.mobile-overlay{position:fixed;inset:0;z-index:19;display:block;background:rgba(17,32,34,.42);backdrop-filter:blur(2px)}.mobile-menu{display:block}.topbar{height:60px;padding:0 18px}.global-search{display:none}.demo-pill,.profile>div:not(.avatar),.profile>svg{display:none}.profile{padding-left:8px}.content{padding:23px 17px 38px}.page-heading{align-items:flex-start;flex-direction:column}.filters{width:100%;overflow-x:auto}.metric-grid,.secondary-row,.data-overview-grid,.patient-charts,.segment-grid{grid-template-columns:1fr}.secondary-row>:last-child,.patient-charts>:last-child{grid-column:auto}.patient-banner{grid-template-columns:1fr 1fr;gap:20px}.patient-banner>div:first-child{grid-column:span 2}.banner-stat{padding-left:0;border-left:0}.report-grid{grid-template-columns:1fr}.pipeline-steps{grid-template-columns:1fr;gap:10px}.pipeline-step{align-items:flex-start;padding-left:50px;text-align:left}.pipeline-step>span{position:absolute;left:0}.pipeline-step:not(:last-child)::after{left:19px;top:40px;width:1px;height:calc(100% - 30px);border-top:0;border-left:1px dashed #bad3d0}.gender-chart-wrap{grid-template-columns:1fr}.gender-legend{grid-template-columns:repeat(3,1fr)}.gender-legend span{grid-template-columns:7px 1fr}.gender-legend strong{grid-column:2}.report-toolbar{align-items:flex-start;gap:10px;flex-direction:column}.report-tabs{max-width:100%;overflow-x:auto}.ai-connection-state{display:none}.ai-chat-wrap .chat-panel{height:calc(100vh - 185px);min-height:560px}.page-heading h1{font-size:22px}}@media(max-width:480px){.metric-grid{grid-template-columns:1fr}.metric-card{padding-left:68px}.filters label:first-child{display:none}.patient-banner{grid-template-columns:1fr}.patient-banner>div:first-child{grid-column:auto}.quality-score-card{align-items:flex-start;flex-direction:column}.report-tabs button{white-space:nowrap}.gender-legend{grid-template-columns:1fr}.topbar-actions{gap:5px}.content{padding-inline:12px}}
</style>

<style>
.filters select:disabled{cursor:wait;opacity:.58}
.filter-loading{display:inline-flex!important;align-items:center;gap:5px!important;margin:0!important;color:#39817a!important;font-size:9px!important;white-space:nowrap}
.filter-loading svg{animation:filter-spin .8s linear infinite}
@keyframes filter-spin{to{transform:rotate(360deg)}}
.cost-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(300px,.75fr);gap:15px;align-items:start}
.cost-form-panel{padding:21px 23px}.model-badge{padding:5px 8px;color:#277d75;background:#e7f5f2;border-radius:6px;font-size:9px;font-weight:700}
.cost-form-section{margin-top:18px;padding-top:16px;border-top:1px solid #edf0f1}.cost-form-section:first-child{margin-top:8px;padding-top:0;border-top:0}.cost-form-section h3{margin-bottom:12px;color:#41535c;font-size:11px}
.cost-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px 13px}.cost-field-grid label{display:grid;align-content:start;gap:6px;color:#68767f;font-size:9px}.cost-field-grid label.wide{grid-column:span 2}.cost-field-grid label small{min-height:12px;color:#84929a;font-size:8px;line-height:12px}
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

<style>
.decision-row{grid-template-columns:repeat(3,minmax(0,1fr))}
.analysis-badge{flex:0 0 auto;padding:4px 7px;color:#277b74;background:#eaf5f3;border-radius:6px;font-size:8px;font-weight:650}
.analytics-empty{height:285px;display:grid;place-items:center;color:#95a0a6;background:#f8faf9;border:1px dashed #dce5e3;border-radius:9px;font-size:10px}
.insights-warning,.analytics-caveat{display:flex;align-items:center;gap:6px;margin:12px 2px 0;color:#8a744e;font-size:9px}
.analytics-caveat{color:#87939a}
.compare-trigger.active{color:#fff;background:var(--teal);border-color:var(--teal)}
.filter-context{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:-10px 0 15px;color:#869198;font-size:9px}.filter-context>span{font-weight:650}.filter-context button{padding:5px 8px;color:#277b74;background:#eaf5f3;border:1px solid #d7ebe8;border-radius:6px;font-size:9px;cursor:pointer}.filter-context .clear-all{color:#8b6964;background:#fbefed;border-color:#f1dcd8}
.comparison-panel{margin:13px 0 0;padding:20px 22px}.comparison-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.comparison-head h2{margin-top:3px;font-size:14px}.comparison-head p{margin-top:5px;color:#8a969c;font-size:9px}.comparison-tabs,.ranking-tabs{display:flex;gap:4px;padding:3px;background:#eef2f2;border-radius:8px}.comparison-tabs button,.ranking-tabs button{padding:6px 9px;color:#75828a;background:transparent;border:0;border-radius:6px;font-size:9px;cursor:pointer}.comparison-tabs button.active,.ranking-tabs button.active{color:#fff;background:var(--teal);box-shadow:0 3px 8px rgba(23,111,106,.18)}
.comparison-controls{display:flex;align-items:flex-end;gap:10px;margin-top:16px;padding:13px;background:#f7f9f9;border:1px solid #e9edee;border-radius:10px}.comparison-controls label{display:grid;gap:5px;min-width:180px;flex:1;color:#7c898f;font-size:8px}.comparison-controls select{width:100%;height:34px;padding:0 30px 0 9px;color:#3d5159;background:#fff;border:1px solid #dce4e5;border-radius:7px;font-size:10px}.comparison-controls>span{align-self:center;margin-top:14px;color:#9aa4a9;font-size:9px;font-weight:700}.ai-action,.compare-run{display:inline-flex;align-items:center;justify-content:center;gap:5px;height:34px;padding:0 11px;border-radius:7px;font-size:9px;cursor:pointer}.ai-action{margin-left:auto;color:#fff;background:#207f77;border:1px solid #207f77}.compare-run{color:#277b74;background:#e9f5f3;border:1px solid #cfe7e3;font-weight:650}.ai-action.compact{height:28px;flex:0 0 auto;padding:0 8px;color:#277b74;background:#e9f5f3;border-color:#d7ebe8}.ai-action:hover,.compare-run:hover{filter:brightness(.95)}.ai-action:disabled,.compare-run:disabled{opacity:.5;cursor:not-allowed}
.comparison-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px}.comparison-metrics article{padding:13px;border:1px solid #e7ecec;border-radius:9px}.comparison-metrics article>span{color:#879399;font-size:8px}.comparison-metrics article>div{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:5px;margin-top:9px}.comparison-metrics strong{font-size:12px}.comparison-metrics strong:last-child{text-align:right}.comparison-metrics small{color:#8e999f;font-size:7px;font-weight:500}.comparison-metrics b{color:#a1aaae;font-size:7px;font-weight:500}.comparison-metrics p{margin-top:8px;padding-top:7px;border-top:1px solid #edf0f1;font-size:8px}.positive-text{color:#258178}.negative-text{color:#be6961}
.hospital-compare-status{display:flex;align-items:center;gap:5px;margin:12px 2px 0;color:#77868d;font-size:9px}.hospital-compare-status.error{color:#b7665f}.hospital-compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.hospital-compare-grid>article{min-width:0;padding:15px;border:1px solid #e5ebeb;border-radius:10px;background:#fff}.hospital-trend,.hospital-case-mix{grid-column:1/-1}.hospital-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}.hospital-section-head h3{color:#314950;font-size:11px}.hospital-section-head p{margin-top:4px;color:#8b989e;font-size:8px}.hospital-section-head>span{flex:0 0 auto;padding:4px 7px;color:#277b74;background:#eaf5f3;border-radius:5px;font-size:7px}.hospital-mix-table{display:grid;gap:10px}.hospital-mix-row{display:grid;grid-template-columns:minmax(90px,1.2fr) 1fr 1fr;align-items:center;gap:9px}.hospital-mix-row>strong{overflow:hidden;color:#52646c;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.hospital-mix-row>div{display:grid;gap:4px}.hospital-mix-row span{color:#77868d;font-size:7px}.hospital-mix-row i{display:block;height:5px;overflow:hidden;background:#eef2f2;border-radius:4px}.hospital-mix-row em{display:block;height:100%;min-width:2px;border-radius:4px}.mix-a{background:#238b82}.mix-b{background:#7397c8}.hospital-mix-table.compact .hospital-mix-row{grid-template-columns:minmax(75px,1fr) 1fr 1fr}.case-mix-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.case-mix-grid>div{display:grid;grid-template-columns:auto 1fr auto 1fr auto;align-items:baseline;gap:6px;padding:12px;background:#f7f9f9;border-radius:8px}.case-mix-grid b{grid-column:1/-1;color:#53666e;font-size:8px}.case-mix-grid strong{color:#1d756e;font-size:17px}.case-mix-grid small{color:#86949a;font-size:7px}.case-mix-grid p{grid-column:1/-1;margin-top:5px;color:#74838a;font-size:8px}.hospital-caveat{margin-top:12px;color:#87949a;font-size:8px}
.chart-click-card{transition:border-color .18s ease,box-shadow .18s ease,transform .18s ease}.chart-click-card:hover{border-color:#c9dfdc;box-shadow:0 12px 30px rgba(28,92,87,.09);transform:translateY(-2px)}.chart-click-card:focus-visible{outline:2px solid rgba(23,111,106,.38);outline-offset:3px}body.chart-modal-open{overflow:hidden}.chart-modal-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:28px;background:rgba(18,34,37,.58);backdrop-filter:blur(6px)}.chart-modal-card{width:min(1180px,calc(100vw - 56px));max-height:calc(100vh - 56px);overflow:hidden;background:#fff;border:1px solid rgba(255,255,255,.72);border-radius:18px;box-shadow:0 28px 80px rgba(9,31,31,.28)}.chart-modal-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:20px 24px 16px;border-bottom:1px solid #e8eded}.chart-modal-card>header span{color:#2d8981;font-size:8px;font-weight:750;letter-spacing:.16em}.chart-modal-card>header h2{margin-top:5px;color:#283b43;font-size:18px}.chart-modal-card>header p{margin-top:5px;color:#849198;font-size:10px}.chart-modal-card>header button{width:34px;height:34px;display:grid;place-items:center;flex:0 0 auto;color:#66777f;background:#f5f7f7;border:1px solid #e1e7e8;border-radius:9px;cursor:pointer}.chart-modal-card>header button:hover{color:#a95550;background:#faeeee;border-color:#f0d5d2}.chart-modal-body{padding:14px 22px 4px}.chart-modal-card>footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 24px 14px;color:#87949a;font-size:8px}.chart-modal-card>footer span{display:inline-flex;align-items:center;gap:5px}.chart-modal-card>footer kbd{padding:4px 7px;color:#66777f;background:#f4f6f6;border:1px solid #dfe5e6;border-radius:5px;font-size:8px}.chart-focus-enter-active,.chart-focus-leave-active{transition:opacity .2s ease}.chart-focus-enter-active .chart-modal-card,.chart-focus-leave-active .chart-modal-card{transition:transform .22s ease,opacity .18s ease}.chart-focus-enter-from,.chart-focus-leave-to{opacity:0}.chart-focus-enter-from .chart-modal-card{opacity:0;transform:translateY(18px) scale(.97)}.chart-focus-leave-to .chart-modal-card{opacity:0;transform:translateY(8px) scale(.985)}
.field-quality-panel{margin-top:13px}.matrix-controls{display:flex;align-items:center;gap:7px}.matrix-controls select{height:34px;padding:0 28px 0 10px;color:#53616a;background:#fff;border:1px solid #dde3e5;border-radius:8px;font-size:9px}.matrix-empty{padding:32px;color:#89959c;text-align:center;font-size:10px}.matrix-empty.error,.library-error,.patient-filter-error{color:#a85d53}.quality-matrix-wrap{max-height:520px}.quality-matrix thead{position:sticky;top:0;z-index:2}.quality-matrix td:first-child strong,.quality-matrix td:first-child small{display:block}.quality-matrix td:first-child small,.quality-matrix td:nth-last-child(2) small{margin-top:3px;color:#98a2a8;font-size:7px}.domain-tag{padding:3px 6px;color:#527873;background:#eef6f5;border-radius:5px;font-size:8px}.matrix-score{display:inline-block;min-width:47px;padding:4px 6px;color:#1d7f75;background:#e8f5f2;border-radius:5px;text-align:center}.matrix-score.warning{color:#a76b25;background:#fbf0df}.matrix-score.conditional{border:1px dashed #86bdb7}.matrix-caveat{display:flex;align-items:center;gap:6px;margin-top:11px;color:#86939a;font-size:8px;line-height:1.5}
.patient-filter-panel{margin-bottom:13px}.patient-filter-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}.patient-filter-grid label{display:grid;gap:5px;color:#75828a;font-size:8px}.patient-filter-grid select{width:100%;height:35px;padding:0 8px;color:#40525b;background:#fafcfc;border:1px solid #dfe6e8;border-radius:7px;font-size:9px}.patient-filter-error{margin-top:9px;font-size:9px}.patient-banner.loading{opacity:.66}.report-id{margin-left:7px;color:#a0a9ae;font-size:8px}.status-tag.draft{color:#8a6d3e;background:#fbf2e4}.library-actions{display:flex;gap:12px}.report-library .panel-head{align-items:center}.library-error{margin:8px 0;font-size:9px}
.ranking-tabs{width:max-content;margin:3px 0 4px}.ranking-tabs button{padding:5px 7px;font-size:8px}.ranking-empty{height:250px}
@media(max-width:1180px){.patient-filter-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:1180px){.decision-row{grid-template-columns:repeat(2,1fr)}.decision-row>:last-child{grid-column:span 2}.comparison-metrics{grid-template-columns:repeat(2,1fr)}}
@media(max-width:800px){.decision-row{grid-template-columns:1fr}.decision-row>:last-child{grid-column:auto}.comparison-head,.comparison-controls{align-items:stretch;flex-direction:column}.comparison-controls label{min-width:0}.comparison-controls>span{align-self:center;margin:0}.comparison-controls .ai-action,.comparison-controls .compare-run{width:100%;margin-left:0}.comparison-metrics{grid-template-columns:1fr 1fr}.hospital-compare-grid{grid-template-columns:1fr}.hospital-trend,.hospital-case-mix{grid-column:auto}.hospital-mix-row{grid-template-columns:minmax(80px,1fr) 1fr 1fr}.case-mix-grid{grid-template-columns:1fr}.chart-modal-backdrop{padding:12px}.chart-modal-card{width:calc(100vw - 24px);max-height:calc(100vh - 24px);border-radius:13px}.chart-modal-card>header{padding:15px 16px 12px}.chart-modal-card>header h2{font-size:15px}.chart-modal-body{padding:8px 8px 0}.chart-modal-card>footer{padding:8px 16px 12px}.chart-modal-card>footer span{max-width:70%}.matrix-controls{width:100%;align-items:stretch;flex-wrap:wrap}.field-quality-panel .panel-head{flex-direction:column}.matrix-controls select{flex:1}.patient-filter-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.comparison-metrics{grid-template-columns:1fr}.comparison-tabs{width:100%}.comparison-tabs button{flex:1}.patient-filter-grid{grid-template-columns:1fr}}
</style>

<style>
/* 医院对比详情使用非对称主次布局，卡片高度由内容决定。 */
.hospital-compare-grid{grid-template-columns:1fr;gap:16px}
.hospital-detail-mosaic{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1.16fr) minmax(340px,.84fr);gap:16px;align-items:start}
.hospital-detail-mosaic.single{grid-template-columns:1fr}
.hospital-side-stack{display:grid;gap:16px;margin-top:24px}
.hospital-detail-mosaic .hospital-mix-card{position:relative;min-width:0;overflow:hidden;padding:20px 21px 21px;background:#fff;border:1px solid #dfe7e5;border-radius:15px;box-shadow:0 8px 24px rgba(24,65,61,.045)}
.hospital-detail-mosaic .hospital-mix-card::before{content:"";position:absolute;inset:0 0 auto;height:3px;background:#279587}
.hospital-detail-mosaic .severity-mix-card::before{background:#7598c7}
.hospital-detail-mosaic .admission-mix-card::before{background:#d3a35d}
.hospital-detail-mosaic .hospital-section-head{margin-bottom:16px}
.hospital-detail-mosaic .hospital-section-head h3{font-size:14px}
.hospital-detail-mosaic .hospital-section-head p{font-size:11px}
.hospital-detail-mosaic .hospital-section-head>span{font-size:10px}
.hospital-detail-mosaic .hospital-mix-table{gap:13px}
.hospital-detail-mosaic .hospital-mix-row>strong{font-size:11px}
.hospital-detail-mosaic .hospital-mix-row span{font-size:10px}
.hospital-detail-mosaic .hospital-mix-row i{height:6px;background:#edf2f1}
.hospital-detail-mosaic .severity-mix-card{background:#fbfcfe}
.hospital-detail-mosaic .admission-mix-card{margin-right:26px;background:#fffdf9}
.hospital-detail-mosaic .disease-mix-card{margin-left:8px}
@media(max-width:1050px){.hospital-detail-mosaic{grid-template-columns:1fr}.hospital-side-stack{margin-top:0}.hospital-detail-mosaic .admission-mix-card{margin-right:0}.hospital-detail-mosaic .disease-mix-card{margin-left:0}}
</style>
