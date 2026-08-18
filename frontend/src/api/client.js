const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
// Cold aggregate queries over 2.09M rows can take longer when the dashboard
// starts several requests concurrently. Redis makes repeat loads fast, while
// this finite timeout prevents a valid first load from being reported as down.
const REQUEST_TIMEOUT_MS = 45_000

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function get(path, params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const suffix = query.size ? `?${query.toString()}` : ''
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}${path}${suffix}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.success) {
      throw new ApiError(payload?.message || `请求失败（HTTP ${response.status}）`, response.status)
    }
    return payload
  } catch (error) {
    if (error.name === 'AbortError') throw new ApiError('请求超时，请检查后端服务')
    if (error instanceof ApiError) throw error
    throw new ApiError('无法连接分析服务，请确认 Flask 后端已启动')
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function post(path, body, options = {}) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.success) {
      throw new ApiError(payload?.message || `请求失败（HTTP ${response.status}）`, response.status)
    }
    return payload
  } catch (error) {
    if (error.name === 'AbortError') throw new ApiError('AI 分析超时，请稍后重试', 504)
    if (error instanceof ApiError) throw error
    throw new ApiError('无法连接分析服务，请确认 Flask 后端已启动')
  } finally {
    window.clearTimeout(timeout)
  }
}
