<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { analyticsApi } from '../api/analytics.js'
import ChartCard from '../components/ChartCard.vue'
import MetricCard from '../components/MetricCard.vue'
import { formatCount, formatCurrency, formatDecimal } from '../utils/format.js'

const resources = reactive(
  Object.fromEntries(
    ['diseases', 'diseaseCost', 'hospitals', 'age', 'payments', 'severity', 'trends'].map((key) => [
      key,
      { loading: true, data: [], error: '' },
    ]),
  ),
)
const overview = reactive({ loading: true, data: {}, error: '' })
const health = ref('checking')
const lastUpdated = ref('')

const palette = ['#246b8e', '#2f8f83', '#d18a32', '#6f7f93', '#9b6a8f', '#4e8b57']
const baseGrid = { left: 44, right: 20, top: 18, bottom: 44, containLabel: true }
const axisLabel = { color: '#667085', fontSize: 11 }

async function loadResource(key, request) {
  resources[key].loading = true
  resources[key].error = ''
  try {
    const payload = await request()
    resources[key].data = payload.data || []
    if (key === 'trends' && payload.meta?.trend_available === false) {
      resources[key].data = []
      resources[key].note = payload.meta.note
    }
  } catch (error) {
    resources[key].error = error.message
  } finally {
    resources[key].loading = false
  }
}

async function loadDashboard() {
  overview.loading = true
  overview.error = ''
  health.value = 'checking'
  const filters = {}
  const healthPromise = analyticsApi
    .health()
    .then(() => (health.value = 'online'))
    .catch(() => (health.value = 'offline'))
  const overviewPromise = analyticsApi
    .overview(filters)
    .then((payload) => (overview.data = payload.data || {}))
    .catch((error) => (overview.error = error.message))
    .finally(() => (overview.loading = false))

  await Promise.allSettled([
    healthPromise,
    overviewPromise,
    loadResource('diseases', () => analyticsApi.diseasesTop(filters)),
    loadResource('diseaseCost', () => analyticsApi.diseasesCost(filters)),
    loadResource('hospitals', () => analyticsApi.hospitalsTop(filters)),
    loadResource('age', () => analyticsApi.ageDistribution(filters)),
    loadResource('payments', () => analyticsApi.paymentsDistribution(filters)),
    loadResource('severity', () => analyticsApi.severityDistribution(filters)),
    loadResource('trends', () => analyticsApi.yearlyTrends(filters)),
  ])
  lastUpdated.value = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date())
}

const horizontalBar = (state, nameKey, valueKey, color = palette[0], currency = false) => ({
  color: [color],
  grid: { ...baseGrid, left: 26, bottom: 28 },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    valueFormatter: currency ? (value) => formatCurrency(value) : undefined,
  },
  xAxis: { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } },
  yAxis: {
    type: 'category',
    inverse: true,
    data: state.data.map((row) => row[nameKey]),
    axisLabel: { ...axisLabel, width: 150, overflow: 'truncate' },
    axisTick: { show: false },
    axisLine: { show: false },
  },
  series: [{ type: 'bar', data: state.data.map((row) => row[valueKey]), barMaxWidth: 18 }],
})

const diseaseOption = computed(() => horizontalBar(resources.diseases, 'diagnosis', 'record_count'))
const hospitalOption = computed(() => horizontalBar(resources.hospitals, 'hospital', 'record_count', palette[1]))
const costOption = computed(() =>
  horizontalBar(resources.diseaseCost, 'diagnosis', 'avg_total_charges', palette[2], true),
)
const ageOption = computed(() => ({
  color: [palette[0]],
  grid: baseGrid,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: {
    type: 'category',
    data: resources.age.data.map((row) => row.age_group),
    axisLabel: { ...axisLabel, rotate: 24 },
    axisTick: { show: false },
  },
  yAxis: { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } },
  series: [{ type: 'bar', data: resources.age.data.map((row) => row.record_count), barMaxWidth: 34 }],
}))
const paymentOption = computed(() => ({
  color: palette,
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 条（{d}%）' },
  legend: { bottom: 0, type: 'scroll', textStyle: axisLabel },
  series: [
    {
      type: 'pie',
      radius: ['43%', '68%'],
      center: ['50%', '43%'],
      label: { formatter: '{b}\n{d}%', color: '#475467' },
      data: resources.payments.data.map((row) => ({ name: row.payment_type, value: row.record_count })),
    },
  ],
}))
const severityOption = computed(() => ({
  color: [palette[4]],
  grid: baseGrid,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: {
    type: 'category',
    data: resources.severity.data.map((row) => row.severity),
    axisLabel,
    axisTick: { show: false },
  },
  yAxis: { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } },
  series: [{ type: 'bar', data: resources.severity.data.map((row) => row.record_count), barMaxWidth: 38 }],
}))
const trendOption = computed(() => ({
  color: [palette[0], palette[2]],
  grid: baseGrid,
  tooltip: { trigger: 'axis' },
  legend: { data: ['住院记录', '平均费用'], bottom: 0, textStyle: axisLabel },
  xAxis: {
    type: 'category',
    data: resources.trends.data.map((row) => row.year),
    axisLabel,
    boundaryGap: false,
  },
  yAxis: [
    { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } },
    { type: 'value', axisLabel: { ...axisLabel, formatter: '${value}' }, splitLine: { show: false } },
  ],
  series: [
    {
      name: '住院记录',
      type: 'line',
      data: resources.trends.data.map((row) => row.record_count),
      smooth: true,
      symbolSize: 7,
    },
    {
      name: '平均费用',
      type: 'line',
      yAxisIndex: 1,
      data: resources.trends.data.map((row) => row.avg_total_charges),
      smooth: true,
      symbolSize: 7,
    },
  ],
}))

onMounted(loadDashboard)
</script>

<template>
  <main class="page-shell">
    <header class="app-header">
      <div class="brand-mark" aria-hidden="true">医</div>
      <div class="app-title">
        <p>MEDICAL DATA INTELLIGENCE</p>
        <h1>智慧医疗大数据与 AI 大模型分析平台</h1>
      </div>
      <div class="header-actions">
        <RouterLink class="header-link" to="/data-quality">数据质量</RouterLink>
        <RouterLink class="header-link" to="/ai">AI 智能分析</RouterLink>
        <span class="service-status" :class="`status-${health}`">
          <i />{{ health === 'online' ? '数据服务正常' : health === 'offline' ? '数据服务异常' : '检查服务中' }}
        </span>
        <button type="button" @click="loadDashboard">刷新数据</button>
      </div>
    </header>

    <section class="content">
      <div class="section-heading">
        <div>
          <h2>住院数据概览</h2>
          <p>统计结果实时来自 Flask API 与 MySQL，不包含前端硬编码业务数据。</p>
        </div>
        <span v-if="lastUpdated">更新时间 {{ lastUpdated }}</span>
      </div>

      <div v-if="overview.error" class="overview-error" role="alert">{{ overview.error }}</div>
      <section class="metric-grid">
        <MetricCard label="住院记录数" :value="formatCount(overview.data.total_records)" hint="清洗后记录" :loading="overview.loading" />
        <MetricCard label="医疗机构数" :value="formatCount(overview.data.facility_count)" hint="去重机构" :loading="overview.loading" />
        <MetricCard label="平均住院天数" :value="formatDecimal(overview.data.avg_length_of_stay)" hint="天" :loading="overview.loading" />
        <MetricCard label="平均医疗费用" :value="formatCurrency(overview.data.avg_total_charges)" hint="Total Charges" :loading="overview.loading" />
      </section>

      <section class="chart-grid">
        <ChartCard title="疾病 Top 10" subtitle="按住院记录数排序（数据中无患者唯一标识）" :state="resources.diseases" :option="diseaseOption" />
        <ChartCard title="年龄分布" subtitle="不同年龄组住院记录数" :state="resources.age" :option="ageOption" />
        <ChartCard title="医疗费用分布" subtitle="疾病平均 Total Charges" :state="resources.diseaseCost" :option="costOption" />
        <ChartCard title="医院住院量排行" subtitle="医疗机构住院记录 Top 10" :state="resources.hospitals" :option="hospitalOption" />
        <ChartCard title="支付方式分布" subtitle="Payment Typology 1 占比" :state="resources.payments" :option="paymentOption" />
        <ChartCard title="病情严重程度" subtitle="APR 严重程度病例分布" :state="resources.severity" :option="severityOption" />
        <ChartCard
          class="chart-wide"
          title="年度趋势"
          subtitle="住院量与平均医疗费用"
          :state="resources.trends"
          :option="trendOption"
          :empty-text="resources.trends.note || '当前数据不足以形成年度趋势'"
        />
      </section>
    </section>
  </main>
</template>
