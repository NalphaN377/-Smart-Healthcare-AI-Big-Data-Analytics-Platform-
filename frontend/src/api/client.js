const BASE = '/api'
let csrfToken = ''

export function setCsrfToken(token) { csrfToken = token || '' }

async function request(url, options = {}) {
  const method = String(options.method || 'GET').toUpperCase()
  const { skipAuthRedirect = false, ...fetchOptions } = options
  const response = await fetch(BASE + url, {
    ...fetchOptions,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(method !== 'GET' && method !== 'HEAD' && csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload || payload.code !== 0) {
    if (response.status === 401 && !skipAuthRedirect && !url.startsWith('/auth/login')) {
      const redirect = encodeURIComponent(window.location.pathname + window.location.search)
      window.location.assign(`/login?redirect=${redirect}`)
    }
    throw new Error(payload?.message || `请求失败 (${response.status})`)
  }
  return payload
}

export function authLogin(username, password) { return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }), skipAuthRedirect: true }) }
export function authRegister(payload) { return request('/auth/register', { method: 'POST', body: JSON.stringify(payload), skipAuthRedirect: true }) }
export function authLogout() { return request('/auth/logout', { method: 'POST' }) }
export function authMe() { return request('/auth/me', { skipAuthRedirect: true }) }
export function changePassword(currentPassword, newPassword) { return request('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }) }
export function cancelAccount(password, confirmation) { return request('/auth/account', { method: 'DELETE', body: JSON.stringify({ password, confirmation }) }) }
export function listUsers() { return request('/admin/users') }
export function createUser(payload) { return request('/admin/users', { method: 'POST', body: JSON.stringify(payload) }) }
export function updateUser(id, payload) { return request(`/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(payload) }) }
export function deleteUser(id) { return request(`/admin/users/${id}`, { method: 'DELETE' }) }
export function resetUserPassword(id, newPassword) { return request(`/admin/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ new_password: newPassword }) }) }
export function adminHealth() { return request('/admin/system/health') }
export function auditLogs(limit = 100) { return request(`/admin/audit-logs?limit=${limit}`) }
export function publicReports() { return request('/reports/public') }
export function publishReport(id) { return request(`/admin/reports/${id}/publish`, { method: 'PUT' }) }

function queryString(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function health() { return request('/health') }
export function metadata() { return request('/metadata') }
export function overview(filters = {}) { return request(`/overview${queryString(filters)}`) }
export function dataQuality() { return request('/data-quality') }
export function yearTrend(filters = {}) { return request(`/year_trend${queryString(filters)}`) }
export function paymentRatio(filters = {}) { return request(`/payment_ratio${queryString(filters)}`) }
export function dimensionValues(dimension, limit = 100) { return request(`/dimensions/${dimension}/values?limit=${limit}`) }
export function predictCost(features) { return request('/v2/predictions/cost', { method: 'POST', body: JSON.stringify({ features }) }) }

export function aggregate(dimension, metrics, limit = 20, filters = {}) {
  return request(`/aggregate${queryString({ dimension, metrics, limit, ...filters })}`)
}

export function chat(query) {
  return request('/chat', { method: 'POST', body: JSON.stringify({ query }) })
}

export function createReport(payload = {}) {
  return request('/reports', { method: 'POST', body: JSON.stringify(payload) })
}

/** 读取 Flask SSE 流。callbacks: context / delta / done / error */
export async function streamChat(query, callbacks = {}, conversationId = null) {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
    body: JSON.stringify({ query, conversation_id: conversationId }),
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.message || `流式请求失败 (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      let eventName = 'message'
      let data = ''
      block.split(/\r?\n/).forEach((line) => {
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        if (line.startsWith('data:')) data += line.slice(5).trim()
      })
      if (!data) continue
      const payload = JSON.parse(data)
      callbacks[eventName]?.(payload)
      if (eventName === 'error') throw new Error(payload.message || 'AI 流式生成中断')
    }
    if (done) break
  }
}
