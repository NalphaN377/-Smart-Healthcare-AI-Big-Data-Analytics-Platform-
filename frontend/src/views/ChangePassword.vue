<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { changePassword } from '../api/client'
import { refreshAuth } from '../auth'

const router = useRouter(); const current = ref(''); const next = ref(''); const confirm = ref(''); const error = ref(''); const loading = ref(false)
async function submit(){if(next.value!==confirm.value){error.value='两次输入的新密码不一致';return}loading.value=true;error.value='';try{await changePassword(current.value,next.value);await refreshAuth();await router.replace('/overview')}catch(exc){error.value=exc.message}finally{loading.value=false}}
</script>
<template><main class="page"><form @submit.prevent="submit"><h1>修改初始密码</h1><p>为了账号安全，继续使用平台前请设置新密码。</p><label>当前密码<input v-model="current" type="password" autocomplete="current-password"></label><label>新密码<input v-model="next" type="password" autocomplete="new-password" placeholder="至少10位，包含字母和数字"></label><label>确认新密码<input v-model="confirm" type="password" autocomplete="new-password"></label><div v-if="error" class="error">{{ error }}</div><button :disabled="loading">{{loading?'正在保存…':'保存并进入平台'}}</button></form></main></template>
<style scoped>.page{min-height:100vh;display:grid;place-items:center;padding:20px;background:#f2f6f5;font-family:"Segoe UI","Microsoft YaHei",sans-serif}form{width:min(420px,100%);padding:36px;background:#fff;border:1px solid #dfe7e6;border-radius:16px;box-shadow:0 15px 45px rgba(30,70,65,.08)}h1{font-size:24px;color:#263b3a}p{margin:8px 0 24px;color:#84918f;font-size:13px}label{display:block;margin:15px 0;color:#52605f;font-size:12px;font-weight:600}input{box-sizing:border-box;width:100%;height:43px;margin-top:7px;padding:0 12px;border:1px solid #d8e1e0;border-radius:8px;outline:none}.error{margin:12px 0;padding:9px;color:#a64f48;background:#fff0ee;border-radius:7px;font-size:11px}button{width:100%;height:44px;margin-top:15px;border:0;border-radius:8px;color:#fff;background:#176f6a;cursor:pointer}button:disabled{opacity:.55}</style>
