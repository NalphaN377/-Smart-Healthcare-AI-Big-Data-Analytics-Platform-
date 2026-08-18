<script setup>
import { onMounted, ref } from 'vue'

import { aiApi } from '../api/ai.js'
import AIChart from '../components/AIChart.vue'

const examples = [
  '住院人数最多的五种疾病是什么？',
  '哪些疾病的平均住院费用最高？',
  '不同年龄组的平均费用有什么差异？',
  '哪些医院的住院病例最多？',
  '不同支付方式占比是多少？',
  '不同病情严重程度的平均住院时间是多少？',
]

const input = ref('')
const loading = ref(false)
const providerConfigured = ref(null)
const providerLabel = ref('')
const statusError = ref('')
const sessionId = ref(null)
const messages = ref([])

onMounted(async () => {
  try {
    const payload = await aiApi.status()
    providerConfigured.value = payload.data.configured
    providerLabel.value = payload.data.configured
      ? `${payload.data.provider.name} / ${payload.data.provider.model}`
      : 'AI provider not configured'
  } catch (error) {
    providerConfigured.value = false
    statusError.value = error.message
  }
})

async function ask(question = input.value) {
  const query = question.trim()
  if (!query || loading.value) return
  messages.value.push({ role: 'user', text: query })
  input.value = ''
  loading.value = true
  try {
    const payload = await aiApi.query(query, sessionId.value)
    sessionId.value = payload.data.session_id
    messages.value.push({
      role: 'assistant',
      text: payload.data.answer,
      result: payload.data,
      meta: payload.meta,
    })
  } catch (error) {
    messages.value.push({
      role: 'error',
      text:
        error.status === 503
          ? 'AI provider not configured。统计驾驶舱与其他分析 API 不受影响。'
          : error.status === 504
            ? '大模型响应超时，请稍后重试。'
            : error.status === 422
              ? '当前问题不在已注册的医疗统计分析能力范围内。'
              : error.message,
    })
  } finally {
    loading.value = false
  }
}

function newConversation() {
  messages.value = []
  sessionId.value = null
  input.value = ''
}

function toolLabel(tool) {
  return {
    get_overview: '总体住院情况',
    get_top_diseases: '疾病病例排名',
    get_disease_cost_analysis: '疾病费用分析',
    get_hospital_analysis: '医院分析',
    get_age_analysis: '年龄组分析',
    get_payment_distribution: '支付方式分析',
    get_severity_analysis: '病情严重程度分析',
    get_year_trend: '年度趋势',
  }[tool] || tool
}
</script>

<template>
  <main class="page-shell ai-page">
    <header class="app-header">
      <div class="brand-mark" aria-hidden="true">医</div>
      <div class="app-title">
        <p>GROUNDED MEDICAL ANALYTICS</p>
        <h1>AI 智能分析助手</h1>
      </div>
      <nav class="header-actions" aria-label="主要导航">
        <RouterLink class="header-link" to="/">数据驾驶舱</RouterLink>
        <span class="service-status" :class="providerConfigured ? 'status-online' : 'status-offline'"><i />{{ providerLabel || '检查 AI 服务中' }}</span>
      </nav>
    </header>

    <section class="ai-layout">
      <aside class="ai-sidebar">
        <button class="new-chat-button" type="button" @click="newConversation">新建对话</button>
        <h2>示例问题</h2>
        <button v-for="example in examples" :key="example" type="button" class="example-button" :disabled="loading || providerConfigured === false" @click="ask(example)">
          {{ example }}
        </button>
        <p class="safety-note">本系统用于数据分析与教学演示，不提供医疗诊断或个体治疗建议。</p>
      </aside>

      <section class="chat-workspace">
        <div v-if="providerConfigured === false" class="provider-banner" role="status">
          <strong>AI provider not configured</strong>
          <span>{{ statusError || '请在本地环境变量中配置兼容 Provider。MySQL、HDFS、Hive、Dashboard 和分析 API 仍可独立运行。' }}</span>
        </div>

        <div class="chat-scroll" aria-live="polite">
          <div v-if="messages.length === 0" class="chat-empty">
            <span>AI</span>
            <h2>基于真实住院统计数据提问</h2>
            <p>Agent 只能调用已注册的分析工具，不会生成 SQL，也不会访问患者身份信息。</p>
          </div>
          <article v-for="(message, index) in messages" :key="index" class="chat-message" :class="`message-${message.role}`">
            <div class="message-role">{{ message.role === 'user' ? '你' : message.role === 'assistant' ? 'AI 分析' : '提示' }}</div>
            <div class="message-body">
              <p>{{ message.text }}</p>
              <template v-if="message.result">
                <AIChart :spec="message.result.chart" />
                <div class="result-provenance">
                  <span><b>数据来源</b>{{ message.result.sources[0]?.name }}</span>
                  <span><b>分析范围</b>{{ message.result.sources[0]?.record_count?.toLocaleString('zh-CN') }} cleaned records</span>
                  <span><b>调用分析</b>{{ toolLabel(message.result.tool_calls[0]?.tool) }}</span>
                  <span><b>工具耗时</b>{{ message.result.tool_calls[0]?.elapsed_ms }} ms</span>
                </div>
              </template>
            </div>
          </article>
          <div v-if="loading" class="chat-loading"><i />正在调用受控分析工具并生成 grounded 中文解读…</div>
        </div>

        <form class="chat-input" @submit.prevent="ask()">
          <textarea v-model="input" rows="2" maxlength="1000" :disabled="loading || providerConfigured === false" placeholder="请输入医疗统计分析问题…" @keydown.enter.exact.prevent="ask()" />
          <button type="submit" :disabled="loading || !input.trim() || providerConfigured === false">{{ loading ? '分析中' : '发送' }}</button>
        </form>
      </section>
    </section>
  </main>
</template>

