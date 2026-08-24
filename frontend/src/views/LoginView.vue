<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../auth'

const route = useRoute()
const router = useRouter()
const username = ref(String(route.query.username || ''))
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!username.value.trim() || !password.value || loading.value) return
  loading.value = true; error.value = ''
  try {
    const user = await login(username.value, password.value)
    await router.replace(user.must_change_password ? '/change-password' : String(route.query.redirect || '/overview'))
  } catch (exc) { error.value = exc.message || '登录失败' } finally { loading.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-brand"><div class="logo"><i></i><i></i></div><p>SMART HEALTHCARE PLATFORM</p><h1>让医疗数据<br><span>成为可靠洞察</span></h1><small>智慧医疗大数据与 AI 分析平台</small></section>
    <section class="login-panel"><form @submit.prevent="submit"><header><h2>欢迎登录</h2><p>使用平台账号进入智医数析</p></header><label>用户名<input v-model.trim="username" autocomplete="username" maxlength="50" autofocus placeholder="请输入用户名"></label><label>密码<div class="password"><input v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" @keyup.enter="submit"><button type="button" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></div></label><p v-if="error" class="error">{{ error }}</p><button class="submit" :disabled="loading || !username || !password">{{ loading ? '正在验证…' : '登 录' }}</button><footer><p>没有账户？<router-link to="/register">去注册</router-link></p><p>忘记密码？请联系管理员</p></footer></form></section>
  </main>
</template>

<style scoped>
*{box-sizing:border-box}.login-page{min-height:100vh;display:grid;grid-template-columns:minmax(360px,1fr) minmax(480px,1fr);font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;background:#f4f7f7}.login-brand{display:flex;flex-direction:column;justify-content:center;padding:10vw;color:#fff;background:linear-gradient(145deg,#123b39,#176f6a 65%,#2e948a);position:relative;overflow:hidden}.login-brand:after{content:"";position:absolute;width:520px;height:520px;border:1px solid rgba(255,255,255,.1);border-radius:50%;right:-240px;bottom:-230px}.logo{position:relative;width:48px;height:48px;background:white;border-radius:14px;margin-bottom:28px}.logo i{position:absolute;left:12px;top:21px;width:24px;height:6px;background:#1a7b74;border-radius:5px}.logo i:last-child{transform:rotate(90deg)}.login-brand p{font-size:11px;letter-spacing:.23em;color:#a8d2ce}.login-brand h1{margin:18px 0;font-size:42px;line-height:1.25}.login-brand h1 span{color:#8ee0d6}.login-brand small{color:#b2cfcc}.login-panel{display:grid;place-items:center;padding:30px}.login-panel form{width:min(390px,100%);padding:38px;background:#fff;border:1px solid #e1e8e8;border-radius:18px;box-shadow:0 18px 55px rgba(30,60,60,.08)}header{margin-bottom:30px}h2{font-size:25px;color:#263a3a}header p{margin-top:8px;color:#879494;font-size:13px}label{display:block;margin-top:19px;color:#4f6060;font-size:12px;font-weight:600}input{width:100%;height:45px;margin-top:8px;padding:0 13px;border:1px solid #dbe3e3;border-radius:9px;outline:none;font-size:13px}input:focus{border-color:#4ba59c;box-shadow:0 0 0 3px rgba(75,165,156,.12)}.password{position:relative}.password input{padding-right:58px}.password button{position:absolute;right:9px;top:19px;border:0;background:transparent;color:#32837c;font-size:11px;cursor:pointer}.error{margin-top:14px;padding:9px 11px;color:#a75249;background:#fff0ee;border-radius:7px;font-size:11px}.submit{width:100%;height:46px;margin-top:24px;border:0;border-radius:9px;background:#176f6a;color:white;font-weight:600;cursor:pointer}.submit:disabled{opacity:.55;cursor:not-allowed}footer{display:grid;gap:7px;margin-top:24px;text-align:center;color:#9aa5a5;font-size:11px}footer a{color:#238078;text-decoration:none;font-weight:600}footer a:hover{text-decoration:underline}@media(max-width:760px){.login-page{grid-template-columns:1fr}.login-brand{display:none}.login-panel{padding:18px}.login-panel form{padding:28px}}
</style>
