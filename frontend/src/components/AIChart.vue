<script setup>
import { computed } from 'vue'

import EChart from './EChart.vue'

const props = defineProps({
  spec: { type: Object, required: true },
})

const palette = ['#246b8e', '#2f8f83', '#d18a32']
const axisLabel = { color: '#667085', fontSize: 11 }
const grid = { left: 34, right: 20, top: 24, bottom: 50, containLabel: true }

const tableFields = computed(() => {
  const fields = [props.spec.x_field, ...(props.spec.series || []).map((item) => item.field)].filter(Boolean)
  return [...new Set(fields.length ? fields : Object.keys(props.spec.data?.[0] || {}))]
})

const option = computed(() => {
  const spec = props.spec
  const rows = spec.data || []
  const categoryField = spec.x_field
  const series = spec.series || []
  if (spec.type === 'pie') {
    const valueField = series[0]?.field
    return {
      color: palette,
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll', textStyle: axisLabel },
      series: [
        {
          type: 'pie',
          radius: ['40%', '68%'],
          data: rows.map((row) => ({ name: row[categoryField], value: row[valueField] })),
        },
      ],
    }
  }
  const horizontal = spec.type === 'horizontal_bar'
  const categories = rows.map((row) => row[categoryField])
  const chartSeries = series.map((item) => ({
    name: item.name,
    type: spec.type === 'line' ? 'line' : 'bar',
    data: rows.map((row) => row[item.field]),
    barMaxWidth: 28,
    smooth: spec.type === 'line',
  }))
  return {
    color: palette,
    grid,
    tooltip: { trigger: 'axis', axisPointer: { type: spec.type === 'line' ? 'line' : 'shadow' } },
    legend: { bottom: 0, textStyle: axisLabel },
    xAxis: horizontal
      ? { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } }
      : { type: 'category', data: categories, axisLabel: { ...axisLabel, rotate: categories.length > 6 ? 20 : 0 } },
    yAxis: horizontal
      ? { type: 'category', inverse: true, data: categories, axisLabel: { ...axisLabel, width: 180, overflow: 'truncate' } }
      : { type: 'value', axisLabel, splitLine: { lineStyle: { color: '#eef1f4' } } },
    series: chartSeries,
  }
})

function displayValue(value) {
  if (typeof value === 'number') return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
  return value ?? '—'
}
</script>

<template>
  <section class="ai-chart-panel">
    <h4>{{ spec.title }}</h4>
    <div v-if="spec.status === 'unavailable'" class="ai-chart-unavailable">{{ spec.message }}</div>
    <div v-else-if="spec.type === 'table'" class="ai-table-wrap">
      <table>
        <thead><tr><th v-for="field in tableFields" :key="field">{{ field }}</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in spec.data" :key="index">
            <td v-for="field in tableFields" :key="field">{{ displayValue(row[field]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <EChart v-else :option="option" />
  </section>
</template>

