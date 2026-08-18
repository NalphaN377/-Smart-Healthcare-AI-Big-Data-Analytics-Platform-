<script setup>
import { computed, onMounted, reactive } from 'vue'

import { mlApi } from '../api/ml.js'
import { formatCurrency, formatCount, formatDecimal } from '../utils/format.js'

const state = reactive({ loading: true, submitting: false, error: '', status: {}, result: null })
const form = reactive({
  age_group: '',
  gender: '',
  admission_type: '',
  diagnosis_code: '',
  severity: '',
  mortality_risk: '',
  medical_surgical_description: '',
  emergency_indicator: false,
  payment_type_1: '',
})

const labels = {
  age_group: '年龄组',
  gender: '性别',
  admission_type: '入院类型',
  diagnosis_code: 'CCSR 诊断代码',
  severity: '病情严重程度',
  mortality_risk: '死亡风险等级',
  medical_surgical_description: '医疗/外科分类',
  payment_type_1: '第一支付方式',
}
const selectFields = computed(() =>
  (state.status.features || [])
    .filter((name) => name !== 'emergency_indicator')
    .map((name) => ({ name, label: labels[name] || name, options: state.status.feature_options?.[name] || [] })),
)

function populateDefaults() {
  for (const field of selectFields.value) {
    if (!form[field.name] && field.options.length) form[field.name] = field.options[0]
  }
}

async function loadStatus() {
  state.loading = true
  state.error = ''
  try {
    const payload = await mlApi.status()
    state.status = payload.data || {}
    populateDefaults()
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function predict() {
  state.submitting = true
  state.error = ''
  state.result = null
  try {
    const payload = await mlApi.predict({ ...form })
    state.result = payload.data
  } catch (error) {
    state.error = error.message
  } finally {
    state.submitting = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <main class="page-shell">
    <header class="app-header">
      <div class="brand-mark" aria-hidden="true">估</div>
      <div class="app-title"><p>INPATIENT COST ESTIMATION</p><h1>住院费用估计</h1></div>
      <nav class="header-actions" aria-label="主要导航">
        <RouterLink class="header-link" to="/">数据驾驶舱</RouterLink>
        <RouterLink class="header-link" to="/data-quality">数据质量</RouterLink>
        <RouterLink class="header-link" to="/ai">AI 智能分析</RouterLink>
      </nav>
    </header>

    <section class="content prediction-content">
      <div class="section-heading">
        <div><h2>基于行政住院数据的费用估计</h2><p>模型不使用 Total Costs、Total Charges 或住院天数，结果为教学用统计估计。</p></div>
        <span v-if="state.status.model_version">{{ state.status.model_version }}</span>
      </div>
      <div v-if="state.loading" class="quality-loading"><i class="spinner" />正在读取模型状态…</div>
      <div v-else-if="state.error" class="overview-error" role="alert">{{ state.error }}</div>
      <div v-else-if="!state.status.available" class="overview-error" role="status">
        费用预测模型尚未训练。其他数据分析功能不受影响。
      </div>

      <template v-else>
        <section class="prediction-layout">
          <form class="prediction-form" @submit.prevent="predict">
            <div class="chart-header"><h2>输入住院记录特征</h2><p>选项来自已训练模型的真实数据元数据</p></div>
            <div class="prediction-field-grid">
              <label v-for="field in selectFields" :key="field.name">
                <span>{{ field.label }}</span>
                <select v-model="form[field.name]" required>
                  <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
                </select>
              </label>
              <label>
                <span>急诊科标志</span>
                <select v-model="form.emergency_indicator" required>
                  <option :value="false">否</option>
                  <option :value="true">是</option>
                </select>
              </label>
            </div>
            <button class="prediction-submit" type="submit" :disabled="state.submitting">
              {{ state.submitting ? '估计中…' : '估计 Total Costs' }}
            </button>
          </form>

          <aside class="prediction-result">
            <div class="chart-header"><h2>估计结果</h2><p>模型输出为单点估计，不代表报价或置信区间</p></div>
            <div v-if="state.result" class="prediction-value">
              <span>预计总成本</span><strong>{{ formatCurrency(state.result.predicted_cost) }}</strong>
              <p>{{ state.result.disclaimer }}</p>
            </div>
            <div v-else class="prediction-empty">完成左侧表单后查看模型估计。</div>
            <dl class="model-facts">
              <div><dt>训练样本</dt><dd>{{ formatCount(state.status.sample_size) }}</dd></div>
              <div><dt>测试集 MAE</dt><dd>{{ formatCurrency(state.status.metrics?.mae) }}</dd></div>
              <div><dt>基线 MAE</dt><dd>{{ formatCurrency(state.status.metrics?.baseline_mae) }}</dd></div>
              <div><dt>测试集 R²</dt><dd>{{ formatDecimal(state.status.metrics?.r2, 4) }}</dd></div>
            </dl>
          </aside>
        </section>
        <p class="prediction-disclaimer">仅用于数据分析和教学展示，不构成医疗或费用结算依据。</p>
      </template>
    </section>
  </main>
</template>
