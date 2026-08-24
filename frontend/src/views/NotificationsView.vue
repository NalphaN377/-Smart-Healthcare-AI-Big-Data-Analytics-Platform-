<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '../api/client'

const router = useRouter()
const notifications = ref([])
const unreadCount = ref(0)
const loading = ref(true)
const error = ref('')
const markingAll = ref(false)
const hasUnread = computed(() => unreadCount.value > 0)
let refreshTimer = null

function formatTime(value) {
  if (!value) return '未知时间'
  return String(value).replace('T', ' ').replace(/\+00:00$/, '')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await listNotifications(100)
    notifications.value = response.data.items || []
    unreadCount.value = Number(response.data.unread_count || 0)
  } catch (err) {
    error.value = err.message || '通知加载失败'
  } finally {
    loading.value = false
  }
}

async function openNotification(item) {
  error.value = ''
  try {
    if (!item.is_read) {
      await markNotificationRead(item.id)
      item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
    await router.push({ name: 'public-reports', query: { report: item.report_id } })
  } catch (err) {
    await load()
    error.value = err.message === '通知不存在' ? '该报告已被管理员撤回。' : (err.message || '无法打开通知')
  }
}

async function markAll() {
  if (!hasUnread.value || markingAll.value) return
  markingAll.value = true
  error.value = ''
  try {
    await markAllNotificationsRead()
    notifications.value.forEach((item) => { item.is_read = true })
    unreadCount.value = 0
  } catch (err) {
    error.value = err.message || '标记已读失败'
  } finally {
    markingAll.value = false
  }
}

onMounted(() => {
  load()
  refreshTimer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => { if (refreshTimer) window.clearInterval(refreshTimer) })
</script>

<template>
  <main class="notification-page">
    <header>
      <div>
        <button class="back" @click="router.push('/overview')">← 返回总览</button>
        <h1>消息通知</h1>
        <p>管理员发布的公开报告会在这里通知你</p>
      </div>
      <button class="mark-all" :disabled="!hasUnread || markingAll" @click="markAll">
        {{ markingAll ? '处理中…' : '全部标为已读' }}
      </button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="loading" class="empty">正在加载通知…</section>
    <section v-else-if="!notifications.length" class="empty">
      <span><AppIcon name="bell" :size="25" /></span>
      <h2>暂无消息</h2>
      <p>新的公开报告发布后会出现在这里。</p>
    </section>
    <section v-else class="notification-list" aria-live="polite">
      <button
        v-for="item in notifications"
        :key="item.id"
        class="notification-item"
        :class="{ unread: !item.is_read }"
        @click="openNotification(item)"
      >
        <span class="notification-icon"><AppIcon name="report" :size="20" /></span>
        <span class="notification-copy">
          <strong>{{ item.title }}</strong>
          <span>{{ item.message }}</span>
          <small>{{ formatTime(item.created_at) }}</small>
        </span>
        <i v-if="!item.is_read" aria-label="未读"></i>
        <AppIcon name="arrow-right" :size="17" />
      </button>
    </section>
  </main>
</template>

<style scoped>
.notification-page{min-height:100vh;padding:34px 7vw 60px;color:#2b3d3c;background:#f3f6f6;font-family:"Segoe UI","Microsoft YaHei",sans-serif}header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}.back{padding:0;color:#34736d;background:transparent;border:0;cursor:pointer}h1{margin:14px 0 5px;font-size:27px}header p{color:#899592;font-size:12px}.mark-all{padding:9px 13px;color:#27776f;background:#fff;border:1px solid #d6e0df;border-radius:8px;cursor:pointer}.mark-all:disabled{cursor:default;opacity:.45}.notification-list{overflow:hidden;background:#fff;border:1px solid #dfe7e6;border-radius:14px;box-shadow:0 8px 25px rgba(39,66,64,.05)}.notification-item{position:relative;width:100%;display:flex;align-items:center;gap:14px;padding:18px 20px;color:#65736f;background:#fff;border:0;border-bottom:1px solid #edf1f0;text-align:left;cursor:pointer;transition:.18s}.notification-item:last-child{border-bottom:0}.notification-item:hover{background:#f7faf9}.notification-item.unread{background:#f0f8f6}.notification-icon{width:42px;height:42px;display:grid;place-items:center;flex:0 0 auto;color:#247d75;background:#e5f3f1;border-radius:11px}.notification-copy{min-width:0;flex:1}.notification-copy strong,.notification-copy span,.notification-copy small{display:block}.notification-copy strong{color:#30443f;font-size:13px}.notification-copy span{margin:6px 0;color:#71807c;font-size:11px;line-height:1.55}.notification-copy small{color:#9aa5a2;font-size:9px}.notification-item>i{width:7px;height:7px;flex:0 0 auto;background:#df6159;border-radius:50%;box-shadow:0 0 0 4px rgba(223,97,89,.1)}.empty{display:grid;justify-items:center;padding:70px 20px;color:#889591;background:#fff;border:1px solid #dfe7e6;border-radius:14px;text-align:center}.empty>span{width:52px;height:52px;display:grid;place-items:center;color:#38847d;background:#e8f5f3;border-radius:14px}.empty h2{margin:14px 0 6px;color:#40534e;font-size:15px}.empty p{font-size:11px}.error{margin-bottom:14px;padding:11px;color:#a45149;background:#fff0ee;border:1px solid #f0d4cf;border-radius:8px}@media(max-width:700px){.notification-page{padding:22px 16px}header{align-items:stretch;flex-direction:column}.mark-all{align-self:flex-start}.notification-item{padding:15px 13px}.notification-icon{width:36px;height:36px}}
</style>
