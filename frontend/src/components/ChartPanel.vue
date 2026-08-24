<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, default: null },
  summary: { type: String, default: '' },
})

const chartRef = ref(null)
let chart = null

function resize() {
  if (chart) chart.resize()
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  if (props.option) chart.setOption(props.option)
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  if (chart) chart.dispose()
})

watch(
  () => props.option,
  (opt) => {
    if (opt && chart) chart.setOption(opt, true)
  },
  { deep: true },
)
</script>

<template>
  <div class="chart-panel">
    <div v-if="summary" class="summary">{{ summary }}</div>
    <div v-if="option" ref="chartRef" class="chart"></div>
    <div v-else class="placeholder">分析结果图表将在这里展示</div>
  </div>
</template>

<style scoped>
.chart-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 320px;
}
.summary {
  background: #fff; border-radius: 8px; padding: 14px 16px;
  font-size: 14px; line-height: 1.7; color: #2c3e50;
  border-left: 4px solid #2f7fd6;
}
.chart { flex: 1; background: #fff; border-radius: 8px; min-height: 320px; }
.placeholder {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: #95a5a6; font-size: 14px; background: #fff; border-radius: 8px;
  min-height: 320px;
}
</style>
