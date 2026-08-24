<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { cancelAccount } from '../api/client'
import { authState, clearAuth } from '../auth'

const router = useRouter()
const password = ref('')
const confirmation = ref('')
const loading = ref(false)
const error = ref('')

async function cancel() {
  if (authState.user?.role === 'admin') { error.value = '管理员账号不能自助注销'; return }
  if (confirmation.value !== '注销账号') { error.value = '请输入“注销账号”确认操作'; return }
  if (!window.confirm('账号注销后将无法登录，确定继续吗？')) return
  loading.value = true; error.value = ''
  try {
    await cancelAccount(password.value, confirmation.value)
    clearAuth()
    await router.replace('/login')
  } catch (exc) { error.value = exc.message || '注销失败' } finally { loading.value = false }
}
</script>

<template><main class="page"><section class="card"><button class="back" @click="router.push('/overview')">← 返回工作台</button><header><h1>账户设置</h1><p>{{authState.user?.display_name}} · @{{authState.user?.username}}</p></header><section class="info"><span>账户类型</span><strong>{{authState.user?.role==='doctor'?'医生用户':authState.user?.role==='patient'?'患者用户':'运维员用户'}}</strong><span>邮箱</span><strong>{{authState.user?.email||'未设置'}}</strong></section><section class="danger"><h2>注销账号</h2><p v-if="authState.user?.role!=='admin'">注销后账号会立即失效，历史报告与安全审计记录将被保留。此操作不可自行恢复。</p><p v-else>管理员账号不能自助注销。如需调整管理员账号，请先创建其他管理员并进行交接。</p><form v-if="authState.user?.role!=='admin'" @submit.prevent="cancel"><label>当前密码<input v-model="password" required type="password" autocomplete="current-password" placeholder="请输入当前密码"></label><label>输入“注销账号”确认<input v-model="confirmation" required placeholder="注销账号"></label><div v-if="error" class="error">{{error}}</div><button :disabled="loading">{{loading?'正在注销…':'永久注销我的账号'}}</button></form></section></section></main></template>

<style scoped>*{box-sizing:border-box}.page{min-height:100vh;display:grid;place-items:center;padding:24px;background:#f3f6f6;color:#2c3e3c;font-family:"Segoe UI","Microsoft YaHei",sans-serif}.card{width:min(620px,100%);padding:34px;background:#fff;border:1px solid #dfe7e6;border-radius:16px;box-shadow:0 14px 45px rgba(30,70,66,.07)}.back{padding:0;border:0;background:transparent;color:#258078;cursor:pointer}header{margin:22px 0}h1{font-size:26px}header p{margin-top:6px;color:#899592;font-size:11px}.info{display:grid;grid-template-columns:100px 1fr;gap:11px;padding:18px;background:#f6f9f8;border-radius:9px;font-size:11px}.info span{color:#8b9694}.danger{margin-top:25px;padding-top:23px;border-top:1px solid #edf0ef}.danger h2{color:#923f39;font-size:16px}.danger>p{margin:8px 0 18px;color:#7f8b89;font-size:11px;line-height:1.7}label{display:block;margin:13px 0;color:#566461;font-size:11px;font-weight:600}input{width:100%;height:42px;margin-top:7px;padding:0 11px;border:1px solid #d9e1df;border-radius:8px;outline:none}input:focus{border-color:#c27a73;box-shadow:0 0 0 3px rgba(194,122,115,.1)}form button{width:100%;height:43px;margin-top:13px;border:1px solid #b8564e;border-radius:8px;color:#fff;background:#a94d46;cursor:pointer}form button:disabled{opacity:.55}.error{padding:9px;color:#a34e47;background:#fff0ee;border-radius:7px;font-size:11px}</style>
