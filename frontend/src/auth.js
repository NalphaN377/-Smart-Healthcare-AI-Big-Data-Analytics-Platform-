import { computed, reactive } from 'vue'
import { authLogin, authLogout, authMe, setCsrfToken } from './api/client'

const state = reactive({ user: null, ready: false })

function applyAuth(payload) {
  state.user = payload?.user || null
  setCsrfToken(payload?.csrf_token || '')
}

export async function bootstrapAuth() {
  if (state.ready) return state.user
  try { applyAuth((await authMe()).data) } catch (_error) { applyAuth(null) }
  state.ready = true
  return state.user
}

export async function refreshAuth() {
  state.ready = false
  return bootstrapAuth()
}

export async function login(username, password, captcha) {
  const response = await authLogin(username, password, captcha)
  applyAuth(response.data)
  state.ready = true
  return state.user
}

export async function logout() {
  try { await authLogout() } finally { applyAuth(null); state.ready = true }
}

export function clearAuth() { applyAuth(null); state.ready = true }

export function can(permission) { return Boolean(state.user?.permissions?.includes(permission)) }
export const authState = state
export const currentUser = computed(() => state.user)
