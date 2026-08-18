<script setup>
import EChart from './EChart.vue'

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  state: { type: Object, required: true },
  option: { type: Object, required: true },
  emptyText: { type: String, default: '暂无可展示数据' },
})
</script>

<template>
  <section class="chart-card">
    <header class="chart-header">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ subtitle }}</p>
      </div>
    </header>
    <div v-if="state.loading" class="state-box" aria-live="polite">
      <span class="spinner" />
      正在读取真实分析数据…
    </div>
    <div v-else-if="state.error" class="state-box state-error" role="alert">
      {{ state.error }}
    </div>
    <div v-else-if="!state.data?.length" class="state-box">
      {{ emptyText }}
    </div>
    <EChart v-else :option="option" />
  </section>
</template>
