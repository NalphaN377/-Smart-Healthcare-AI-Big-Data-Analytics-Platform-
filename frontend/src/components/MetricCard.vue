<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  hint: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})
</script>

<template>
  <article class="metric-card" :aria-busy="loading">
    <span class="metric-label">{{ label }}</span>
    <span v-if="loading" class="metric-skeleton" />
    <strong v-else class="metric-value">{{ value }}</strong>
    <span class="metric-hint">{{ hint }}</span>
  </article>
</template>
