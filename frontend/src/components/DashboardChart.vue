<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, DataZoomComponent, DatasetComponent, GraphicComponent, GridComponent, LegendComponent, MarkLineComponent, ToolboxComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

echarts.use([BarChart, HeatmapChart, LineChart, PieChart, ScatterChart, AriaComponent, DataZoomComponent, DatasetComponent, GraphicComponent, GridComponent, LegendComponent, MarkLineComponent, ToolboxComponent, TooltipComponent, VisualMapComponent, SVGRenderer])

const emit = defineEmits(['select'])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [String, Number], default: '280px' },
})

const chartRef = ref(null)
let chart
let observer

function render() {
  if (!chart || !props.option) return
  const isAiCartesianChart = Boolean(
    props.option.toolbox && (props.option.xAxis || props.option.yAxis),
  )
  const safeAiGrid = (grid = {}) => ({
    ...grid,
    left: typeof grid.left === 'number' ? Math.max(grid.left, 88) : (grid.left || 88),
    containLabel: false,
  })
  const option = isAiCartesianChart
    ? {
        ...props.option,
        grid: Array.isArray(props.option.grid)
          ? props.option.grid.map((grid) => safeAiGrid(grid))
          : safeAiGrid(props.option.grid),
      }
    : props.option
  chart.setOption(option, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(chartRef.value, null, { renderer: 'svg' })
  chart.on('click', (params) => emit('select', {
    name: params.name, value: params.value, seriesName: params.seriesName, dataIndex: params.dataIndex,
  }))
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
