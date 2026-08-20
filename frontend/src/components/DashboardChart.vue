<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { DatasetComponent, GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

echarts.use([BarChart, LineChart, PieChart, DatasetComponent, GraphicComponent, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [String, Number], default: '280px' },
})

const chartRef = ref(null)
let chart
let observer

function render() {
  if (!chart || !props.option) return
  chart.setOption(props.option, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(chartRef.value, null, { renderer: 'svg' })
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartRef.value)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="chartRef" class="dashboard-chart" :style="{ height: typeof height === 'number' ? `${height}px` : height }"></div>
</template>

<style scoped>
.dashboard-chart { width: 100%; min-width: 0; }
</style>
