import { get, post } from './client.js'

export const aiApi = {
  status: () => get('/ai/status'),
  query: (query, sessionId = null) =>
    post(
      '/ai/query',
      { query, ...(sessionId ? { session_id: sessionId } : {}) },
      { timeoutMs: 60_000 },
    ),
}

