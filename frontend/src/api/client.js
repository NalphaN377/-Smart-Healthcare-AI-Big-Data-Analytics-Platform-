const BASE = '/api'

async function request(url, options = {}) {
  const response = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload || payload.code !== 0) {
    throw new Error(payload?.message || `请求失败 (${response.status})`)
  }
  return payload
}

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
export async function streamChat(query, callbacks = {}) {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ query }),
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
