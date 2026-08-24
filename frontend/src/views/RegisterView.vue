<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authRegister } from '../api/client'

const router = useRouter()
const form = reactive({ username: '', display_name: '', email: '', role: 'patient', password: '', password_confirm: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  if (loading.value) return
  if (form.password !== form.password_confirm) { error.value = '两次输入的密码不一致'; return }
  loading.value = true; error.value = ''
  try {
    await authRegister(form)
    await router.replace({ path: '/login', query: { registered: '1', username: form.username } })
  } catch (exc) { error.value = exc.message || '注册失败' } finally { loading.value = false }
}
</script>

<template>
  <main class="register-page"><section class="card"><button class="back" type="button" @click="router.push('/login')">← 返回登录</button><header><p>SMART HEALTHCARE PLATFORM</p><h1>创建平台账户</h1><span>患者和医生用户可在此完成注册</span></header><form @submit.prevent="submit"><div class="two"><label>用户名<input v-model.trim="form.username" required minlength="3" maxlength="50" autocomplete="username" placeholder="3-50个字符"></label><label>显示名称<input v-model.trim="form.display_name" required maxlength="100" placeholder="请输入姓名或称呼"></label></div><label>邮箱（可选）<input v-model.trim="form.email" type="email" maxlength="200" autocomplete="email" placeholder="用于账号联系"></label><label>账户类型<select v-model="form.role"><option value="patient">患者用户</option><option value="doctor">医生用户</option></select><small>{{ form.role === 'patient' ? '可使用公开总览、患者版 AI 和公开报告' : '可使用数据资产、患者画像、深度分析和报告功能' }}</small></label><div class="two"><label>密码<input v-model="form.password" required type="password" minlength="10" autocomplete="new-password" placeholder="至少10位，包含字母和数字"></label><label>确认密码<input v-model="form.password_confirm" required type="password" minlength="10" autocomplete="new-password" placeholder="再次输入密码"></label></div><p v-if="error" class="error">{{error}}</p><button class="submit" :disabled="loading">{{loading?'正在注册…':'完成注册'}}</button></form><footer>已有账户？<router-link to="/login">返回登录</router-link></footer></section></main>
</template>

<style scoped>*{box-sizing:border-box}.register-page{min-height:100vh;display:grid;place-items:center;padding:28px;background:linear-gradient(145deg,#edf5f3,#f7f9f9);font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;color:#2b3d3c}.card{width:min(680px,100%);padding:34px 42px;background:#fff;border:1px solid #dce6e4;border-radius:18px;box-shadow:0 18px 60px rgba(26,74,69,.09)}.back{padding:0;border:0;background:transparent;color:#278179;font-size:11px;cursor:pointer}header{margin:24px 0 26px}header p{color:#31877f;font-size:9px;letter-spacing:.18em}h1{margin:8px 0 5px;font-size:27px}header span{color:#899491;font-size:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:13px}label{display:block;margin:14px 0;color:#52615f;font-size:11px;font-weight:600}input,select{width:100%;height:42px;margin-top:7px;padding:0 11px;border:1px solid #d8e2e0;border-radius:8px;background:#fff;outline:none;font-size:12px}input:focus,select:focus{border-color:#4ca69c;box-shadow:0 0 0 3px rgba(76,166,156,.11)}label small{display:block;margin-top:6px;color:#8c9794;font-size:9px;font-weight:400}.error{margin-top:12px;padding:9px;color:#a45249;background:#fff0ee;border-radius:7px;font-size:11px}.submit{width:100%;height:44px;margin-top:19px;border:0;border-radius:8px;color:#fff;background:#176f6a;font-weight:600;cursor:pointer}.submit:disabled{opacity:.55}footer{margin-top:20px;text-align:center;color:#929c99;font-size:11px}footer a{color:#238078;text-decoration:none;font-weight:600}@media(max-width:640px){.card{padding:27px 22px}.two{grid-template-columns:1fr}.register-page{padding:14px}}</style>
