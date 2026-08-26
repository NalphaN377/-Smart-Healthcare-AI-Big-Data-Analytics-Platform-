<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import DashboardChart from './DashboardChart.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  suggestions: { type: Array, default: () => [] },
})

const emit = defineEmits(['send'])
const input = ref('')
const scrollBox = ref(null)
const suggestionPage = ref(0)
const suggestionsPerPage = 4
const suggestionPages = computed(() => Math.max(1, Math.ceil(props.suggestions.length / suggestionsPerPage)))
const visibleSuggestions = computed(() => {
  const start = suggestionPage.value * suggestionsPerPage
  return props.suggestions.slice(start, start + suggestionsPerPage)
})
let suggestionTimer = null

function pauseSuggestions() {
  if (suggestionTimer) window.clearInterval(suggestionTimer)
  suggestionTimer = null
}

function resumeSuggestions() {
  pauseSuggestions()
  if (suggestionPages.value <= 1 || props.loading || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  suggestionTimer = window.setInterval(() => {
    suggestionPage.value = (suggestionPage.value + 1) % suggestionPages.value
  }, 5000)
}

function changeSuggestionPage(offset) {
  suggestionPage.value = (suggestionPage.value + offset + suggestionPages.value) % suggestionPages.value
  resumeSuggestions()
}

function submit() {
  const q = input.value.trim()
  if (!q) return
  emit('send', q)
  input.value = ''
}

function useSuggestion(text) {
  input.value = text
  submit()
}

watch(
  () => {
    const latest = props.messages.at(-1)
    return [props.messages.length, props.loading, latest?.content?.length || 0, Boolean(latest?.chart)]
  },
  async () => {
    await nextTick()
    if (scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight
  },
)

watch(() => props.suggestions, () => {
  suggestionPage.value = 0
  resumeSuggestions()
})
watch(() => props.loading, (loading) => loading ? pauseSuggestions() : resumeSuggestions())
onMounted(resumeSuggestions)
onBeforeUnmount(pauseSuggestions)
</script>

<template>
  <div class="chat-panel">
    <div class="messages" ref="scrollBox">
      <div v-if="messages.length === 0" class="empty">
        <div class="ai-orb"><AppIcon name="sparkle" :size="22" /></div>
        <strong>你好，我是医疗数据分析助手</strong>
        <span>可以用自然语言查询住院量、费用、疾病趋势与资源利用情况。</span>
      </div>
      <div
        v-for="(m, i) in messages"
        :key="i"
        class="message"
        :class="[m.role, { 'has-chart': Boolean(m.chart) }]"
      >
        <div v-if="m.role === 'assistant'" class="message-avatar"><AppIcon name="sparkle" :size="15" /></div>
        <div class="bubble">
          <div class="message-text">{{ m.content }}</div>
          <div v-if="m.role === 'assistant' && m.chart" class="inline-chart">
            <div class="inline-chart-head"><span><AppIcon name="chart" :size="13" /> 可视化结果</span><small>基于本次聚合数据</small></div>
            <DashboardChart :option="m.chart" height="330px" />
            <p>住院记录级聚合 · 金额为名义美元</p>
          </div>
        </div>
      </div>
      <div v-if="loading" class="message assistant">
        <div class="message-avatar"><AppIcon name="sparkle" :size="15" /></div>
        <div class="bubble thinking"><i></i><i></i><i></i></div>
      </div>
    </div>

    <div
      v-if="suggestions.length"
      class="suggestion-carousel"
      @focusin="pauseSuggestions"
      @focusout="resumeSuggestions"
    >
      <Transition name="suggestion-page" mode="out-in">
        <div :key="suggestionPage" class="suggestions">
          <button v-for="item in visibleSuggestions" :key="item" @click="useSuggestion(item)">{{ item }}</button>
        </div>
      </Transition>
      <div v-if="suggestionPages > 1" class="suggestion-controls">
        <button type="button" aria-label="上一组建议问题" @click="changeSuggestionPage(-1)">‹</button>
        <span>{{ suggestionPage + 1 }} / {{ suggestionPages }}</span>
        <button type="button" aria-label="下一组建议问题" @click="changeSuggestionPage(1)">›</button>
      </div>
    </div>

    <div class="input-bar">
      <textarea
        v-model="input"
        rows="1"
        placeholder="输入你的分析问题，例如：不同年龄段住院时长对比"
        @keydown.enter.prevent="submit"
      ></textarea>
      <button :disabled="loading || !input.trim()" aria-label="发送" @click="submit"><AppIcon name="send" :size="18" /></button>
    </div>
    <p class="disclaimer">AI 生成内容仅用于数据分析参考，不构成医疗诊断建议</p>
  </div>
</template>

<style scoped>
.chat-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--surface, #fff);
  border: 1px solid var(--line, #e5e9ef);
  border-radius: 18px;
  overflow: hidden;
  min-width: 0;
}
.messages { flex: 1; overflow-y: auto; padding: 24px; min-height: 260px; }
.empty { min-height: 230px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #7b8794; font-size: 13px; line-height: 1.7; text-align: center; }
.empty strong { color: #253442; font-size: 16px; margin: 13px 0 5px; }
.empty span { max-width: 300px; }
.ai-orb { width: 46px; height: 46px; display: grid; place-items: center; color: #fff; border-radius: 15px; background: #087f72; box-shadow: 0 8px 22px rgba(8, 127, 114, .18); }
.message { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 16px; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.message-avatar { width: 28px; height: 28px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 9px; background: #e8f6f3; color: #14776f; }
.bubble {
  max-width: 84%;
  padding: 11px 14px;
  border-radius: 5px 14px 14px 14px;
  font-size: 13px;
  line-height: 1.72;
  white-space: pre-wrap;
}
.user .bubble { background: #176b68; color: #fff; border-radius: 14px 5px 14px 14px; }
.assistant .bubble { background: #f1f4f6; color: #35424e; }
.assistant.has-chart .bubble { width: min(920px, calc(100% - 36px)); max-width: 96%; }
.message-text { white-space: pre-wrap; }
.inline-chart { margin-top: 13px; padding: 13px 14px 8px; overflow: hidden; background: #fff; border: 1px solid #dfe7e8; border-radius: 12px; box-shadow: 0 6px 18px rgba(27, 58, 61, .05); }
.inline-chart-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 3px; }
.inline-chart-head span { display: inline-flex; align-items: center; gap: 5px; color: #237c75; font-size: 10px; font-weight: 700; }
.inline-chart-head small,.inline-chart>p { color: #929da2; font-size: 9px; }
.inline-chart>p { padding: 7px 2px 2px; border-top: 1px solid #edf1f2; }
.suggestion-carousel { min-height: 48px; display: flex; align-items: flex-start; gap: 10px; padding: 0 14px 12px 18px; overflow: hidden; }
.suggestions { min-width: 0; display: flex; flex: 1; gap: 7px; overflow-x: auto; }
.suggestions button { min-height: 36px; white-space: nowrap; border: 1px solid #dce5e7; background: #f8fbfb; color: #53646b; padding: 7px 12px; border-radius: 20px; font-size: 12px; cursor: pointer; transition: color 180ms ease, background-color 180ms ease, border-color 180ms ease, transform 180ms ease; }
.suggestions button:hover { border-color: #77b7b0; color: #176b68; background: #f0f9f7; }
.suggestion-controls { height: 36px; display: flex; align-items: center; gap: 5px; flex: 0 0 auto; color: #82908f; font-size: 10px; }
.suggestion-controls button { width: 28px; height: 28px; display: grid; place-items: center; padding: 0; color: #506864; background: #fff; border: 1px solid #dce5e3; border-radius: 50%; font-size: 18px; line-height: 1; cursor: pointer; }
.suggestion-controls button:hover { color: #087f72; background: #f0f8f6; border-color: #9bcac3; }
.suggestion-page-enter-active,.suggestion-page-leave-active { transition: opacity 220ms ease, transform 220ms ease; }
.suggestion-page-enter-from { opacity: 0; transform: translateX(14px); }
.suggestion-page-leave-to { opacity: 0; transform: translateX(-14px); }
.input-bar { display: flex; align-items: center; gap: 9px; margin: 0 16px; padding: 8px 8px 8px 13px; border: 1px solid #dce2e6; border-radius: 13px; background: #fff; }
.input-bar textarea {
  flex: 1; resize: none; padding: 5px 0; border: none; font-family: inherit;
  font-size: 13px; line-height: 1.5; outline: none;
}
.input-bar button {
  width: 36px; height: 36px; display: grid; place-items: center; border: none; border-radius: 10px;
  background: #087f72; color: #fff; cursor: pointer; transition: background-color 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}
.input-bar button:hover { background: #076b61; box-shadow: 0 6px 14px rgba(8, 127, 114, .16); transform: translateY(-1px); }
.input-bar button:disabled { background: #c9d6d5; cursor: not-allowed; transform: none; }
.disclaimer { text-align: center; font-size: 10px; color: #a0a8af; padding: 8px 12px 12px; }
.thinking { display: flex; align-items: center; gap: 4px; height: 39px; }
.thinking i { width: 5px; height: 5px; border-radius: 50%; background: #78908e; animation: bounce 1s infinite ease-in-out; }
.thinking i:nth-child(2) { animation-delay: .15s; }.thinking i:nth-child(3) { animation-delay: .3s; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .4; } 30% { transform: translateY(-4px); opacity: 1; } }
@media(max-width:700px){.messages{padding:16px 12px}.bubble{max-width:92%}.assistant.has-chart .bubble{width:calc(100% - 36px);max-width:calc(100% - 36px);padding:9px}.inline-chart{padding:9px 8px 6px}.inline-chart-head small{display:none}.suggestion-carousel{padding-inline:12px 9px}.suggestion-controls span{display:none}}
</style>
