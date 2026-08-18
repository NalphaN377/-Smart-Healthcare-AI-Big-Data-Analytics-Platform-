<script setup>
import { computed, onMounted, reactive } from 'vue'

import { dataQualityApi } from '../api/dataQuality.js'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import { formatCount, formatDecimal } from '../utils/format.js'

const state = reactive({ loading: true, error: '', summary: {}, fields: [] })

const fieldLabels = {
  age_group: '年龄组',
  facility_name: '医疗机构',
  diagnosis_description: '诊断描述',
  severity: '严重程度',
  payment_type_1: '第一支付方式',
  length_of_stay: '住院天数',
  total_charges: '总费用',
  total_costs: '总成本',
}
const anomalyLabels = {
  negative_charges: '负数费用',
  negative_costs: '负数成本',
  invalid_length_of_stay: '非法住院天数',
  invalid_birth_weight: '非法出生体重',
  invalid_year: '非法年份',
  invalid_emergency_indicator: '非法急诊标志',
}

const overallScore = computed(() => {
  const values = [
    state.summary.completeness_score,
    state.summary.validity_score,
    state.summary.consistency_score,
  ].filter((value) => Number.isFinite(value))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
})

const missingOption = computed(() => ({
  color: ['#246b8e'],
  grid: { left: 44, right: 20, top: 20, bottom: 62, containLabel: true },
  tooltip: { trigger: 'axis', valueFormatter: (value) => `${value}%` },
  xAxis: {
    type: 'category',
    data: state.fields.map((row) => fieldLabels[row.field] || row.field),
    axisLabel: { color: '#667085', rotate: 25 },
  },
  yAxis: {
    type: 'value',
    name: '缺失率（%）',
    axisLabel: { color: '#667085', formatter: '{value}%' },
    splitLine: { lineStyle: { color: '#eef1f4' } },
  },
  series: [{ type: 'bar', data: state.fields.map((row) => row.missing_rate), barMaxWidth: 38 }],
}))

const anomalyRows = computed(() =>
  Object.entries(state.summary.anomalies || {}).map(([key, value]) => ({
    key,
    label: anomalyLabels[key] || key,
    value,
  })),
)
const anomalyOption = computed(() => ({
  color: ['#d18a32'],
  grid: { left: 36, right: 20, top: 20, bottom: 62, containLabel: true },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: anomalyRows.value.map((row) => row.label),
    axisLabel: { color: '#667085', rotate: 25 },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#667085' },
    splitLine: { lineStyle: { color: '#eef1f4' } },
  },
  series: [{ type: 'bar', data: anomalyRows.value.map((row) => row.value), barMaxWidth: 38 }],
}))

async function loadQuality() {
  state.loading = true
  state.error = ''
  try {
    const [summary, fields] = await Promise.all([dataQualityApi.summary(), dataQualityApi.fields()])
    state.summary = summary.data || {}
    state.fields = fields.data || []
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

onMounted(loadQuality)
</script>

<template>
  <main class="page-shell">
    <header class="app-header">
      <div class="brand-mark" aria-hidden="true">质</div>
      <div class="app-title">
        <p>DATA QUALITY OBSERVABILITY</p>
        <h1>医疗数据质量监控</h1>
      </div>
      <nav class="header-actions" aria-label="主要导航">
        <RouterLink class="header-link" to="/">数据驾驶舱</RouterLink>
        <RouterLink class="header-link" to="/cost-prediction">费用估计</RouterLink>
        <RouterLink class="header-link" to="/ai">AI 智能分析</RouterLink>
        <button type="button" @click="loadQuality">刷新快照</button>
      </nav>
    </header>

    <section class="content quality-content">
      <div class="section-heading">
        <div>
          <h2>清洗后数据质量快照</h2>
          <p>指标由正式 Parquet 离线生成；页面加载不会扫描 209 万行数据。</p>
        </div>
        <span v-if="state.summary.generated_at">生成时间 {{ state.summary.generated_at }}</span>
      </div>

      <div v-if="state.error" class="overview-error" role="alert">
        数据质量快照加载失败：{{ state.error }}
      </div>
      <div v-if="state.loading" class="quality-loading"><i class="spinner" />正在加载质量快照…</div>

      <template v-else-if="!state.error">
        <section class="metric-grid quality-metrics">
          <MetricCard label="总体质量评分" :value="`${formatDecimal(overallScore)}%`" hint="三项质量维度均值" />
          <MetricCard label="完整性" :value="`${formatDecimal(state.summary.completeness_score)}%`" hint="非空单元格占比" />
          <MetricCard label="有效性" :value="`${formatDecimal(state.summary.validity_score)}%`" hint="六类规则校验" />
          <MetricCard label="一致性" :value="`${formatDecimal(state.summary.consistency_score)}%`" hint="年份/住院日/急诊标志" />
        </section>

        <section class="quality-facts">
          <span><b>{{ formatCount(state.summary.total_rows) }}</b> 清洗后记录</span>
          <span><b>{{ formatCount(state.summary.total_columns) }}</b> 个字段</span>
          <span><b>{{ formatCount(state.summary.facility_count) }}</b> 家医疗机构</span>
          <span><b>{{ formatCount(state.summary.duplicate_rows_removed) }}</b> 条重复已删除</span>
        </section>

        <section class="chart-grid">
          <article class="chart-card">
            <div class="chart-header"><h2>关键字段缺失率</h2><p>仅展示业务关键字段，不隐藏零缺失字段</p></div>
            <EChart :option="missingOption" />
          </article>
          <article class="chart-card">
            <div class="chart-header"><h2>清洗后异常统计</h2><p>负值、住院日、出生体重、年份和急诊标志</p></div>
            <EChart :option="anomalyOption" />
          </article>
        </section>

        <section class="quality-table-card">
          <div class="chart-header"><h2>关键字段明细</h2><p>缺失数与全量记录占比</p></div>
          <div class="quality-table-wrap">
            <table>
              <thead><tr><th>字段</th><th>内部字段名</th><th>缺失数</th><th>缺失率</th></tr></thead>
              <tbody>
                <tr v-for="field in state.fields" :key="field.field">
                  <td>{{ fieldLabels[field.field] || field.field }}</td>
                  <td><code>{{ field.field }}</code></td>
                  <td>{{ formatCount(field.missing_count) }}</td>
                  <td>{{ field.missing_rate.toFixed(4) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </section>
  </main>
</template>
